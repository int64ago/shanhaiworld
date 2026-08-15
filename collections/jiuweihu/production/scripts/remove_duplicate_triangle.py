#!/usr/bin/env python3
"""Remove one audited duplicate triangle from a GLB index accessor.

The Rodin original is never modified. The target triangle is replaced by the
last triangle and the accessor count is shortened by three indices, leaving
all buffer offsets and texture payloads unchanged.
"""

from __future__ import annotations

import argparse
import json
import struct
from collections import Counter
from pathlib import Path


JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
COMPONENTS = {5121: ("B", 1), 5123: ("H", 2), 5125: ("I", 4)}


def read_glb(path: Path) -> tuple[dict, bytearray]:
    payload = path.read_bytes()
    magic, version, declared = struct.unpack_from("<III", payload, 0)
    if magic != 0x46546C67 or version != 2 or declared != len(payload):
        raise ValueError("input is not a valid GLB 2.0 container")
    offset = 12
    document = None
    binary = None
    while offset < len(payload):
        length, kind = struct.unpack_from("<II", payload, offset)
        offset += 8
        chunk = payload[offset : offset + length]
        offset += length
        if kind == JSON_CHUNK:
            document = json.loads(chunk)
        elif kind == BIN_CHUNK:
            binary = bytearray(chunk)
    if document is None or binary is None:
        raise ValueError("GLB must contain JSON and BIN chunks")
    return document, binary


def accessor_layout(document: dict, accessor_index: int) -> tuple[dict, int, str, int]:
    accessor = document["accessors"][accessor_index]
    view = document["bufferViews"][accessor["bufferView"]]
    component_type = accessor["componentType"]
    if accessor["type"] != "SCALAR" or component_type not in COMPONENTS:
        raise ValueError("index accessor must be an unsigned scalar")
    fmt, width = COMPONENTS[component_type]
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride", width)
    if stride != width:
        raise ValueError("interleaved index buffers are not supported")
    return accessor, start, fmt, width


def read_indices(document: dict, binary: bytearray, accessor_index: int) -> list[int]:
    accessor, start, fmt, width = accessor_layout(document, accessor_index)
    return [
        struct.unpack_from("<" + fmt, binary, start + index * width)[0]
        for index in range(accessor["count"])
    ]


def write_glb(path: Path, document: dict, binary: bytearray) -> None:
    json_bytes = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((-len(json_bytes)) % 4)
    binary += b"\x00" * ((-len(binary)) % 4)
    total = 12 + 8 + len(json_bytes) + 8 + len(binary)
    output = bytearray(struct.pack("<III", 0x46546C67, 2, total))
    output += struct.pack("<II", len(json_bytes), JSON_CHUNK) + json_bytes
    output += struct.pack("<II", len(binary), BIN_CHUNK) + binary
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(output)


def read_positions(document: dict, binary: bytearray, accessor_index: int) -> list[tuple[float, float, float]]:
    accessor = document["accessors"][accessor_index]
    view = document["bufferViews"][accessor["bufferView"]]
    if accessor["componentType"] != 5126 or accessor["type"] != "VEC3":
        raise ValueError("POSITION accessor must be FLOAT VEC3")
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    stride = view.get("byteStride", 12)
    return [struct.unpack_from("<fff", binary, start + index * stride) for index in range(accessor["count"])]


def edge_counts(indices: list[int], positions: list[tuple[float, float, float]]) -> Counter[tuple[int, int]]:
    welded: dict[tuple[float, float, float], int] = {}
    vertex_ids = [
        welded.setdefault(tuple(round(value, 8) for value in position), len(welded))
        for position in positions
    ]
    counts: Counter[tuple[int, int]] = Counter()
    for offset in range(0, len(indices), 3):
        a, b, c = indices[offset : offset + 3]
        for left, right in ((a, b), (b, c), (c, a)):
            counts[tuple(sorted((vertex_ids[left], vertex_ids[right])))] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--triangle", required=True, type=int)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()

    document, binary = read_glb(args.input)
    primitive = document["meshes"][0]["primitives"][0]
    accessor_index = primitive["indices"]
    accessor, start, fmt, width = accessor_layout(document, accessor_index)
    indices = read_indices(document, binary, accessor_index)
    positions = read_positions(document, binary, primitive["attributes"]["POSITION"])
    if len(indices) % 3:
        raise ValueError("index count is not divisible by three")
    triangle_count = len(indices) // 3
    if not 0 <= args.triangle < triangle_count - 1:
        raise ValueError("target triangle must precede the final triangle")

    target_offset = args.triangle * 3
    removed = indices[target_offset : target_offset + 3]
    replacement = indices[-3:]
    before = edge_counts(indices, positions)
    for component, value in enumerate(replacement):
        struct.pack_into("<" + fmt, binary, start + (target_offset + component) * width, value)
    accessor["count"] -= 3
    cleaned = read_indices(document, binary, accessor_index)
    after = edge_counts(cleaned, positions)

    before_summary = {
        "boundary_edges": sum(count == 1 for count in before.values()),
        "nonmanifold_edges": sum(count > 2 for count in before.values()),
    }
    after_summary = {
        "boundary_edges": sum(count == 1 for count in after.values()),
        "nonmanifold_edges": sum(count > 2 for count in after.values()),
    }
    if before_summary != {"boundary_edges": 2, "nonmanifold_edges": 1}:
        raise ValueError(f"unexpected source topology: {before_summary}")
    if after_summary != {"boundary_edges": 0, "nonmanifold_edges": 0}:
        raise ValueError(f"cleanup did not produce a closed manifold: {after_summary}")

    write_glb(args.output, document, binary)
    report = {
        "schema_version": 1,
        "operation": "remove_duplicate_triangle",
        "source": str(args.input),
        "output": str(args.output),
        "primitive": 0,
        "index_accessor": accessor_index,
        "removed_triangle": args.triangle,
        "removed_indices": removed,
        "replacement_indices": replacement,
        "triangles_before": triangle_count,
        "triangles_after": len(cleaned) // 3,
        "topology_before": before_summary,
        "topology_after": after_summary,
        "anatomy_changed": False,
        "notes": [
            "The removed triangle duplicated an already two-sided edge and introduced two boundary edges plus one three-incident edge.",
            "The immutable Rodin source remains at models/raw-v4.glb. No component, appendage or anatomical region was deleted."
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
