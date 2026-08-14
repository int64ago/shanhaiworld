#!/usr/bin/env python3
"""Load project-local environment variables without external dependencies."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


ENV_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _parse_value(raw: str, *, path: Path, line_number: int) -> str:
    value = raw.strip()
    if not value:
        return ""

    if value.startswith('"'):
        try:
            parsed, end = json.JSONDecoder().raw_decode(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid double-quoted value at {path}:{line_number}") from exc
        if not isinstance(parsed, str):
            raise ValueError(f"Expected a string value at {path}:{line_number}")
        trailing = value[end:].strip()
        if trailing and not trailing.startswith("#"):
            raise ValueError(f"Unexpected text after value at {path}:{line_number}")
        return parsed

    if value.startswith("'"):
        end = value.find("'", 1)
        if end < 0:
            raise ValueError(f"Invalid single-quoted value at {path}:{line_number}")
        trailing = value[end + 1 :].strip()
        if trailing and not trailing.startswith("#"):
            raise ValueError(f"Unexpected text after value at {path}:{line_number}")
        return value[1:end]

    # Treat a hash as an inline comment only when it is preceded by whitespace.
    value = re.split(r"\s+#", value, maxsplit=1)[0].rstrip()
    return value


def load_project_env(
    project_root: str | Path,
    *,
    filename: str = ".env",
    override: bool = False,
) -> list[str]:
    """Load root .env values and return key names loaded from the file.

    Existing process environment variables win unless ``override`` is true.
    Values are never printed or returned.
    """

    path = Path(project_root).expanduser().resolve() / filename
    if not path.is_file():
        return []

    loaded: list[str] = []
    for line_number, original in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(f"Expected KEY=VALUE at {path}:{line_number}")

        key, raw_value = line.split("=", 1)
        key = key.strip()
        if not ENV_KEY.fullmatch(key):
            raise ValueError(f"Invalid environment key at {path}:{line_number}")

        if override or key not in os.environ:
            os.environ[key] = _parse_value(raw_value, path=path, line_number=line_number)
            loaded.append(key)

    return loaded
