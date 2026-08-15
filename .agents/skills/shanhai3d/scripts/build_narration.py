#!/usr/bin/env python3
"""Build the collection's fixed Mandarin narration with the shared voice profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any


SHARED_VOICE_PROFILE = "mandarin-tingting-r160-v1"
VOICE_PROFILES: dict[str, dict[str, Any]] = {
    SHARED_VOICE_PROFILE: {
        "voice": "Tingting",
        "rate": 160,
        "sample_rate": 22050,
        "bitrate": 32000,
        "quality": 64,
        "strategy": 1,
    }
}


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected a JSON object in {path}")
    return data


def normalized_text(value: str) -> str:
    return "".join(value.split())


def resolve_collection_path(collection_root: Path, raw_path: str) -> Path:
    path = (collection_root / raw_path).resolve()
    try:
        path.relative_to(collection_root.resolve())
    except ValueError as error:
        raise RuntimeError(f"Narration path escapes collection root: {raw_path}") from error
    return path


def required_tool(path: str) -> str:
    resolved = shutil.which(path)
    if not resolved:
        raise RuntimeError(f"Required macOS audio tool is unavailable: {path}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate one fixed Mandarin narration for a Shanhaiworld collection."
    )
    parser.add_argument("slug")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--prompt-file", required=True)
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    collection_root = (project_root / "collections" / args.slug).resolve()
    config_path = collection_root / "collection.json"
    config = read_json(config_path)
    narration = config.get("narration")
    if not isinstance(narration, dict):
        raise RuntimeError("collection.json must define narration")

    profile_id = narration.get("voice_profile")
    profile = VOICE_PROFILES.get(profile_id)
    if not profile:
        raise RuntimeError(
            f"narration.voice_profile must be {SHARED_VOICE_PROFILE!r}"
        )
    audio_ref = narration.get("audio")
    if not isinstance(audio_ref, str) or not audio_ref.strip():
        raise RuntimeError("collection.json must define narration.audio")
    output_path = resolve_collection_path(collection_root, audio_ref)
    if output_path.exists():
        raise RuntimeError(
            f"Refusing to overwrite narration asset; choose a versioned path: {output_path}"
        )

    config_text = narration.get("text")
    if not isinstance(config_text, str) or not config_text.strip():
        raise RuntimeError("collection.json must define non-empty narration.text")
    prompt_path = Path(args.prompt_file).resolve()
    prompt_text = prompt_path.read_text(encoding="utf-8").strip()
    if normalized_text(prompt_text) != normalized_text(config_text):
        raise RuntimeError("Narration prompt text does not match collection.json narration.text")

    say = required_tool("say")
    afconvert = required_tool("afconvert")
    runtime_root = project_root / ".agents" / "runtime" / args.slug
    runtime_root.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="narration-", dir=runtime_root) as temp_dir:
        temp_root = Path(temp_dir)
        speech_path = temp_root / "narration.aiff"
        encoded_path = temp_root / "narration.m4a"
        source_text = temp_root / "narration.txt"
        source_text.write_text(prompt_text + "\n", encoding="utf-8")
        subprocess.run(
            [
                say,
                "-v",
                str(profile["voice"]),
                "-r",
                str(profile["rate"]),
                "-f",
                str(source_text),
                "-o",
                str(speech_path),
            ],
            check=True,
        )
        subprocess.run(
            [
                afconvert,
                str(speech_path),
                str(encoded_path),
                "-f",
                "m4af",
                "-d",
                "aac",
                "-b",
                str(profile["bitrate"]),
                "-q",
                str(profile["quality"]),
                "-s",
                str(profile["strategy"]),
            ],
            check=True,
        )
        os.replace(encoded_path, output_path)

    payload = output_path.read_bytes()
    result = {
        "slug": args.slug,
        "voice_profile": profile_id,
        "voice": profile["voice"],
        "rate": profile["rate"],
        "path": str(output_path.relative_to(project_root)),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
