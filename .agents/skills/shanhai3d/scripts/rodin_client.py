#!/usr/bin/env python3
"""Submit and retrieve Hyper3D Rodin tasks without exposing credentials or signed URLs."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from env_utils import load_project_env


BASE_URL = "https://api.hyper3d.com/api/v2"
TERMINAL_FAILURES = {"Failed", "Canceled", "Cancelled", "Error"}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object in {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def next_record_path(directory: Path, purpose: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    highest = 0
    for path in directory.glob("[0-9][0-9][0-9]-*.json"):
        try:
            highest = max(highest, int(path.name[:3]))
        except ValueError:
            pass
    return directory / f"{highest + 1:03d}-{purpose}.json"


def load_key(project_root: Path) -> str:
    load_project_env(project_root)
    key = os.environ.get("RODIN_API_KEY", "").strip()
    if not key:
        raise RuntimeError("RODIN_API_KEY is missing")
    return key


def api_request(
    key: str,
    path: str,
    *,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    body: bytes | None = None,
    content_type: str | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif content_type:
        headers["Content-Type"] = content_type

    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"error": f"HTTP_{exc.code}"}
        error = payload.get("error") or f"HTTP {exc.code}"
        message = payload.get("message")
        detail = f"{error}: {message}" if message and message != error else str(error)
        raise RuntimeError(f"Rodin API request failed ({exc.code}): {detail}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Rodin API returned an unexpected response")
    return payload


def encode_multipart(
    fields: list[tuple[str, str]], images: list[Path]
) -> tuple[bytes, str]:
    boundary = f"----shanhaiworld-{uuid.uuid4().hex}"
    chunks: list[bytes] = []

    def append(value: str) -> None:
        chunks.append(value.encode("utf-8"))

    for name, value in fields:
        append(f"--{boundary}\r\n")
        append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n')
        append(value)
        append("\r\n")

    for image in images:
        mime = mimetypes.guess_type(image.name)[0] or "application/octet-stream"
        append(f"--{boundary}\r\n")
        append(
            f'Content-Disposition: form-data; name="images"; filename="{image.name}"\r\n'
        )
        append(f"Content-Type: {mime}\r\n\r\n")
        chunks.append(image.read_bytes())
        append("\r\n")

    append(f"--{boundary}--\r\n")
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def provider_root(collection: Path) -> Path:
    return collection / "production" / "providers" / "rodin"


def write_status_token(project_root: Path, task_uuid: str, token: str | None) -> str | None:
    if not token:
        return None
    path = project_root / ".agents" / "runtime" / "rodin" / f"{task_uuid}.token"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token, encoding="utf-8")
    path.chmod(0o600)
    return str(path.relative_to(project_root))


def read_status_token(project_root: Path, task: dict[str, Any]) -> str:
    reference = task.get("status_token_file")
    if not reference:
        raise RuntimeError("Task status token is unavailable")
    path = project_root / str(reference)
    token = path.read_text(encoding="utf-8").strip()
    if not token:
        raise RuntimeError("Task status token is empty")
    return token


def task_store(collection: Path) -> tuple[Path, dict[str, Any]]:
    path = provider_root(collection) / "tasks.json"
    if path.exists():
        value = read_json(path)
    else:
        value = {
            "schema_version": 1,
            "creature_id": collection.name,
            "provider": "hyper3d_rodin_gen2",
            "tasks": [],
        }
    if not isinstance(value.get("tasks"), list):
        raise RuntimeError(f"Expected tasks array in {path}")
    return path, value


def latest_task(collection: Path) -> dict[str, Any]:
    _, store = task_store(collection)
    tasks = store["tasks"]
    if not tasks:
        raise RuntimeError("No Rodin task has been submitted for this collection")
    task = tasks[-1]
    if not isinstance(task, dict):
        raise RuntimeError("Invalid task record")
    return task


def safe_response(payload: dict[str, Any]) -> dict[str, Any]:
    jobs = payload.get("jobs") if isinstance(payload.get("jobs"), dict) else {}
    return {
        "error": payload.get("error"),
        "message": payload.get("message"),
        "uuid": payload.get("uuid"),
        "jobs": {
            "uuids": jobs.get("uuids", []),
        },
    }


def command_balance(args: argparse.Namespace) -> int:
    root = Path(args.project_root).expanduser().resolve()
    payload = api_request(load_key(root), "/check_balance")
    print(json.dumps({"authenticated": True, "balance": payload.get("balance")}))
    return 0


def command_submit(args: argparse.Namespace) -> int:
    root = Path(args.project_root).expanduser().resolve()
    collection = Path(args.collection).expanduser().resolve()
    images = [Path(value).expanduser().resolve() for value in args.images]
    if not 1 <= len(images) <= 5:
        raise RuntimeError("Rodin accepts one to five images")
    for image in images:
        if not image.is_file():
            raise RuntimeError(f"Image not found: {image}")

    prompt = Path(args.prompt_file).read_text(encoding="utf-8").strip()
    if args.mesh_mode == "Raw" and not args.standard_textures:
        raise RuntimeError(
            "Rodin HighPack is incompatible with Raw mode; use Quad or pass --standard-textures"
        )
    fields = [
        ("tier", "Gen-2"),
        ("condition_mode", "concat"),
        ("prompt", prompt),
        ("geometry_file_format", "glb"),
        ("material", "PBR"),
        ("mesh_mode", args.mesh_mode),
        ("quality", args.quality),
        ("preview_render", "true"),
        ("use_original_alpha", "false"),
        ("bbox_condition", "[100,85,150]"),
    ]
    if args.quality_override is not None:
        fields.append(("quality_override", str(args.quality_override)))
    if not args.standard_textures:
        fields.append(("addons", "HighPack"))
    estimated_credit_cost = 0.5 if args.standard_textures else 1.5
    request_summary = {
        "schema_version": 1,
        "created_at": now_iso(),
        "provider": "hyper3d_rodin_gen2",
        "endpoint": "/api/v2/rodin",
        "input_files": [str(path.relative_to(root)) for path in images],
        "prompt_file": str(Path(args.prompt_file).resolve().relative_to(root)),
        "parameters": dict(fields),
        "estimated_credit_cost": estimated_credit_cost,
        "credentials_recorded": False,
    }
    request_path = next_record_path(provider_root(collection) / "requests", "submit")
    write_json(request_path, request_summary)

    body, content_type = encode_multipart(fields, images)
    payload = api_request(
        load_key(root),
        "/rodin",
        method="POST",
        body=body,
        content_type=content_type,
        timeout=300,
    )
    summary = safe_response(payload)
    if not summary.get("uuid"):
        raise RuntimeError(
            f"Rodin did not return a task UUID: {summary.get('error') or summary.get('message')}"
        )

    response_path = next_record_path(provider_root(collection) / "responses", "submit")
    write_json(
        response_path,
        {"schema_version": 1, "created_at": now_iso(), **summary},
    )
    path, store = task_store(collection)
    response_jobs = payload.get("jobs") if isinstance(payload.get("jobs"), dict) else {}
    token_file = write_status_token(root, summary["uuid"], response_jobs.get("subscription_key"))
    task = {
        "task_uuid": summary["uuid"],
        "status_token_file": token_file,
        "job_uuids": summary["jobs"].get("uuids", []),
        "status": "Submitted",
        "submitted_at": now_iso(),
        "request_record": str(request_path.relative_to(root)),
        "response_record": str(response_path.relative_to(root)),
        "credit_cost": estimated_credit_cost,
    }
    store["tasks"].append(task)
    write_json(path, store)
    print(json.dumps({"submitted": True, "task_uuid": task["task_uuid"]}))
    return 0


def command_bang(args: argparse.Namespace) -> int:
    root = Path(args.project_root).expanduser().resolve()
    collection = Path(args.collection).expanduser().resolve()
    source_task = latest_task(collection)
    asset_id = args.asset_id or source_task.get("task_uuid")
    if not asset_id:
        raise RuntimeError("BANG requires a Rodin Gen-2 task UUID")

    request_payload = {
        "asset_id": asset_id,
        "strength": args.strength,
        "geometry_file_format": "glb",
        "material": "PBR",
        "resolution": "Basic",
    }
    request_path = next_record_path(provider_root(collection) / "requests", "bang")
    write_json(
        request_path,
        {
            "schema_version": 1,
            "created_at": now_iso(),
            "provider": "hyper3d_rodin_bang",
            "endpoint": "/api/v2/bang",
            "parameters": request_payload,
            "estimated_credit_cost": 0.5,
            "credentials_recorded": False,
        },
    )
    payload = api_request(
        load_key(root),
        "/bang",
        method="POST",
        json_body=request_payload,
        timeout=300,
    )
    summary = safe_response(payload)
    if not summary.get("uuid"):
        raise RuntimeError(
            f"Rodin BANG did not return a task UUID: {summary.get('error') or summary.get('message')}"
        )

    response_path = next_record_path(provider_root(collection) / "responses", "bang")
    write_json(response_path, {"schema_version": 1, "created_at": now_iso(), **summary})
    path, store = task_store(collection)
    response_jobs = payload.get("jobs") if isinstance(payload.get("jobs"), dict) else {}
    token_file = write_status_token(root, summary["uuid"], response_jobs.get("subscription_key"))
    task = {
        "kind": "bang",
        "source_asset_id": asset_id,
        "task_uuid": summary["uuid"],
        "status_token_file": token_file,
        "job_uuids": summary["jobs"].get("uuids", []),
        "status": "Submitted",
        "submitted_at": now_iso(),
        "request_record": str(request_path.relative_to(root)),
        "response_record": str(response_path.relative_to(root)),
        "credit_cost": 0.5,
    }
    store["tasks"].append(task)
    write_json(path, store)
    print(json.dumps({"submitted": True, "kind": "bang", "task_uuid": task["task_uuid"]}))
    return 0


def status_once(project_root: Path, key: str, task: dict[str, Any]) -> dict[str, Any]:
    subscription_key = read_status_token(project_root, task)
    payload = api_request(
        key,
        "/status",
        method="POST",
        json_body={"subscription_key": subscription_key},
    )
    jobs = payload.get("jobs") if isinstance(payload.get("jobs"), list) else []
    return {
        "error": payload.get("error"),
        "jobs": [
            {"uuid": item.get("uuid"), "status": item.get("status")}
            for item in jobs
            if isinstance(item, dict)
        ],
    }


def command_poll(args: argparse.Namespace) -> int:
    root = Path(args.project_root).expanduser().resolve()
    collection = Path(args.collection).expanduser().resolve()
    key = load_key(root)
    task = latest_task(collection)
    deadline = time.monotonic() + args.timeout
    last_states: tuple[str, ...] | None = None
    while True:
        status = status_once(root, key, task)
        states = tuple(str(job.get("status")) for job in status["jobs"])
        if states != last_states:
            print(json.dumps({"task_uuid": task.get("task_uuid"), "states": states}))
            sys.stdout.flush()
            last_states = states
        if states and all(state == "Done" for state in states):
            final_status = "Done"
            break
        if any(state in TERMINAL_FAILURES for state in states):
            final_status = "Failed"
            break
        if time.monotonic() >= deadline:
            final_status = "Timeout"
            break
        time.sleep(args.interval)

    response_path = next_record_path(provider_root(collection) / "responses", "status")
    write_json(
        response_path,
        {
            "schema_version": 1,
            "created_at": now_iso(),
            "task_uuid": task.get("task_uuid"),
            "status": final_status,
            "jobs": status["jobs"],
        },
    )
    path, store = task_store(collection)
    store["tasks"][-1]["status"] = final_status
    store["tasks"][-1]["status_record"] = str(response_path.relative_to(root))
    store["tasks"][-1]["updated_at"] = now_iso()
    token_reference = store["tasks"][-1].pop("status_token_file", None)
    if token_reference:
        token_path = root / str(token_reference)
        if token_path.is_file():
            token_path.unlink()
    write_json(path, store)
    return 0 if final_status == "Done" else 1


def safe_filename(value: str, fallback: str) -> str:
    name = Path(value).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return name or fallback


def command_download(args: argparse.Namespace) -> int:
    root = Path(args.project_root).expanduser().resolve()
    collection = Path(args.collection).expanduser().resolve()
    key = load_key(root)
    store_path, store = task_store(collection)
    task_index = len(store["tasks"]) - 1
    if args.task_uuid:
        task_index = next(
            (
                index
                for index, candidate in enumerate(store["tasks"])
                if isinstance(candidate, dict)
                and candidate.get("task_uuid") == args.task_uuid
            ),
            -1,
        )
        if task_index < 0:
            raise RuntimeError(f"Unknown Rodin task UUID: {args.task_uuid}")
    if task_index < 0:
        raise RuntimeError("No Rodin task has been submitted for this collection")
    task = store["tasks"][task_index]
    if not isinstance(task, dict):
        raise RuntimeError("Invalid task record")
    task_uuid = task.get("task_uuid")
    payload = api_request(
        key,
        "/download",
        method="POST",
        json_body={"task_uuid": task_uuid},
    )
    items = payload.get("list") if isinstance(payload.get("list"), list) else []
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    downloaded: list[dict[str, Any]] = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict) or not item.get("url"):
            continue
        name = safe_filename(str(item.get("name") or ""), f"rodin-{index}")
        destination = out_dir / name
        if destination.exists():
            destination = out_dir / f"{destination.stem}-v2{destination.suffix}"
        request = urllib.request.Request(str(item["url"]), headers={"Accept": "*/*"})
        with urllib.request.urlopen(request, timeout=300) as response:
            destination.write_bytes(response.read())
        downloaded.append(
            {
                "provider_name": item.get("name"),
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
            "task_uuid": task_uuid,
            "error": payload.get("error"),
            "files": downloaded,
            "signed_urls_recorded": False,
        },
    )
    store["tasks"][task_index]["download_record"] = str(response_path.relative_to(root))
    store["tasks"][task_index]["downloaded_files"] = [
        item["local_path"] for item in downloaded
    ]
    store["tasks"][task_index]["updated_at"] = now_iso()
    store["tasks"][task_index].pop("runtime_files_removed_at", None)
    write_json(store_path, store)
    print(json.dumps({"downloaded": len(downloaded), "files": downloaded}))
    return 0 if downloaded else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    subparsers = parser.add_subparsers(dest="command", required=True)

    balance = subparsers.add_parser("balance")
    balance.set_defaults(func=command_balance)

    submit = subparsers.add_parser("submit")
    submit.add_argument("--collection", required=True)
    submit.add_argument("--prompt-file", required=True)
    submit.add_argument("--images", nargs="+", required=True)
    submit.add_argument(
        "--mesh-mode",
        choices=("Quad", "Raw"),
        default="Quad",
        help="Rodin mesh topology mode (default: Quad for downstream rigging)",
    )
    submit.add_argument(
        "--quality",
        choices=("high", "medium", "low", "extra-low"),
        default="high",
        help="Rodin source mesh quality (default: high)",
    )
    submit.add_argument(
        "--quality-override",
        type=int,
        help="Optional provider-supported face-count override",
    )
    submit.add_argument(
        "--standard-textures",
        action="store_true",
        help="Use standard textures instead of the paid 4K HighPack addon",
    )
    submit.set_defaults(func=command_submit)

    bang = subparsers.add_parser("bang")
    bang.add_argument("--collection", required=True)
    bang.add_argument("--asset-id")
    bang.add_argument("--strength", type=int, default=5)
    bang.set_defaults(func=command_bang)

    poll = subparsers.add_parser("poll")
    poll.add_argument("--collection", required=True)
    poll.add_argument("--interval", type=int, default=10)
    poll.add_argument("--timeout", type=int, default=1200)
    poll.set_defaults(func=command_poll)

    download = subparsers.add_parser("download")
    download.add_argument("--collection", required=True)
    download.add_argument("--out-dir", required=True)
    download.add_argument(
        "--task-uuid",
        help="Download a specific recorded task instead of the latest task",
    )
    download.set_defaults(func=command_download)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        return args.func(args)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
