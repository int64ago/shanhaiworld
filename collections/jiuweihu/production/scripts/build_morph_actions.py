#!/usr/bin/env python3
"""Build deterministic semantic morph actions for the Nine-Tailed Fox.

This is the audited fallback after Tripo's generic quadruped walk visibly
misclassified low tail chains. It preserves the accepted mesh and PBR payload,
derives four leg regions from welded surface geodesics, and adds localized head,
spine, leg and continuous nine-tail deformation fields as GLB morph targets.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import struct
from pathlib import Path


JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
COMPONENTS = {5121: ("B", 1), 5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
TYPES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def read_glb(path: Path) -> tuple[dict, bytearray]:
    payload = path.read_bytes()
    magic, version, declared = struct.unpack_from("<III", payload, 0)
    if magic != 0x46546C67 or version != 2 or declared != len(payload):
        raise ValueError("input is not a valid GLB 2.0 container")
    document = None
    binary = None
    offset = 12
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
        raise ValueError("GLB requires JSON and BIN chunks")
    return document, binary


def read_accessor(document: dict, binary: bytearray, index: int) -> list[tuple[float, ...]]:
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    fmt, width = COMPONENTS[accessor["componentType"]]
    components = TYPES[accessor["type"]]
    packed = "<" + fmt * components
    size = width * components
    stride = view.get("byteStride", size)
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return [struct.unpack_from(packed, binary, start + item * stride) for item in range(accessor["count"])]


def append_accessor(
    document: dict,
    binary: bytearray,
    values: list[float],
    accessor_type: str,
    *,
    target: int | None = None,
    include_bounds: bool = False,
) -> int:
    while len(binary) % 4:
        binary.append(0)
    byte_offset = len(binary)
    binary.extend(struct.pack("<" + "f" * len(values), *values))
    view: dict[str, int] = {"buffer": 0, "byteOffset": byte_offset, "byteLength": len(values) * 4}
    if target is not None:
        view["target"] = target
    document.setdefault("bufferViews", []).append(view)
    view_index = len(document["bufferViews"]) - 1
    components = TYPES[accessor_type]
    count = len(values) // components
    accessor: dict[str, object] = {
        "bufferView": view_index,
        "componentType": 5126,
        "count": count,
        "type": accessor_type,
    }
    if include_bounds:
        grouped = [values[item : item + components] for item in range(0, len(values), components)]
        accessor["min"] = [min(group[axis] for group in grouped) for axis in range(components)]
        accessor["max"] = [max(group[axis] for group in grouped) for axis in range(components)]
    document.setdefault("accessors", []).append(accessor)
    return len(document["accessors"]) - 1


def write_glb(path: Path, document: dict, binary: bytearray) -> None:
    document["buffers"][0]["byteLength"] = len(binary)
    json_bytes = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    json_bytes += b" " * ((-len(json_bytes)) % 4)
    padded_binary = bytearray(binary)
    padded_binary += b"\x00" * ((-len(padded_binary)) % 4)
    total = 12 + 8 + len(json_bytes) + 8 + len(padded_binary)
    output = bytearray(struct.pack("<III", 0x46546C67, 2, total))
    output += struct.pack("<II", len(json_bytes), JSON_CHUNK) + json_bytes
    output += struct.pack("<II", len(padded_binary), BIN_CHUNK) + padded_binary
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(output)


def distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a[axis] - b[axis]) ** 2 for axis in range(3)))


def smoothstep(edge0: float, edge1: float, value: float) -> float:
    if edge0 == edge1:
        return float(value >= edge1)
    amount = max(0.0, min(1.0, (value - edge0) / (edge1 - edge0)))
    return amount * amount * (3.0 - 2.0 * amount)


def welded_graph(
    positions: list[tuple[float, float, float]], indices: list[int]
) -> tuple[list[int], list[tuple[float, float, float]], list[dict[int, float]]]:
    weld_map: dict[tuple[float, float, float], int] = {}
    raw_to_weld: list[int] = []
    welded_positions: list[tuple[float, float, float]] = []
    for position in positions:
        key = tuple(round(value, 8) for value in position)
        if key not in weld_map:
            weld_map[key] = len(welded_positions)
            welded_positions.append(position)
        raw_to_weld.append(weld_map[key])
    adjacency: list[dict[int, float]] = [dict() for _ in welded_positions]
    for offset in range(0, len(indices), 3):
        triangle = [raw_to_weld[index] for index in indices[offset : offset + 3]]
        for left, right in ((triangle[0], triangle[1]), (triangle[1], triangle[2]), (triangle[2], triangle[0])):
            if left == right:
                continue
            length = distance(welded_positions[left], welded_positions[right])
            old = adjacency[left].get(right)
            if old is None or length < old:
                adjacency[left][right] = length
                adjacency[right][left] = length
    return raw_to_weld, welded_positions, adjacency


def choose_seed(
    positions: list[tuple[float, float, float]], *, side: float, front: bool
) -> int:
    target = (side * 0.055, 0.006, 0.315 if front else -0.315)
    candidates = [
        (distance(position, target), index)
        for index, position in enumerate(positions)
        if position[1] < 0.045
        and (position[0] * side) > 0
        and (position[2] > 0.16 if front else position[2] < -0.16)
    ]
    if not candidates:
        raise ValueError(f"could not find {'front' if front else 'rear'} paw seed on side {side}")
    return min(candidates)[1]


def geodesic_mask(
    seed: int, adjacency: list[dict[int, float]], *, full_distance: float = 0.24, max_distance: float = 0.39
) -> list[float]:
    distances = [math.inf] * len(adjacency)
    distances[seed] = 0.0
    queue: list[tuple[float, int]] = [(0.0, seed)]
    while queue:
        current, node = heapq.heappop(queue)
        if current != distances[node] or current > max_distance:
            continue
        for neighbor, edge in adjacency[node].items():
            candidate = current + edge
            if candidate < distances[neighbor] and candidate <= max_distance:
                distances[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))
    return [
        1.0 if value <= full_distance else 1.0 - smoothstep(full_distance, max_distance, value)
        if value <= max_distance
        else 0.0
        for value in distances
    ]


def rotate_x(position: tuple[float, float, float], pivot: tuple[float, float, float], angle: float) -> tuple[float, float, float]:
    x, y, z = position
    px, py, pz = pivot
    cosine, sine = math.cos(angle), math.sin(angle)
    return (x, py + cosine * (y - py) - sine * (z - pz), pz + sine * (y - py) + cosine * (z - pz))


def rotate_y(position: tuple[float, float, float], pivot: tuple[float, float, float], angle: float) -> tuple[float, float, float]:
    x, y, z = position
    px, py, pz = pivot
    cosine, sine = math.cos(angle), math.sin(angle)
    return (px + cosine * (x - px) + sine * (z - pz), y, pz - sine * (x - px) + cosine * (z - pz))


def make_targets(
    positions: list[tuple[float, float, float]],
    raw_to_weld: list[int],
    leg_masks: dict[str, list[float]],
) -> dict[str, list[tuple[float, float, float]]]:
    target_names = [
        "tail_left", "tail_right", "tail_lift", "tail_flare",
        "head_left", "head_right", "head_down", "head_up",
        "crouch", "arch", "gait_a", "gait_b", "surge",
        "pounce_extend", "lean_left", "lean_right",
    ]
    outputs = {name: [] for name in target_names}
    tail_pivot = (0.0, 0.25, -0.18)
    head_pivot = (0.0, 0.28, 0.16)
    leg_specs = {
        "front_left": ((-0.052, 0.245, 0.275), 1.0),
        "front_right": ((0.052, 0.245, 0.275), -1.0),
        "rear_left": ((-0.052, 0.225, -0.245), -1.0),
        "rear_right": ((0.052, 0.225, -0.245), 1.0),
    }
    for raw_index, original in enumerate(positions):
        welded = raw_to_weld[raw_index]
        front_mask = max(leg_masks["front_left"][welded], leg_masks["front_right"][welded])
        rear_mask = max(leg_masks["rear_left"][welded], leg_masks["rear_right"][welded])
        tail_weight = smoothstep(-0.17, -0.43, original[2]) * (1.0 - rear_mask)
        head_weight = smoothstep(0.14, 0.34, original[2]) * (1.0 - front_mask)
        body_weight = smoothstep(0.035, 0.25, original[1])

        transformed = rotate_y(original, tail_pivot, math.radians(14.0) * tail_weight)
        outputs["tail_left"].append(transformed)
        transformed = rotate_y(original, tail_pivot, math.radians(-14.0) * tail_weight)
        outputs["tail_right"].append(transformed)
        transformed = rotate_x(original, tail_pivot, math.radians(17.0) * tail_weight)
        outputs["tail_lift"].append(transformed)
        x, y, z = original
        outputs["tail_flare"].append((x * (1.0 + 0.32 * tail_weight), y + 0.055 * tail_weight, z))

        outputs["head_left"].append(rotate_y(original, head_pivot, math.radians(25.0) * head_weight))
        outputs["head_right"].append(rotate_y(original, head_pivot, math.radians(-25.0) * head_weight))
        outputs["head_down"].append(rotate_x(original, head_pivot, math.radians(-18.0) * head_weight))
        outputs["head_up"].append(rotate_x(original, head_pivot, math.radians(16.0) * head_weight))
        outputs["crouch"].append((x, y - 0.075 * body_weight, z))
        outputs["arch"].append((x, y + 0.055 * body_weight, z))
        surge_weight = smoothstep(0.02, 0.34, z) * body_weight
        outputs["surge"].append((x, y + 0.020 * surge_weight, z + 0.115 * surge_weight))
        planted_weight = max(front_mask, rear_mask)
        lean_weight = body_weight * (1.0 - 0.75 * planted_weight)
        outputs["lean_left"].append((x - 0.055 * lean_weight, y, z))
        outputs["lean_right"].append((x + 0.055 * lean_weight, y, z))

        gait_points: dict[str, tuple[float, float, float]] = {}
        for gait_name, phase in (("gait_a", 1.0), ("gait_b", -1.0)):
            delta_x = delta_y = delta_z = 0.0
            for leg_name, (pivot, direction) in leg_specs.items():
                mask = leg_masks[leg_name][welded]
                is_rear = leg_name.startswith("rear")
                if is_rear:
                    right_share = smoothstep(-0.018, 0.018, original[0])
                    side_share = right_share if leg_name.endswith("right") else 1.0 - right_share
                    # The provider mesh connects both rear paws through a short
                    # underside surface path, so their raw geodesic masks fully
                    # overlap. Side ownership prevents opposite hip rotations
                    # from cancelling while retaining a soft midline blend.
                    upper_leg_taper = 1.0 - 0.92 * smoothstep(0.12, 0.27, original[1])
                    pelvis_taper = 1.0 - 0.82 * smoothstep(-0.25, -0.155, original[2])
                    mask *= (0.08 + 0.92 * side_share) * upper_leg_taper * pelvis_taper
                if is_rear:
                    changed = (original[0], original[1], original[2] + 0.052 * direction * phase * mask)
                    lift = 0.018 * mask if direction * phase > 0 else 0.0
                else:
                    angle = math.radians(22.0) * direction * phase * mask
                    changed = rotate_x(original, pivot, angle)
                    lift = 0.030 * mask if direction * phase > 0 else 0.0
                delta_x += changed[0] - original[0]
                delta_y += changed[1] - original[1] + lift
                delta_z += changed[2] - original[2]
            gait_points[gait_name] = (
                original[0] + delta_x,
                original[1] + delta_y,
                original[2] + delta_z,
            )
        outputs["gait_a"].append(gait_points["gait_a"])
        outputs["gait_b"].append(gait_points["gait_b"])
        pounce_point = original
        for leg_name, (pivot, _) in leg_specs.items():
            mask = leg_masks[leg_name][welded]
            angle = math.radians(-25.0 if leg_name.startswith("front") else 22.0) * mask
            pounce_point = rotate_x(pounce_point, pivot, angle)
            if mask > 0:
                pounce_point = (pounce_point[0], pounce_point[1] + 0.018 * mask, pounce_point[2])
        outputs["pounce_extend"].append(pounce_point)
    return outputs


def animation_rows(target_count: int, frames: list[dict[str, float]], target_names: list[str]) -> list[float]:
    rows: list[float] = []
    for frame in frames:
        rows.extend(float(frame.get(name, 0.0)) for name in target_names)
    if len(rows) % target_count:
        raise AssertionError("animation weight row is incomplete")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()

    document, binary = read_glb(args.input)
    primitive = document["meshes"][0]["primitives"][0]
    positions = [tuple(value) for value in read_accessor(document, binary, primitive["attributes"]["POSITION"])]
    indices = [int(value[0]) for value in read_accessor(document, binary, primitive["indices"])]
    raw_to_weld, welded_positions, adjacency = welded_graph(positions, indices)
    seed_specs = {
        "front_left": (-1.0, True),
        "front_right": (1.0, True),
        "rear_left": (-1.0, False),
        "rear_right": (1.0, False),
    }
    seeds = {name: choose_seed(welded_positions, side=side, front=front) for name, (side, front) in seed_specs.items()}
    leg_masks = {name: geodesic_mask(seed, adjacency) for name, seed in seeds.items()}
    targets = make_targets(positions, raw_to_weld, leg_masks)
    target_names = list(targets)
    primitive["targets"] = []
    maximum_displacements: dict[str, float] = {}
    for name, deformed in targets.items():
        deltas: list[float] = []
        maximum = 0.0
        for original, changed in zip(positions, deformed):
            delta = tuple(changed[axis] - original[axis] for axis in range(3))
            maximum = max(maximum, math.sqrt(sum(value * value for value in delta)))
            deltas.extend(delta)
        accessor = append_accessor(
            document,
            binary,
            deltas,
            "VEC3",
            target=34962,
            include_bounds=True,
        )
        primitive["targets"].append({"POSITION": accessor})
        maximum_displacements[name] = round(maximum, 6)
    mesh = document["meshes"][0]
    mesh["weights"] = [0.0] * len(target_names)
    mesh.setdefault("extras", {})["targetNames"] = target_names

    clips = {
        "Idle": (
            [0, 1, 2, 3, 4],
            [
                {"tail_left": .10, "arch": .04},
                {"tail_right": .16, "head_up": .08, "arch": .10},
                {"tail_left": .14, "head_left": .06, "crouch": .05},
                {"tail_right": .10, "head_down": .05, "arch": .08},
                {"tail_left": .10, "arch": .04},
            ],
        ),
        "Walk": (
            [0, .3, .6, .9, 1.2, 1.5, 1.8, 2.1, 2.4],
            [
                {"gait_a": .72, "tail_left": .12, "arch": .06}, {},
                {"gait_b": .72, "tail_right": .12, "crouch": .06}, {},
                {"gait_a": .72, "tail_left": .12, "arch": .06}, {},
                {"gait_b": .72, "tail_right": .12, "crouch": .06}, {},
                {"gait_a": .72, "tail_left": .12, "arch": .06},
            ],
        ),
        "Pounce": (
            [0, .55, 1.0, 1.35, 1.8, 2.35, 3.0],
            [{}, {"crouch": .72, "head_down": .36, "tail_lift": .18},
             {"crouch": 1.0, "head_down": .62, "tail_lift": .25},
             {"arch": .88, "head_up": .72, "tail_lift": .82, "tail_flare": .38, "surge": 1.0, "pounce_extend": 1.0},
             {"arch": .55, "head_up": .36, "tail_lift": .52, "surge": .44, "pounce_extend": .42},
             {"crouch": .18, "head_down": .10, "tail_lift": .18}, {}],
        ),
        "Nine-Tail Flare": (
            [0, .7, 1.2, 2.0, 2.8, 3.5],
            [{}, {"tail_lift": .42, "tail_flare": .35, "arch": .18},
             {"tail_lift": .95, "tail_flare": 1.0, "head_up": .42, "arch": .45},
             {"tail_lift": .85, "tail_flare": .92, "head_left": .18, "arch": .38},
             {"tail_lift": .38, "tail_flare": .30, "head_right": .12, "arch": .14}, {}],
        ),
        "Threat Display": (
            [0, .55, 1.0, 1.55, 2.2, 2.8, 3.4],
            [{}, {"crouch": .62, "head_down": .38, "tail_lift": .35},
             {"crouch": .82, "head_down": .72, "tail_lift": .75, "tail_flare": .72},
             {"crouch": .72, "head_left": .28, "tail_right": .32, "tail_lift": .70, "tail_flare": .62},
             {"crouch": .68, "head_right": .28, "tail_left": .32, "tail_lift": .65, "tail_flare": .55},
             {"crouch": .30, "head_down": .20, "tail_lift": .30, "tail_flare": .22}, {}],
        ),
        "Listen": (
            [0, .6, 1.15, 1.8, 2.4, 3.0],
            [{}, {"head_left": .62, "head_up": .22, "tail_right": .10},
             {"head_left": .92, "head_up": .36, "arch": .10, "tail_right": .18},
             {"head_right": .82, "head_up": .22, "tail_left": .16},
             {"head_right": .35, "head_down": .08, "tail_left": .08}, {}],
        ),
        "Dodge": (
            [0, .42, .78, 1.18, 1.65, 2.2],
            [{}, {"crouch": .52, "head_left": .35, "tail_right": .30, "lean_left": .52},
             {"arch": .48, "head_right": .72, "tail_left": .78, "tail_lift": .30, "surge": .28, "lean_right": 1.0},
             {"crouch": .35, "head_left": .32, "tail_right": .45, "lean_left": .65},
             {"arch": .12, "head_right": .12, "tail_left": .12, "lean_right": .18}, {}],
        ),
    }
    mesh_node = next(index for index, node in enumerate(document["nodes"]) if node.get("mesh") == 0)
    document["animations"] = []
    for clip_name, (times, frames) in clips.items():
        input_accessor = append_accessor(document, binary, [float(value) for value in times], "SCALAR", include_bounds=True)
        weights = animation_rows(len(target_names), frames, target_names)
        output_accessor = append_accessor(document, binary, weights, "SCALAR")
        document["animations"].append({
            "name": clip_name,
            "samplers": [{"input": input_accessor, "output": output_accessor, "interpolation": "LINEAR"}],
            "channels": [{"sampler": 0, "target": {"node": mesh_node, "path": "weights"}}],
            "extras": {
                "phases": ["preparation", "main", "recovery"],
                "semantic_regions": ["nine_tail_field", "head_neck", "spine_body", "four_legs"] if clip_name == "Walk" else ["nine_tail_field", "head_neck", "spine_body"],
                "root_motion": False,
            },
        })
    document.setdefault("asset", {})["generator"] = "shanhai3d deterministic morph fallback v8"
    write_glb(args.output, document, binary)

    report = {
        "schema_version": 1,
        "source": str(args.input),
        "output": str(args.output),
        "motion_mode": "morph",
        "fallback_reason": "Tripo quadruped rig-check passed, but its preset walk visibly misclassified low tail chains and failed deformation QC.",
        "welded_vertices": len(welded_positions),
        "raw_vertices": len(positions),
        "paw_seeds": {name: {"welded_vertex": seed, "position": list(welded_positions[seed])} for name, seed in seeds.items()},
        "leg_region_vertices": {name: sum(value > 0 for value in mask) for name, mask in leg_masks.items()},
        "morph_targets": target_names,
        "maximum_displacements": maximum_displacements,
        "walk_leg_displacements": {
            target_name: {
                leg_name: {
                    "maximum": round(max(values), 6),
                    "mean": round(sum(values) / len(values), 6),
                    "sample_vertices": len(values),
                }
                for leg_name, (side, _) in seed_specs.items()
                if (values := [
                    distance(original, changed)
                    for raw_index, (original, changed) in enumerate(zip(positions, targets[target_name]))
                    if leg_masks[leg_name][raw_to_weld[raw_index]] >= 0.5
                    and original[0] * side > 0
                ])
            }
            for target_name in ("gait_a", "gait_b")
        },
        "animations": list(clips),
        "animation_count": len(clips),
        "anatomy_changed": False,
        "notes": [
            "Leg masks are derived from welded surface geodesics, preventing spatially adjacent tails from being treated as paws.",
            "Tail motion is a continuous root-preserving field over the original nine-tail mesh; no tail is split, deleted or regenerated.",
            "All action clips are in place and contain explicit preparation, main and recovery phases.",
            "Walk v8 separates the fully overlapping rear-paw geodesic masks by left/right surface position so opposite hind strides no longer cancel.",
            "The rear step uses a restrained tapered fore-aft limb field with swing-foot lift; this keeps the abdomen and inner-thigh surface stable while making both hind paws visibly alternate."
        ],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
