#!/usr/bin/env python3
"""Upload, rig, animate and download Tripo tasks with sanitized audit records."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from env_utils import load_project_env


API_BASE = "https://openapi.tripo3d.ai/v3"
TERMINAL = {"success", "failed", "cancelled"}
RIG_TYPES = (
    "biped",
    "quadruped",
    "hexapod",
    "octopod",
    "avian",
    "serpentine",
    "aquatic",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object: {path}")
    return value


def next_record_path(directory: Path, suffix: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    indexes = []
    for path in directory.glob("[0-9][0-9][0-9]-*.json"):
        try:
            indexes.append(int(path.name[:3]))
        except ValueError:
            continue
    return directory / f"{max(indexes, default=0) + 1:03d}-{suffix}.json"


def provider_root(collection: Path) -> Path:
    return collection / "production" / "providers" / "tripo"


def load_key(project_root: Path) -> str:
    load_project_env(project_root)
    key = os.environ.get("TRIPO_API_KEY", "").strip()
    if not key:
        raise RuntimeError("TRIPO_API_KEY is missing")
    return key


def api_request(
    key: str,
    path: str,
    *,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    body: bytes | None = None,
    content_type: str | None = None,
    timeout: int = 300,
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    if json_body is not None:
        body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        content_type = "application/json"
    if content_type:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(
        f"{API_BASE}{path}", data=body, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Tripo API request failed ({exc.code}): {detail}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Tripo API returned an unexpected response")
    if payload.get("code") not in (None, 0):
        raise RuntimeError(
            f"Tripo API error {payload.get('code')}: {payload.get('message') or 'unknown'}"
        )
    return payload


def encode_file(path: Path) -> tuple[bytes, str]:
    boundary = f"----shanhaiworld-{uuid.uuid4().hex}"
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    chunks = [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(),
        path.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def task_store(collection: Path) -> tuple[Path, dict[str, Any]]:
    path = provider_root(collection) / "tasks.json"
    if path.exists():
        store = read_json(path)
    else:
        store = {
            "schema_version": 1,
            "creature_id": collection.name,
            "provider": "tripo",
            "tasks": [],
        }
    if not isinstance(store.get("tasks"), list):
        raise RuntimeError(f"Invalid tasks array: {path}")
    return path, store


def file_store(collection: Path) -> tuple[Path, dict[str, Any]]:
    path = provider_root(collection) / "files.json"
    if path.exists():
        store = read_json(path)
    else:
        store = {"schema_version": 1, "creature_id": collection.name, "files": []}
    if not isinstance(store.get("files"), list):
        raise RuntimeError(f"Invalid files array: {path}")
    return path, store


def safe_task(data: dict[str, Any]) -> dict[str, Any]:
    output = data.get("output") if isinstance(data.get("output"), dict) else {}
    safe_output = {
        key: output.get(key)
        for key in ("riggable", "rig_type")
        if key in output
    }
    safe_output["available_files"] = sorted(
        key for key, value in output.items() if "url" in key.lower() and value
    )
    return {
        "task_id": data.get("task_id"),
        "type": data.get("type"),
        "status": data.get("status"),
        "progress": data.get("progress"),
        "credits_consumed": data.get("credits_consumed"),
        "error_code": data.get("error_code"),
        "error_message": data.get("error_message"),
        "output": safe_output,
        "created_at": data.get("created_at"),
        "completed_at": data.get("completed_at"),
    }


def submit_task(
    project_root: Path,
    collection: Path,
    kind: str,
    endpoint: str,
    parameters: dict[str, Any],
) -> str:
    request_path = next_record_path(provider_root(collection) / "requests", kind)
    write_json(
        request_path,
        {
            "schema_version": 1,
            "created_at": now_iso(),
            "provider": "tripo",
            "endpoint": endpoint,
            "parameters": parameters,
            "credentials_recorded": False,
        },
    )
    payload = api_request(load_key(project_root), endpoint, method="POST", json_body=parameters)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    task_id = data.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        raise RuntimeError("Tripo did not return a task_id")
    response_path = next_record_path(provider_root(collection) / "responses", kind)
    write_json(
        response_path,
        {
            "schema_version": 1,
            "created_at": now_iso(),
            "task_id": task_id,
            "accepted": True,
        },
    )
    path, store = task_store(collection)
    store["tasks"].append(
        {
            "kind": kind,
            "task_id": task_id,
            "status": "submitted",
            "submitted_at": now_iso(),
            "request_record": str(request_path.relative_to(project_root)),
            "response_record": str(response_path.relative_to(project_root)),
        }
    )
    write_json(path, store)
    print(json.dumps({"submitted": True, "kind": kind, "task_id": task_id}))
    return task_id


def latest_file_token(collection: Path) -> str:
    _, store = file_store(collection)
    if not store["files"]:
        raise RuntimeError("No Tripo file has been uploaded for this collection")
    token = store["files"][-1].get("file_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Latest Tripo file_token is unavailable")
    return token


def select_task(collection: Path, task_id: str | None, kind: str | None = None) -> dict[str, Any]:
    _, store = task_store(collection)
    candidates = [task for task in store["tasks"] if not kind or task.get("kind") == kind]
    if task_id:
        candidates = [task for task in candidates if task.get("task_id") == task_id]
    if not candidates:
        raise RuntimeError("Matching Tripo task is unavailable")
    return candidates[-1]


def command_upload(args: argparse.Namespace) -> int:
    root = Path(args.project_root).expanduser().resolve()
    collection = Path(args.collection).expanduser().resolve()
    source = Path(args.file).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".glb":
        raise RuntimeError("Tripo rig input must be an existing GLB file")
    if source.stat().st_size > 150 * 1024 * 1024:
        raise RuntimeError("Tripo rig input exceeds the documented 150 MB limit")
    request_path = next_record_path(provider_root(collection) / "requests", "upload")
    write_json(
        request_path,
        {
            "schema_version": 1,
            "created_at": now_iso(),
            "provider": "tripo",
            "endpoint": "/files",
            "input_file": str(source.relative_to(root)),
            "bytes": source.stat().st_size,
            "credentials_recorded": False,
        },
    )
    body, content_type = encode_file(source)
    payload = api_request(
        load_key(root), "/files", method="POST", body=body, content_type=content_type
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    token = data.get("file_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Tripo did not return a file_token")
    response_path = next_record_path(provider_root(collection) / "responses", "upload")
    write_json(
        response_path,
        {
            "schema_version": 1,
            "created_at": now_iso(),
            "uploaded": True,
            "file_token": token,
        },
    )
    path, store = file_store(collection)
    store["files"].append(
        {
            "file_token": token,
            "local_path": str(source.relative_to(root)),
            "bytes": source.stat().st_size,
            "uploaded_at": now_iso(),
            "request_record": str(request_path.relative_to(root)),
            "response_record": str(response_path.relative_to(root)),
        }
    )
    write_json(path, store)
    print(json.dumps({"uploaded": True, "file_token": token}))
    return 0


def command_rig_check(args: argparse.Namespace) -> int:
    root = Path(args.project_root).expanduser().resolve()
    collection = Path(args.collection).expanduser().resolve()
    submit_task(root, collection, "rig-check", "/animations/rig-check", {"input": latest_file_token(collection)})
    return 0


def command_rig(args: argparse.Namespace) -> int:
    root = Path(args.project_root).expanduser().resolve()
    collection = Path(args.collection).expanduser().resolve()
    parameters = {
        "input": latest_file_token(collection),
        "model": args.model,
        "rig_type": args.rig_type,
        "spec": "tripo",
        "out_format": "glb",
    }
    submit_task(root, collection, "rig", "/animations/rig", parameters)
    return 0


def command_retarget(args: argparse.Namespace) -> int:
    root = Path(args.project_root).expanduser().resolve()
    collection = Path(args.collection).expanduser().resolve()
    rig_task = select_task(collection, args.rig_task, kind="rig")
    parameters = {
        "input": rig_task["task_id"],
        "animations": args.animations,
        "out_format": "glb",
        "bake_animation": True,
        "animate_in_place": True,
    }
    submit_task(root, collection, "retarget", "/animations/retarget", parameters)
    return 0


def command_poll(args: argparse.Namespace) -> int:
    root = Path(args.project_root).expanduser().resolve()
    collection = Path(args.collection).expanduser().resolve()
    key = load_key(root)
    selected = select_task(collection, args.task_id)
    deadline = time.monotonic() + args.timeout
    last_status = None
    raw_data: dict[str, Any] = {}
    while True:
        payload = api_request(key, f"/tasks/{selected['task_id']}")
        raw_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        status = str(raw_data.get("status") or "unknown").lower()
        if status != last_status:
            print(json.dumps({"task_id": selected["task_id"], "status": status, "progress": raw_data.get("progress")}))
            sys.stdout.flush()
            last_status = status
        if status in TERMINAL:
            break
        if time.monotonic() >= deadline:
            status = "timeout"
            break
        time.sleep(args.interval)

    response_path = next_record_path(provider_root(collection) / "responses", "task")
    write_json(
        response_path,
        {"schema_version": 1, "checked_at": now_iso(), **safe_task(raw_data)},
    )
    path, store = task_store(collection)
    for task in store["tasks"]:
        if task.get("task_id") == selected["task_id"]:
            task["status"] = status
            task["updated_at"] = now_iso()
            task["status_record"] = str(response_path.relative_to(root))
            task["credits_consumed"] = raw_data.get("credits_consumed")
            task["output_summary"] = safe_task(raw_data).get("output")
            break
    write_json(path, store)
    return 0 if status == "success" else 1


def collect_urls(value: Any, prefix: str = "output") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(collect_urls(item, f"{prefix}-{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value, 1):
            found.extend(collect_urls(item, f"{prefix}-{index}"))
    elif isinstance(value, str) and value.startswith(("https://", "http://")):
        found.append((prefix, value))
    return found


def safe_filename(label: str, url: str, index: int) -> str:
    path_name = Path(urllib.parse.urlparse(url).path).name
    suffix = Path(path_name).suffix.lower()
    if suffix not in {".glb", ".gltf", ".fbx", ".png", ".jpg", ".jpeg", ".webp"}:
        suffix = ".bin"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip(".-") or f"output-{index}"
    return f"{index:02d}-{stem}{suffix}"


def command_download(args: argparse.Namespace) -> int:
    root = Path(args.project_root).expanduser().resolve()
    collection = Path(args.collection).expanduser().resolve()
    selected = select_task(collection, args.task_id)
    payload = api_request(load_key(root), f"/tasks/{selected['task_id']}")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if str(data.get("status")).lower() != "success":
        raise RuntimeError("Tripo task is not successful yet")
    urls = collect_urls(data.get("output", {}))
    if not urls:
        raise RuntimeError("Tripo task returned no downloadable output")
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded = []
    for index, (label, url) in enumerate(urls, 1):
        filename = safe_filename(label, url, index)
        destination = out_dir / filename
        with urllib.request.urlopen(url, timeout=300) as response:
            destination.write_bytes(response.read())
        downloaded.append(
            {
                "label": label,
                "local_path": str(destination.relative_to(root)),
                "bytes": destination.stat().st_size,
            }
        )
    response_path = next_record_path(provider_root(collection) / "responses", "download")
    write_json(
        response_path,
        {
            "schema_version": 1,
            "created_at": now_iso(),
            "task_id": selected["task_id"],
            "downloaded": downloaded,
            "signed_urls_recorded": False,
        },
    )
    path, store = task_store(collection)
    for task in store["tasks"]:
        if task.get("task_id") == selected["task_id"]:
            task["download_record"] = str(response_path.relative_to(root))
            task["downloaded_files"] = [item["local_path"] for item in downloaded]
            task["updated_at"] = now_iso()
            break
    write_json(path, store)
    print(json.dumps({"downloaded": len(downloaded), "files": downloaded}))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)

    upload = subparsers.add_parser("upload")
    upload.add_argument("--collection", required=True)
    upload.add_argument("--file", required=True)
    upload.set_defaults(func=command_upload)

    rig_check = subparsers.add_parser("rig-check")
    rig_check.add_argument("--collection", required=True)
    rig_check.set_defaults(func=command_rig_check)

    rig = subparsers.add_parser("rig")
    rig.add_argument("--collection", required=True)
    rig.add_argument("--rig-type", choices=RIG_TYPES, required=True)
    rig.add_argument("--model", default="v2.5-20260210")
    rig.set_defaults(func=command_rig)

    retarget = subparsers.add_parser("retarget")
    retarget.add_argument("--collection", required=True)
    retarget.add_argument("--rig-task")
    retarget.add_argument("--animations", nargs="+", required=True)
    retarget.set_defaults(func=command_retarget)

    poll = subparsers.add_parser("poll")
    poll.add_argument("--collection", required=True)
    poll.add_argument("--task-id")
    poll.add_argument("--interval", type=int, default=10)
    poll.add_argument("--timeout", type=int, default=1200)
    poll.set_defaults(func=command_poll)

    download = subparsers.add_parser("download")
    download.add_argument("--collection", required=True)
    download.add_argument("--task-id")
    download.add_argument("--out-dir", required=True)
    download.set_defaults(func=command_download)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return args.func(args)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
