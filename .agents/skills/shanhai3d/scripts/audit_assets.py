#!/usr/bin/env python3
"""Reject redundant, orphaned, misplaced, or oversized staged collection assets."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


MIB = 1024 * 1024
DUPLICATE_MIN_BYTES = 1 * MIB
NORMAL_GIT_LIMIT = 50 * MIB
EXTERNAL_STORAGE_LIMIT = 500 * MIB

BINARY_SUFFIXES = {
    ".7z",
    ".aiff",
    ".bin",
    ".blend",
    ".bvh",
    ".exr",
    ".fbx",
    ".gif",
    ".glb",
    ".gltf",
    ".hdr",
    ".jpeg",
    ".jpg",
    ".ktx2",
    ".m4a",
    ".mov",
    ".mp3",
    ".mp4",
    ".obj",
    ".ogg",
    ".png",
    ".rar",
    ".tar",
    ".tga",
    ".tif",
    ".tiff",
    ".tgz",
    ".usd",
    ".usdz",
    ".wav",
    ".webm",
    ".webp",
    ".zip",
}
ARCHIVE_SUFFIXES = {".7z", ".rar", ".tar", ".tgz", ".zip"}


def git(root: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(detail or f"git {' '.join(arguments)} failed")
    return result.stdout


def repo_path(root: Path, value: str) -> str:
    candidate = Path(value)
    absolute = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        return absolute.relative_to(root).as_posix()
    except ValueError as exc:
        raise RuntimeError(f"Path is outside the project root: {value}") from exc


def selected_paths(root: Path, arguments: argparse.Namespace) -> list[str]:
    if arguments.staged:
        raw = git(
            root,
            "diff",
            "--cached",
            "--name-only",
            "--diff-filter=ACMR",
            "-z",
        )
        values = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    else:
        values = arguments.paths
    return sorted({repo_path(root, value) for value in values})


def is_binary(path: Path) -> bool:
    return path.suffix.lower() in BINARY_SUFFIXES


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * MIB), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_provider_binary(relative: str) -> bool:
    parts = Path(relative).parts
    return (
        len(parts) >= 5
        and parts[0] == "collections"
        and parts[2] == "production"
        and parts[3] == "providers"
    )


def collection_root(root: Path, relative: str) -> Path | None:
    parts = Path(relative).parts
    if len(parts) < 3 or parts[0] != "collections":
        return None
    return root / parts[0] / parts[1]


def referenced_by_collection_json(root: Path, relative: str) -> bool:
    collection = collection_root(root, relative)
    if collection is None or not collection.is_dir():
        return True
    relative_to_collection = (root / relative).relative_to(collection).as_posix()
    needles = {
        relative,
        relative_to_collection,
        f"./{relative_to_collection}",
    }
    for json_path in collection.rglob("*.json"):
        try:
            text = json_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(needle in text for needle in needles):
            return True
    return False


def uses_lfs(root: Path, relative: str) -> bool:
    output = git(root, "check-attr", "filter", "--", relative).decode(
        "utf-8", errors="replace"
    )
    return output.rstrip().endswith(": lfs")


def tracked_binary_paths(root: Path) -> list[str]:
    raw = git(root, "ls-files", "-z")
    paths = [item.decode("utf-8") for item in raw.split(b"\0") if item]
    return [
        value
        for value in paths
        if (root / value).is_file() and is_binary(root / value)
    ]


def duplicate_errors(root: Path, candidates: list[str]) -> list[str]:
    binary_candidates = [
        value
        for value in candidates
        if (root / value).is_file()
        and is_binary(root / value)
        and (root / value).stat().st_size >= DUPLICATE_MIN_BYTES
    ]
    if not binary_candidates:
        return []

    all_paths = sorted(set(tracked_binary_paths(root)) | set(binary_candidates))
    paths_by_size: dict[int, list[str]] = defaultdict(list)
    for value in all_paths:
        path = root / value
        if path.is_file() and path.stat().st_size >= DUPLICATE_MIN_BYTES:
            paths_by_size[path.stat().st_size].append(value)

    errors: list[str] = []
    reported: set[tuple[str, ...]] = set()
    digest_cache: dict[str, str] = {}
    for candidate in binary_candidates:
        peers = paths_by_size[(root / candidate).stat().st_size]
        if len(peers) < 2:
            continue
        if candidate not in digest_cache:
            digest_cache[candidate] = sha256(root / candidate)
        candidate_digest = digest_cache[candidate]
        matches = []
        for peer in peers:
            if peer not in digest_cache:
                digest_cache[peer] = sha256(root / peer)
            peer_digest = digest_cache[peer]
            if peer_digest == candidate_digest:
                matches.append(peer)
        group = tuple(sorted(matches))
        if len(group) > 1 and group not in reported:
            reported.add(group)
            errors.append(
                "duplicate binary content must have one canonical path: "
                + ", ".join(group)
            )
    return errors


def audit(root: Path, candidates: list[str]) -> list[str]:
    errors: list[str] = []
    for relative in candidates:
        path = root / relative
        if not path.is_file() or not is_binary(path):
            continue
        size = path.stat().st_size
        suffix = path.suffix.lower()

        if is_provider_binary(relative):
            errors.append(
                f"provider binary must stay in .agents/runtime and be promoted once: {relative}"
            )
        if suffix in ARCHIVE_SUFFIXES and collection_root(root, relative):
            errors.append(f"provider/source archives require external storage: {relative}")
        if size >= EXTERNAL_STORAGE_LIMIT:
            errors.append(
                f"binary is {size / MIB:.1f} MiB and must use approved external storage: {relative}"
            )
        elif size >= NORMAL_GIT_LIMIT and not uses_lfs(root, relative):
            errors.append(
                f"binary is {size / MIB:.1f} MiB but is not tracked by LFS: {relative}"
            )
        if collection_root(root, relative) and not referenced_by_collection_json(
            root, relative
        ):
            errors.append(
                "collection binary is not referenced by collection/manifest/audit/QC JSON: "
                f"{relative}"
            )

    errors.extend(duplicate_errors(root, candidates))
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--staged",
        action="store_true",
        help="Audit added, copied, modified, and renamed paths in the Git index",
    )
    selection.add_argument("--paths", nargs="+", help="Audit explicit paths")
    return parser.parse_args()


def main() -> int:
    arguments = parse_args()
    root = Path(arguments.project_root).expanduser().resolve()
    try:
        git(root, "rev-parse", "--is-inside-work-tree")
        candidates = selected_paths(root, arguments)
        errors = audit(root, candidates)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"asset audit error: {exc}", file=sys.stderr)
        return 2

    if errors:
        print("Asset admission failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print(f"Asset admission passed for {len(candidates)} path(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
