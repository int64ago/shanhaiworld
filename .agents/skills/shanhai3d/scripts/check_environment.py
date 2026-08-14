#!/usr/bin/env python3
"""Report Shanhai3d prerequisites without exposing secret values."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
from pathlib import Path

from env_utils import load_project_env


REQUIRED_KEYS = ("RODIN_API_KEY", "TRIPO_API_KEY")
OPTIONAL_KEYS = ("MESHY_API_KEY",)
COMMANDS = ("python3", "node", "npm", "npx")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check local Shanhai3d prerequisites without printing secrets."
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with status 1 when a required API key is missing",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.project_root).expanduser().resolve()
    all_keys = REQUIRED_KEYS + OPTIONAL_KEYS
    process_keys = {name for name in all_keys if os.environ.get(name, "").strip()}
    try:
        loaded_keys = set(load_project_env(root))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    keys = {name: bool(os.environ.get(name, "").strip()) for name in all_keys}
    key_sources = {
        name: (
            "process"
            if name in process_keys
            else ".env"
            if name in loaded_keys and keys[name]
            else "missing"
        )
        for name in all_keys
    }
    commands = {name: shutil.which(name) for name in COMMANDS}
    missing = [name for name in REQUIRED_KEYS if not keys[name]]

    payload = {
        "project_root": str(root),
        "python": platform.python_version(),
        "env_file": {
            "path": str(root / ".env"),
            "exists": (root / ".env").is_file(),
            "loaded_keys": sorted(loaded_keys),
        },
        "keys_configured": keys,
        "key_sources": key_sources,
        "required_keys": list(REQUIRED_KEYS),
        "optional_keys": list(OPTIONAL_KEYS),
        "commands": commands,
        "image_generation": "codex_builtin_imagegen",
        "ready_for_3d_pipeline": not missing,
        "missing": missing,
        "note": "Process environment values take precedence over root .env. Secret values are never displayed.",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if args.strict and missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
