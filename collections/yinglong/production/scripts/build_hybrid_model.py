#!/usr/bin/env python3
"""Build an auditable Yinglong hybrid GLB without a DCC application.

The script preserves the selected Rodin PBR mesh byte-for-byte inside the GLB,
adds physical layered feather plates, continuous branched horn trees, readable
eyes and belly scutes, and authors regional morph targets plus articulated-node
tracks.  It never deletes generated anatomy or splits components to correct
counts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import struct
import tempfile
from pathlib import Path
from typing import Any, Iterable, Sequence


EXPECTED_SOURCE_SHA256 = (
    "4d65e60deb47c59b1490370c222d337083e76ce4370eaaaba3fcc67b33112189"
)
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def smoothstep(low: float, high: float, value: float) -> float:
    if high == low:
        return 0.0
    t = clamp((value - low) / (high - low), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def add(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a: Sequence[float], scalar: float) -> tuple[float, float, float]:
    return (a[0] * scalar, a[1] * scalar, a[2] * scalar)


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length(a: Sequence[float]) -> float:
    return math.sqrt(dot(a, a))


def normalize(a: Sequence[float]) -> tuple[float, float, float]:
    magnitude = length(a)
    if magnitude < 1e-9:
        return (0.0, 0.0, 1.0)
    return mul(a, 1.0 / magnitude)


def quat_y(angle: float) -> list[float]:
    return [0.0, math.sin(angle * 0.5), 0.0, math.cos(angle * 0.5)]


def quat_z(angle: float) -> list[float]:
    return [0.0, 0.0, math.sin(angle * 0.5), math.cos(angle * 0.5)]


def rotate_x(
    point: Sequence[float], pivot: Sequence[float], angle: float
) -> tuple[float, float, float]:
    x, y, z = sub(point, pivot)
    cosine, sine = math.cos(angle), math.sin(angle)
    return add((x, y * cosine - z * sine, y * sine + z * cosine), pivot)


def rotate_y(
    point: Sequence[float], pivot: Sequence[float], angle: float
) -> tuple[float, float, float]:
    x, y, z = sub(point, pivot)
    cosine, sine = math.cos(angle), math.sin(angle)
    return add((x * cosine + z * sine, y, -x * sine + z * cosine), pivot)


def rotate_z(
    point: Sequence[float], pivot: Sequence[float], angle: float
) -> tuple[float, float, float]:
    x, y, z = sub(point, pivot)
    cosine, sine = math.cos(angle), math.sin(angle)
    return add((x * cosine - y * sine, x * sine + y * cosine, z), pivot)


def pad4(data: bytes, byte: bytes = b"\x00") -> bytes:
    return data + byte * ((-len(data)) % 4)


def load_glb(path: Path) -> tuple[dict[str, Any], bytearray]:
    data = path.read_bytes()
    if len(data) < 20:
        raise RuntimeError("Source GLB is truncated")
    magic, version, declared = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or declared != len(data):
        raise RuntimeError("Expected a complete glTF 2.0 binary")
    offset = 12
    chunks: list[tuple[int, bytes]] = []
    while offset < len(data):
        size, chunk_type = struct.unpack_from("<II", data, offset)
        offset += 8
        chunks.append((chunk_type, data[offset : offset + size]))
        offset += size
    if not chunks or chunks[0][0] != JSON_CHUNK:
        raise RuntimeError("GLB has no JSON chunk")
    document = json.loads(chunks[0][1].rstrip(b" \x00").decode("utf-8"))
    binary = next((chunk for kind, chunk in chunks if kind == BIN_CHUNK), b"")
    declared_binary = int(document.get("buffers", [{}])[0].get("byteLength", len(binary)))
    return document, bytearray(binary[:declared_binary])


def write_glb(path: Path, document: dict[str, Any], binary: bytearray) -> None:
    document["buffers"][0]["byteLength"] = len(binary)
    json_bytes = pad4(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        b" ",
    )
    binary_bytes = pad4(bytes(binary), b"\x00")
    total = 12 + 8 + len(json_bytes) + 8 + len(binary_bytes)
    payload = bytearray(struct.pack("<4sII", b"glTF", 2, total))
    payload.extend(struct.pack("<II", len(json_bytes), JSON_CHUNK))
    payload.extend(json_bytes)
    payload.extend(struct.pack("<II", len(binary_bytes), BIN_CHUNK))
    payload.extend(binary_bytes)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def transcode_embedded_textures(
    document: dict[str, Any], binary: bytearray
) -> bytearray:
    """Repack source views and replace 4K PNGs with 4K WebP payloads."""
    images = document.get("images", [])
    image_views = {
        int(image["bufferView"])
        for image in images
        if isinstance(image, dict) and isinstance(image.get("bufferView"), int)
    }
    source_binary = bytes(binary)
    repacked = bytearray()
    for index, view in enumerate(document.get("bufferViews", [])):
        if index in image_views:
            continue
        start = int(view.get("byteOffset", 0))
        end = start + int(view.get("byteLength", 0))
        while len(repacked) % 4:
            repacked.append(0)
        view["byteOffset"] = len(repacked)
        repacked.extend(source_binary[start:end])

    with tempfile.TemporaryDirectory(prefix="yinglong-webp-") as temporary:
        temporary_path = Path(temporary)
        for index, image in enumerate(images):
            view_index = int(image["bufferView"])
            view = document["bufferViews"][view_index]
            start = int(view.get("byteOffset", 0))
            length_value = int(view.get("byteLength", 0))
            # Image views have not been repacked, so recover offsets from the
            # immutable source document payload captured above.
            original_view = load_image_view(document, index, source_binary)
            png_path = temporary_path / f"texture-{index}.png"
            webp_path = temporary_path / f"texture-{index}.webp"
            png_path.write_bytes(original_view)
            name = str(image.get("name", "")).lower()
            quality = "92" if "diffuse" in name else "97"
            command = [
                "cwebp",
                "-quiet",
                "-m",
                "6",
                "-q",
                quality,
                "-exact",
                str(png_path),
                "-o",
                str(webp_path),
            ]
            if "diffuse" in name:
                command.insert(1, "-sharp_yuv")
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
            encoded = webp_path.read_bytes()
            while len(repacked) % 4:
                repacked.append(0)
            view["buffer"] = 0
            view["byteOffset"] = len(repacked)
            view["byteLength"] = len(encoded)
            view.pop("target", None)
            repacked.extend(encoded)
            image["mimeType"] = "image/webp"

    for texture in document.get("textures", []):
        source = texture.pop("source", None)
        if isinstance(source, int):
            texture.setdefault("extensions", {})["EXT_texture_webp"] = {
                "source": source
            }
    for key in ("extensionsUsed", "extensionsRequired"):
        values = document.setdefault(key, [])
        if "EXT_texture_webp" not in values:
            values.append("EXT_texture_webp")
    document.setdefault("extras", {}).setdefault("shanhaiworld", {})[
        "textureTranscode"
    ] = {
        "codec": "WebP",
        "resolution": "source 4K preserved",
        "diffuseQuality": 92,
        "normalAndOrmQuality": 97,
        "tool": "cwebp 1.6.0",
    }
    return repacked


def load_image_view(
    document: dict[str, Any], image_index: int, source_binary: bytes
) -> bytes:
    image = document["images"][image_index]
    view = document["bufferViews"][int(image["bufferView"])]
    # The original offset is preserved separately during the repack.
    original = view.get("extras", {}).get("sourceByteOffset")
    if original is None:
        original = view.get("byteOffset", 0)
    start = int(original)
    return source_binary[start : start + int(view.get("byteLength", 0))]


class Builder:
    def __init__(self, document: dict[str, Any], binary: bytearray) -> None:
        self.doc = document
        self.bin = binary
        for key in ("accessors", "bufferViews", "meshes", "nodes", "materials"):
            self.doc.setdefault(key, [])
        self.doc.setdefault("animations", [])

    def append_view(self, data: bytes, target: int | None = None) -> int:
        while len(self.bin) % 4:
            self.bin.append(0)
        offset = len(self.bin)
        self.bin.extend(data)
        view: dict[str, Any] = {
            "buffer": 0,
            "byteOffset": offset,
            "byteLength": len(data),
        }
        if target is not None:
            view["target"] = target
        self.doc["bufferViews"].append(view)
        return len(self.doc["bufferViews"]) - 1

    def append_accessor(
        self,
        data: bytes,
        *,
        component_type: int,
        count: int,
        value_type: str,
        target: int | None = None,
        minimum: Sequence[float] | None = None,
        maximum: Sequence[float] | None = None,
    ) -> int:
        view = self.append_view(data, target)
        accessor: dict[str, Any] = {
            "bufferView": view,
            "componentType": component_type,
            "count": count,
            "type": value_type,
        }
        if minimum is not None:
            accessor["min"] = list(minimum)
        if maximum is not None:
            accessor["max"] = list(maximum)
        self.doc["accessors"].append(accessor)
        return len(self.doc["accessors"]) - 1

    def float_accessor(
        self,
        values: Sequence[float],
        value_type: str,
        *,
        target: int | None = None,
        minimum: Sequence[float] | None = None,
        maximum: Sequence[float] | None = None,
    ) -> int:
        widths = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
        width = widths[value_type]
        if len(values) % width:
            raise RuntimeError(f"Invalid {value_type} value count")
        packed = struct.pack(f"<{len(values)}f", *values)
        return self.append_accessor(
            packed,
            component_type=5126,
            count=len(values) // width,
            value_type=value_type,
            target=target,
            minimum=minimum,
            maximum=maximum,
        )

    def add_material(
        self,
        name: str,
        color: Sequence[float],
        *,
        metallic: float,
        roughness: float,
        emissive: Sequence[float] | None = None,
        double_sided: bool = False,
    ) -> int:
        material: dict[str, Any] = {
            "name": name,
            "pbrMetallicRoughness": {
                "baseColorFactor": list(color),
                "metallicFactor": metallic,
                "roughnessFactor": roughness,
            },
            "doubleSided": double_sided,
        }
        if emissive:
            material["emissiveFactor"] = list(emissive)
        self.doc["materials"].append(material)
        return len(self.doc["materials"]) - 1

    def add_triangle_mesh(
        self,
        name: str,
        triangles: Sequence[tuple[Sequence[float], Sequence[float], Sequence[float]]],
        material: int,
    ) -> int:
        positions: list[float] = []
        normals: list[float] = []
        for a, b, c in triangles:
            normal = normalize(cross(sub(b, a), sub(c, a)))
            for point in (a, b, c):
                positions.extend(point)
                normals.extend(normal)
        triples = list(zip(positions[0::3], positions[1::3], positions[2::3]))
        position_accessor = self.float_accessor(
            positions,
            "VEC3",
            target=34962,
            minimum=[min(values) for values in zip(*triples)],
            maximum=[max(values) for values in zip(*triples)],
        )
        normal_accessor = self.float_accessor(normals, "VEC3", target=34962)
        self.doc["meshes"].append(
            {
                "name": name,
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": position_accessor,
                            "NORMAL": normal_accessor,
                        },
                        "material": material,
                        "mode": 4,
                    }
                ],
            }
        )
        return len(self.doc["meshes"]) - 1

    def add_node(self, **values: Any) -> int:
        self.doc["nodes"].append(values)
        return len(self.doc["nodes"]) - 1

    def add_animation_accessor(
        self, values: Sequence[float], value_type: str
    ) -> int:
        if value_type == "SCALAR":
            minimum = [min(values)] if values else [0.0]
            maximum = [max(values)] if values else [0.0]
        else:
            minimum = maximum = None
        return self.float_accessor(
            values,
            value_type,
            minimum=minimum,
            maximum=maximum,
        )


def read_float_accessor(
    document: dict[str, Any], binary: bytearray, index: int
) -> list[tuple[float, ...]]:
    accessor = document["accessors"][index]
    if accessor["componentType"] != 5126:
        raise RuntimeError("Only FLOAT accessors are supported by this builder")
    widths = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
    width = widths[accessor["type"]]
    view = document["bufferViews"][accessor["bufferView"]]
    stride = int(view.get("byteStride", width * 4))
    offset = int(view.get("byteOffset", 0)) + int(accessor.get("byteOffset", 0))
    output: list[tuple[float, ...]] = []
    for row in range(int(accessor["count"])):
        output.append(struct.unpack_from(f"<{width}f", binary, offset + row * stride))
    return output


def add_prism(
    triangles: list[tuple[Sequence[float], Sequence[float], Sequence[float]]],
    outline: Sequence[Sequence[float]],
    normal: Sequence[float],
    thickness: float,
) -> None:
    direction = normalize(normal)
    top = [add(point, mul(direction, thickness * 0.5)) for point in outline]
    bottom = [sub(point, mul(direction, thickness * 0.5)) for point in outline]
    for index in range(1, len(top) - 1):
        triangles.append((top[0], top[index], top[index + 1]))
        triangles.append((bottom[0], bottom[index + 1], bottom[index]))
    for index in range(len(outline)):
        nxt = (index + 1) % len(outline)
        triangles.append((top[index], bottom[index], bottom[nxt]))
        triangles.append((top[index], bottom[nxt], top[nxt]))


def feather_outline(
    anchor: Sequence[float],
    direction: Sequence[float],
    normal: Sequence[float],
    width: float,
    blade_length: float,
) -> list[tuple[float, float, float]]:
    d = normalize(direction)
    n = normalize(normal)
    tangent = normalize(cross(n, d))
    if length(tangent) < 1e-5:
        tangent = normalize(cross((0.0, 0.0, 1.0), d))
    base = sub(anchor, mul(d, blade_length * 0.34))
    shoulder = add(anchor, mul(d, blade_length * 0.22))
    tip = add(anchor, mul(d, blade_length * 0.68))
    return [
        add(base, mul(tangent, width * 0.34)),
        add(shoulder, mul(tangent, width * 0.52)),
        tip,
        sub(shoulder, mul(tangent, width * 0.52)),
        sub(base, mul(tangent, width * 0.34)),
    ]


def choose_wing_feathers(
    positions: Sequence[Sequence[float]],
    normals: Sequence[Sequence[float]],
    side: int,
    root: Sequence[float],
) -> tuple[
    list[tuple[Sequence[float], Sequence[float], Sequence[float]]],
    list[tuple[Sequence[float], Sequence[float], Sequence[float]]],
]:
    selected = [
        index
        for index, point in enumerate(positions)
        if side * point[0] > 0.135
        and point[1] > 0.035
        and -0.30 < point[2] < 0.56
    ]
    primary: list[tuple[Sequence[float], Sequence[float], Sequence[float]]] = []
    covert: list[tuple[Sequence[float], Sequence[float], Sequence[float]]] = []
    radial_min = 0.135
    radial_max = max(side * positions[index][0] for index in selected)
    depth_min = min(positions[index][2] for index in selected)
    depth_max = max(positions[index][2] for index in selected)
    radial_bins, depth_bins = 18, 18
    for radial_index in range(radial_bins):
        low_r = radial_min + (radial_max - radial_min) * radial_index / radial_bins
        high_r = radial_min + (radial_max - radial_min) * (radial_index + 1) / radial_bins
        for depth_index in range(depth_bins):
            low_depth = depth_min + (depth_max - depth_min) * depth_index / depth_bins
            high_depth = depth_min + (depth_max - depth_min) * (depth_index + 1) / depth_bins
            cell = [
                index
                for index in selected
                if low_r <= side * positions[index][0] < high_r
                and low_depth <= positions[index][2] < high_depth
            ]
            if len(cell) < 2:
                continue
            for facing in (-1, 1):
                index = max(cell, key=lambda item: facing * normals[item][2])
                point = positions[index]
                surface_normal = normalize(normals[index])
                if facing * surface_normal[2] < 0:
                    surface_normal = mul(surface_normal, -1.0)
                local_point = sub(point, root)
                local_direction = sub(point, root)
                radial_t = smoothstep(radial_min, radial_max, side * point[0])
                blade_length = 0.058 + 0.072 * radial_t
                width = 0.013 + 0.010 * (1.0 - radial_t)
                anchor = add(local_point, mul(surface_normal, 0.0035))
                outline = feather_outline(
                    anchor, local_direction, surface_normal, width, blade_length
                )
                destination = primary if radial_t > 0.58 else covert
                add_prism(destination, outline, surface_normal, 0.0028)
    return primary, covert


def cylinder_between(
    triangles: list[tuple[Sequence[float], Sequence[float], Sequence[float]]],
    start: Sequence[float],
    end: Sequence[float],
    radius_start: float,
    radius_end: float,
    sides: int = 12,
) -> None:
    axis = normalize(sub(end, start))
    helper = (0.0, 0.0, 1.0) if abs(axis[2]) < 0.86 else (0.0, 1.0, 0.0)
    tangent = normalize(cross(axis, helper))
    bitangent = normalize(cross(axis, tangent))
    start_ring: list[tuple[float, float, float]] = []
    end_ring: list[tuple[float, float, float]] = []
    for index in range(sides):
        angle = math.tau * index / sides
        radial = add(mul(tangent, math.cos(angle)), mul(bitangent, math.sin(angle)))
        start_ring.append(add(start, mul(radial, radius_start)))
        end_ring.append(add(end, mul(radial, radius_end)))
    for index in range(sides):
        nxt = (index + 1) % sides
        triangles.append((start_ring[index], end_ring[index], end_ring[nxt]))
        triangles.append((start_ring[index], end_ring[nxt], start_ring[nxt]))
    for index in range(1, sides - 1):
        triangles.append((start, start_ring[index + 1], start_ring[index]))
        triangles.append((end, end_ring[index], end_ring[index + 1]))


def add_tube_path(
    triangles: list[tuple[Sequence[float], Sequence[float], Sequence[float]]],
    points: Sequence[Sequence[float]],
    start_radius: float,
    end_radius: float,
) -> None:
    for index in range(len(points) - 1):
        t0 = index / max(1, len(points) - 1)
        t1 = (index + 1) / max(1, len(points) - 1)
        radius0 = start_radius * (1.0 - t0) + end_radius * t0
        radius1 = start_radius * (1.0 - t1) + end_radius * t1
        cylinder_between(triangles, points[index], points[index + 1], radius0, radius1)


def build_horn(side: int) -> list[tuple[Sequence[float], Sequence[float], Sequence[float]]]:
    s = float(side)
    triangles: list[tuple[Sequence[float], Sequence[float], Sequence[float]]] = []
    main = [
        (0.0, 0.0, 0.0),
        (s * 0.014, 0.041, -0.012),
        (s * 0.036, 0.078, -0.036),
        (s * 0.062, 0.111, -0.066),
        (s * 0.086, 0.135, -0.096),
    ]
    branch_a = [main[1], (s * 0.040, 0.072, 0.004), (s * 0.057, 0.094, 0.018)]
    branch_b = [main[2], (s * 0.069, 0.110, -0.006), (s * 0.088, 0.133, 0.006)]
    branch_c = [main[3], (s * 0.096, 0.142, -0.040), (s * 0.113, 0.163, -0.030)]
    add_tube_path(triangles, main, 0.010, 0.003)
    add_tube_path(triangles, branch_a, 0.006, 0.0018)
    add_tube_path(triangles, branch_b, 0.0055, 0.0017)
    add_tube_path(triangles, branch_c, 0.0045, 0.0015)
    return triangles


def uv_sphere(
    radii: Sequence[float], segments: int = 18, rings: int = 10
) -> list[tuple[Sequence[float], Sequence[float], Sequence[float]]]:
    vertices: list[tuple[float, float, float]] = []
    for ring in range(rings + 1):
        phi = math.pi * ring / rings
        for segment in range(segments + 1):
            theta = math.tau * segment / segments
            vertices.append(
                (
                    radii[0] * math.sin(phi) * math.cos(theta),
                    radii[1] * math.sin(phi) * math.sin(theta),
                    radii[2] * math.cos(phi),
                )
            )
    triangles: list[tuple[Sequence[float], Sequence[float], Sequence[float]]] = []
    for ring in range(rings):
        for segment in range(segments):
            a = ring * (segments + 1) + segment
            b = a + segments + 1
            triangles.append((vertices[a], vertices[b], vertices[a + 1]))
            triangles.append((vertices[a + 1], vertices[b], vertices[b + 1]))
    return triangles


def build_scutes(
    positions: Sequence[Sequence[float]],
) -> list[tuple[Sequence[float], Sequence[float], Sequence[float]]]:
    triangles: list[tuple[Sequence[float], Sequence[float], Sequence[float]]] = []
    for index in range(13):
        z = 0.03 + index * 0.041
        band = [
            point
            for point in positions
            if abs(point[0]) < 0.17 and abs(point[2] - z) < 0.024
        ]
        if not band:
            continue
        y = max(point[1] for point in band) + 0.005
        half_width = 0.102 - 0.022 * smoothstep(0.38, 0.56, z)
        half_height = 0.022
        outline = [
            (-half_width, y, z),
            (-half_width * 0.74, y + 0.004, z + half_height),
            (half_width * 0.74, y + 0.004, z + half_height),
            (half_width, y, z),
            (half_width * 0.66, y + 0.003, z - half_height),
            (-half_width * 0.66, y + 0.003, z - half_height),
        ]
        add_prism(triangles, outline, (0.0, 1.0, 0.0), 0.005)
    return triangles


def build_cheek_scales(
    side: int,
) -> list[tuple[Sequence[float], Sequence[float], Sequence[float]]]:
    s = float(side)
    triangles: list[tuple[Sequence[float], Sequence[float], Sequence[float]]] = []
    for row in range(3):
        for column in range(4):
            center = (
                s * (0.052 + column * 0.021),
                0.491 - row * 0.015,
                0.530 - row * 0.032 + column * 0.004,
            )
            width = 0.015
            height = 0.019
            outline = [
                add(center, (0.0, 0.0, height)),
                add(center, (s * width, 0.0, 0.0)),
                add(center, (0.0, 0.0, -height)),
                add(center, (-s * width, 0.0, 0.0)),
            ]
            add_prism(triangles, outline, (s * 0.44, 0.88, 0.16), 0.004)
    return triangles


def morph_deltas(
    positions: Sequence[Sequence[float]],
) -> tuple[list[str], list[list[tuple[float, float, float]]]]:
    names = [
        "ChestBreath",
        "NeckLift",
        "NeckStrike",
        "TailLeft",
        "TailRight",
        "WingLift",
        "StrideA",
        "StrideB",
        "RainBow",
    ]
    targets = [[] for _ in names]
    for point in positions:
        x, y, z = point
        chest = (
            (1.0 - smoothstep(0.22, 0.34, abs(x)))
            * smoothstep(-0.10, 0.04, y)
            * (1.0 - smoothstep(0.34, 0.49, y))
            * smoothstep(-0.05, 0.22, z)
        )
        targets[0].append((x * 0.032 * chest, 0.006 * chest, 0.014 * chest))

        neck = (
            (1.0 - smoothstep(0.22, 0.31, abs(x)))
            * smoothstep(0.24, 0.58, z)
            * smoothstep(0.00, 0.23, y)
        )
        lifted = rotate_x(point, (0.0, 0.12, 0.25), math.radians(-8.0))
        strike = add(
            rotate_x(point, (0.0, 0.13, 0.28), math.radians(10.0)),
            (0.0, -0.004 * neck, 0.045 * neck),
        )
        targets[1].append(mul(sub(lifted, point), neck))
        targets[2].append(mul(sub(strike, point), neck))

        tail = (
            (1.0 - smoothstep(0.12, 0.20, abs(x)))
            * (1.0 - smoothstep(-0.20, 0.00, z))
        )
        tail_strength = tail * smoothstep(-0.05, -0.82, z)
        targets[3].append((0.092 * tail_strength, 0.010 * tail_strength, 0.0))
        targets[4].append((-0.092 * tail_strength, 0.006 * tail_strength, 0.0))

        wing = smoothstep(0.135, 0.22, abs(x)) * smoothstep(0.02, 0.16, y)
        side = 1.0 if x >= 0.0 else -1.0
        winged = rotate_z(point, (side * 0.12, 0.14, 0.15), side * math.radians(11.5))
        targets[5].append(mul(sub(winged, point), wing))

        leg = smoothstep(0.09, 0.17, abs(x)) * (1.0 - smoothstep(-0.20, -0.06, y))
        phase = 1.0 if x * z >= 0.0 else -1.0
        stride = 0.055 * leg * phase
        targets[6].append((0.0, 0.018 * leg * (1.0 - phase) * 0.5, stride))
        targets[7].append((0.0, 0.018 * leg * (1.0 + phase) * 0.5, -stride))

        bow_region = (
            (1.0 - smoothstep(0.25, 0.38, abs(x)))
            * smoothstep(-0.48, -0.20, z)
            * (1.0 - smoothstep(0.58, 0.76, z))
            * smoothstep(-0.10, 0.08, y)
        )
        targets[8].append((0.028 * math.sin((z + 0.2) * 5.5) * bow_region, -0.018 * bow_region, 0.0))
    return names, targets


def flattened(values: Iterable[Sequence[float]]) -> list[float]:
    return [component for value in values for component in value]


def add_animation(
    builder: Builder,
    *,
    name: str,
    times: Sequence[float],
    weight_frames: Sequence[Sequence[float]],
    model_node: int,
    wing_left: int,
    wing_right: int,
    eye_left: int,
    eye_right: int,
    wing_angles: Sequence[float],
    blink_frames: Sequence[float] | None = None,
) -> None:
    input_accessor = builder.add_animation_accessor(list(times), "SCALAR")
    weight_accessor = builder.add_animation_accessor(flattened(weight_frames), "SCALAR")
    left_rotations = [quat_z(-angle) for angle in wing_angles]
    right_rotations = [quat_z(angle) for angle in wing_angles]
    left_rotation_accessor = builder.add_animation_accessor(
        flattened(left_rotations), "VEC4"
    )
    right_rotation_accessor = builder.add_animation_accessor(
        flattened(right_rotations), "VEC4"
    )
    samplers: list[dict[str, Any]] = [
        {"input": input_accessor, "output": weight_accessor, "interpolation": "LINEAR"},
        {
            "input": input_accessor,
            "output": left_rotation_accessor,
            "interpolation": "LINEAR",
        },
        {
            "input": input_accessor,
            "output": right_rotation_accessor,
            "interpolation": "LINEAR",
        },
    ]
    channels: list[dict[str, Any]] = [
        {"sampler": 0, "target": {"node": model_node, "path": "weights"}},
        {"sampler": 1, "target": {"node": wing_left, "path": "rotation"}},
        {"sampler": 2, "target": {"node": wing_right, "path": "rotation"}},
    ]
    if blink_frames is not None:
        scales = [(1.0, max(0.12, value), 1.0) for value in blink_frames]
        scale_accessor = builder.add_animation_accessor(flattened(scales), "VEC3")
        samplers.append(
            {"input": input_accessor, "output": scale_accessor, "interpolation": "LINEAR"}
        )
        channels.extend(
            [
                {"sampler": 3, "target": {"node": eye_left, "path": "scale"}},
                {"sampler": 3, "target": {"node": eye_right, "path": "scale"}},
            ]
        )
    builder.doc["animations"].append(
        {"name": name, "samplers": samplers, "channels": channels}
    )


def build(source: Path, output: Path, *, web_textures: bool = False) -> dict[str, Any]:
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if source_digest != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(
            f"Unexpected Rodin source SHA-256: {source_digest}; expected {EXPECTED_SOURCE_SHA256}"
        )
    document, binary = load_glb(source)
    if web_textures:
        binary = transcode_embedded_textures(document, binary)
    builder = Builder(document, binary)
    primitive = document["meshes"][0]["primitives"][0]
    position_accessor_index = primitive["attributes"]["POSITION"]
    normal_accessor_index = primitive["attributes"]["NORMAL"]
    positions = read_float_accessor(document, binary, position_accessor_index)
    normals = read_float_accessor(document, binary, normal_accessor_index)

    feather_primary_material = builder.add_material(
        "Indigo primary feathers",
        (0.030, 0.060, 0.105, 1.0),
        metallic=0.08,
        roughness=0.58,
        double_sided=True,
    )
    feather_covert_material = builder.add_material(
        "Blue-green covert feathers",
        (0.050, 0.105, 0.125, 1.0),
        metallic=0.12,
        roughness=0.62,
        double_sided=True,
    )
    ivory_material = builder.add_material(
        "Aged ivory horn branches",
        (0.44, 0.36, 0.24, 1.0),
        metallic=0.02,
        roughness=0.54,
    )
    eye_material = builder.add_material(
        "Rain amber eyes",
        (0.30, 0.16, 0.035, 1.0),
        metallic=0.08,
        roughness=0.24,
        emissive=(0.12, 0.055, 0.008),
    )

    enhancement_children: list[int] = []
    wing_nodes: dict[int, int] = {}
    for side, label in ((-1, "L"), (1, "R")):
        root = (side * 0.12, 0.14, 0.15)
        primary, covert = choose_wing_feathers(positions, normals, side, root)
        primary_mesh = builder.add_triangle_mesh(
            f"WingPrimary_{label}", primary, feather_primary_material
        )
        covert_mesh = builder.add_triangle_mesh(
            f"WingCoverts_{label}", covert, feather_covert_material
        )
        primary_node = builder.add_node(name=f"WingPrimary_{label}", mesh=primary_mesh)
        covert_node = builder.add_node(name=f"WingCoverts_{label}", mesh=covert_mesh)
        parent = builder.add_node(
            name=f"WingFeathers_{label}",
            translation=list(root),
            children=[primary_node, covert_node],
        )
        wing_nodes[side] = parent
        enhancement_children.append(parent)

    for side, label in ((-1, "L"), (1, "R")):
        horn_mesh = builder.add_triangle_mesh(
            f"HornTree_{label}", build_horn(side), ivory_material
        )
        horn_node = builder.add_node(
            name=f"HornTree_{label}",
            mesh=horn_mesh,
            translation=[side * 0.040, 0.350, 0.700],
        )
        enhancement_children.append(horn_node)

    eye_mesh = builder.add_triangle_mesh(
        "EyeGem", uv_sphere((0.005, 0.005, 0.004)), eye_material
    )
    eye_nodes: dict[int, int] = {}
    for side, label in ((-1, "L"), (1, "R")):
        eye = builder.add_node(
            name=f"Eye_{label}",
            mesh=eye_mesh,
            translation=[side * 0.052, 0.260, 0.800],
        )
        eye_nodes[side] = eye
        enhancement_children.append(eye)

    enhancement_root = builder.add_node(
        name="YinglongEnhancements", children=enhancement_children
    )
    document["scenes"][document.get("scene", 0)].setdefault("nodes", []).append(
        enhancement_root
    )

    target_names, targets = morph_deltas(positions)
    primitive["targets"] = []
    for target in targets:
        values = flattened(target)
        target_triples = list(zip(values[0::3], values[1::3], values[2::3]))
        accessor = builder.float_accessor(
            values,
            "VEC3",
            target=34962,
            minimum=[min(components) for components in zip(*target_triples)],
            maximum=[max(components) for components in zip(*target_triples)],
        )
        primitive["targets"].append({"POSITION": accessor})
    document["meshes"][0]["weights"] = [0.0] * len(target_names)
    document["meshes"][0].setdefault("extras", {})["targetNames"] = target_names

    zero = [0.0] * len(target_names)

    def frame(**weights: float) -> list[float]:
        values = list(zero)
        for key, value in weights.items():
            values[target_names.index(key)] = value
        return values

    add_animation(
        builder,
        name="Idle",
        times=[0.0, 1.0, 2.0, 3.0, 4.0],
        weight_frames=[
            frame(ChestBreath=0.15, TailLeft=0.08),
            frame(ChestBreath=0.75, NeckLift=0.12, TailLeft=0.18),
            frame(ChestBreath=0.20, TailRight=0.10),
            frame(ChestBreath=0.70, NeckLift=0.08, TailRight=0.18),
            frame(ChestBreath=0.15, TailLeft=0.08),
        ],
        model_node=0,
        wing_left=wing_nodes[-1],
        wing_right=wing_nodes[1],
        eye_left=eye_nodes[-1],
        eye_right=eye_nodes[1],
        wing_angles=[0.00, 0.025, 0.00, -0.022, 0.00],
        blink_frames=[1.0, 1.0, 0.16, 1.0, 1.0],
    )
    add_animation(
        builder,
        name="Walk",
        times=[0.0, 0.6, 1.2, 1.8, 2.4],
        weight_frames=[
            frame(StrideA=0.15, TailLeft=0.25, ChestBreath=0.20),
            frame(StrideA=0.95, TailRight=0.18, RainBow=0.18),
            frame(StrideB=0.15, TailRight=0.25, ChestBreath=0.20),
            frame(StrideB=0.95, TailLeft=0.18, RainBow=0.18),
            frame(StrideA=0.15, TailLeft=0.25, ChestBreath=0.20),
        ],
        model_node=0,
        wing_left=wing_nodes[-1],
        wing_right=wing_nodes[1],
        eye_left=eye_nodes[-1],
        eye_right=eye_nodes[1],
        wing_angles=[0.02, 0.06, 0.02, -0.04, 0.02],
    )
    add_animation(
        builder,
        name="Flight",
        times=[0.0, 0.75, 1.5, 2.25, 3.0],
        weight_frames=[
            frame(WingLift=0.15, NeckLift=0.35, TailLeft=0.20),
            frame(WingLift=1.0, ChestBreath=0.45, TailRight=0.30),
            frame(WingLift=0.20, RainBow=0.25, TailRight=0.12),
            frame(WingLift=0.85, ChestBreath=0.40, TailLeft=0.30),
            frame(WingLift=0.15, NeckLift=0.35, TailLeft=0.20),
        ],
        model_node=0,
        wing_left=wing_nodes[-1],
        wing_right=wing_nodes[1],
        eye_left=eye_nodes[-1],
        eye_right=eye_nodes[1],
        wing_angles=[0.02, -0.18, 0.06, -0.15, 0.02],
    )
    add_animation(
        builder,
        name="Observe",
        times=[0.0, 0.45, 1.25, 2.05, 2.6],
        weight_frames=[
            frame(ChestBreath=0.20),
            frame(NeckLift=0.55, TailLeft=0.18),
            frame(NeckLift=1.0, TailRight=0.25, ChestBreath=0.35),
            frame(NeckLift=0.45, TailLeft=0.18),
            frame(ChestBreath=0.20),
        ],
        model_node=0,
        wing_left=wing_nodes[-1],
        wing_right=wing_nodes[1],
        eye_left=eye_nodes[-1],
        eye_right=eye_nodes[1],
        wing_angles=[0.0, 0.05, 0.08, 0.03, 0.0],
        blink_frames=[1.0, 0.18, 1.0, 0.18, 1.0],
    )
    add_animation(
        builder,
        name="RainCall",
        times=[0.0, 0.55, 1.35, 2.25, 3.1, 3.6],
        weight_frames=[
            frame(ChestBreath=0.20, RainBow=0.10),
            frame(NeckLift=0.65, WingLift=0.35, ChestBreath=0.55),
            frame(NeckLift=1.0, WingLift=0.95, RainBow=0.85, TailLeft=0.40),
            frame(NeckLift=0.75, WingLift=0.55, TailRight=0.45, ChestBreath=0.80),
            frame(NeckLift=0.40, WingLift=0.25, RainBow=0.30),
            frame(ChestBreath=0.20, RainBow=0.10),
        ],
        model_node=0,
        wing_left=wing_nodes[-1],
        wing_right=wing_nodes[1],
        eye_left=eye_nodes[-1],
        eye_right=eye_nodes[1],
        wing_angles=[0.0, -0.12, -0.28, -0.18, -0.06, 0.0],
    )
    add_animation(
        builder,
        name="Strike",
        times=[0.0, 0.35, 0.72, 1.10, 1.65, 2.2],
        weight_frames=[
            frame(ChestBreath=0.20),
            frame(RainBow=0.55, StrideA=0.35, NeckLift=0.25),
            frame(NeckStrike=1.0, WingLift=0.45, TailLeft=0.65),
            frame(NeckStrike=0.72, StrideB=0.45, TailRight=0.40),
            frame(NeckLift=0.20, ChestBreath=0.45),
            frame(ChestBreath=0.20),
        ],
        model_node=0,
        wing_left=wing_nodes[-1],
        wing_right=wing_nodes[1],
        eye_left=eye_nodes[-1],
        eye_right=eye_nodes[1],
        wing_angles=[0.0, 0.12, -0.10, 0.08, 0.03, 0.0],
    )
    add_animation(
        builder,
        name="WingGuard",
        times=[0.0, 0.45, 1.15, 1.85, 2.4, 2.8],
        weight_frames=[
            frame(ChestBreath=0.20),
            frame(RainBow=0.55, WingLift=0.25, TailRight=0.30),
            frame(RainBow=1.0, WingLift=0.70, StrideA=0.35, TailLeft=0.45),
            frame(RainBow=0.75, WingLift=0.55, StrideB=0.30, TailRight=0.35),
            frame(RainBow=0.25, ChestBreath=0.40),
            frame(ChestBreath=0.20),
        ],
        model_node=0,
        wing_left=wing_nodes[-1],
        wing_right=wing_nodes[1],
        eye_left=eye_nodes[-1],
        eye_right=eye_nodes[1],
        wing_angles=[0.0, 0.16, 0.32, 0.24, 0.08, 0.0],
        blink_frames=[1.0, 1.0, 0.22, 1.0, 1.0, 1.0],
    )

    document.setdefault("asset", {})["generator"] = (
        "Shanhaiworld deterministic Yinglong hybrid builder v1"
    )
    document.setdefault("extras", {}).setdefault("shanhaiworld", {}).update({
        "creature": "yinglong",
        "motionMode": "hybrid",
        "sourceSha256": source_digest,
        "modelingRoute": "Rodin base plus procedural geometry and regional morphs",
        "morphTargets": target_names,
        "actions": [animation["name"] for animation in document["animations"]],
    })
    write_glb(output, document, builder.bin)
    return {
        "source": str(source),
        "source_sha256": source_digest,
        "output": str(output),
        "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "bytes": output.stat().st_size,
        "feather_triangles": sum(
            int(
                document["accessors"][
                    primitive["attributes"]["POSITION"]
                ]["count"]
            )
            // 3
            for mesh in document["meshes"]
            if str(mesh.get("name", "")).startswith("Wing")
            for primitive in mesh.get("primitives", [])
        ),
        "morph_targets": target_names,
        "animations": [animation["name"] for animation in document["animations"]],
        "web_textures": web_textures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--web-textures",
        action="store_true",
        help="Preserve source 4K dimensions while transcoding embedded PNGs to WebP",
    )
    args = parser.parse_args()
    report = build(
        Path(args.source).resolve(),
        Path(args.output).resolve(),
        web_textures=args.web_textures,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
