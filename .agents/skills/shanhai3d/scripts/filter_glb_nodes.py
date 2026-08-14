#!/usr/bin/env python3
"""Disable selected GLB mesh nodes while preserving binary data for later pruning."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path


JSON_CHUNK = 0x4E4F534A


def read_chunks(path: Path) -> tuple[int, list[tuple[int, bytes]]]:
    chunks: list[tuple[int, bytes]] = []
    with path.open("rb") as stream:
        magic, version, declared = struct.unpack("<4sII", stream.read(12))
        if magic != b"glTF" or version != 2:
            raise RuntimeError("Expected a glTF 2.0 binary file")
        while stream.tell() < declared:
            length, chunk_type = struct.unpack("<II", stream.read(8))
            chunks.append((chunk_type, stream.read(length)))
    return version, chunks


def write_chunks(path: Path, version: int, chunks: list[tuple[int, bytes]]) -> None:
    total = 12 + sum(8 + len(data) for _, data in chunks)
    with path.open("wb") as stream:
        stream.write(struct.pack("<4sII", b"glTF", version, total))
        for chunk_type, data in chunks:
            stream.write(struct.pack("<II", len(data), chunk_type))
            stream.write(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--keep-nodes", nargs="+", required=True)
    args = parser.parse_args()

    source = Path(args.input).expanduser().resolve()
    destination = Path(args.output).expanduser().resolve()
    keep = set(args.keep_nodes)
    version, chunks = read_chunks(source)
    json_index = next(index for index, (kind, _) in enumerate(chunks) if kind == JSON_CHUNK)
    document = json.loads(chunks[json_index][1].decode("utf-8"))
    available = {node.get("name") for node in document.get("nodes", []) if node.get("mesh") is not None}
    missing = keep - available
    if missing:
        raise RuntimeError(f"Unknown mesh node names: {sorted(missing)}")

    disabled: list[str] = []
    for node in document.get("nodes", []):
        name = node.get("name")
        if node.get("mesh") is not None and name not in keep:
            node.pop("mesh", None)
            disabled.append(str(name))

    encoded = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded += b" " * ((4 - len(encoded) % 4) % 4)
    chunks[json_index] = (JSON_CHUNK, encoded)
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_chunks(destination, version, chunks)
    print(json.dumps({"kept": sorted(keep), "disabled": sorted(disabled)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
