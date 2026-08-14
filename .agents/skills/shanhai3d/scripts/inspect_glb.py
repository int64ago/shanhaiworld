#!/usr/bin/env python3
"""Report GLB geometry, materials, skinning and animation structure."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import struct
from pathlib import Path
from typing import Any


def load_glb(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        header = stream.read(12)
        if len(header) != 12:
            raise RuntimeError("File is too short for a GLB header")
        magic, version, declared_length = struct.unpack("<4sII", header)
        if magic != b"glTF" or version != 2:
            raise RuntimeError("Expected a glTF 2.0 binary file")
        chunk_length, chunk_type = struct.unpack("<II", stream.read(8))
        if chunk_type != 0x4E4F534A:
            raise RuntimeError("First GLB chunk is not JSON")
        document = json.loads(stream.read(chunk_length).decode("utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError("Expected a glTF JSON object")
    document["_declared_length"] = declared_length
    return document


def primitive_triangles(document: dict[str, Any], primitive: dict[str, Any]) -> int:
    accessors = document.get("accessors", [])
    index = primitive.get("indices")
    if isinstance(index, int) and 0 <= index < len(accessors):
        count = int(accessors[index].get("count", 0))
    else:
        position = primitive.get("attributes", {}).get("POSITION")
        count = int(accessors[position].get("count", 0)) if isinstance(position, int) else 0
    mode = int(primitive.get("mode", 4))
    if mode == 4:
        return count // 3
    if mode in (5, 6):
        return max(0, count - 2)
    return 0


def inspect(path: Path) -> dict[str, Any]:
    document = load_glb(path)
    meshes = document.get("meshes", [])
    primitives = [
        primitive
        for mesh in meshes
        for primitive in mesh.get("primitives", [])
        if isinstance(primitive, dict)
    ]
    triangles = sum(primitive_triangles(document, primitive) for primitive in primitives)
    materials = document.get("materials", [])
    images = document.get("images", [])
    animations = document.get("animations", [])
    skins = document.get("skins", [])
    nodes = document.get("nodes", [])
    accessors = document.get("accessors", [])
    joint_indices = {
        joint
        for skin in skins
        for joint in skin.get("joints", [])
        if isinstance(joint, int)
    }
    skinned_primitives = sum(
        1
        for primitive in primitives
        if "JOINTS_0" in primitive.get("attributes", {})
        and "WEIGHTS_0" in primitive.get("attributes", {})
    )
    morph_target_primitives = sum(
        1 for primitive in primitives if len(primitive.get("targets", [])) > 0
    )
    channel_targets = [
        channel.get("target", {})
        for animation in animations
        for channel in animation.get("channels", [])
        if isinstance(channel.get("target"), dict)
    ]
    target_path_counts = Counter(
        str(target.get("path"))
        for target in channel_targets
        if target.get("path") is not None
    )
    animated_node_indices = {
        target.get("node")
        for target in channel_targets
        if isinstance(target.get("node"), int)
    }
    transform_animated_node_indices = {
        target.get("node")
        for target in channel_targets
        if isinstance(target.get("node"), int)
        and target.get("path") in {"translation", "rotation", "scale"}
    }
    skeletal_animated_nodes = animated_node_indices & joint_indices
    scene_root_indices = {
        node_index
        for scene in document.get("scenes", [])
        for node_index in scene.get("nodes", [])
        if isinstance(node_index, int)
    }
    generic_root_names = {"root", "scene", "armature", "model", "actor", "object"}
    semantic_animated_nodes = {
        index
        for index in transform_animated_node_indices - joint_indices - scene_root_indices
        if 0 <= index < len(nodes)
        and str(nodes[index].get("name", "")).strip()
        and str(nodes[index].get("name", "")).strip().lower() not in generic_root_names
    }
    animation_durations = []
    for animation in animations:
        duration = 0.0
        for sampler in animation.get("samplers", []):
            accessor_index = sampler.get("input")
            if not isinstance(accessor_index, int) or not 0 <= accessor_index < len(accessors):
                continue
            accessor = accessors[accessor_index]
            minimum = accessor.get("min", [0])
            maximum = accessor.get("max", [0])
            if minimum and maximum:
                duration = max(duration, float(maximum[0]) - float(minimum[0]))
        animation_durations.append(round(duration, 4))
    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "declared_bytes": document.get("_declared_length"),
        "scenes": len(document.get("scenes", [])),
        "nodes": len(nodes),
        "meshes": len(meshes),
        "primitives": len(primitives),
        "triangles": triangles,
        "materials": len(materials),
        "textures": len(document.get("textures", [])),
        "images": len(images),
        "image_mime_types": sorted(
            {str(image.get("mimeType")) for image in images if image.get("mimeType")}
        ),
        "skins": len(skins),
        "skin_joint_counts": [len(skin.get("joints", [])) for skin in skins],
        "unique_joints": len(joint_indices),
        "skinned_primitives": skinned_primitives,
        "morph_target_primitives": morph_target_primitives,
        "animations": len(animations),
        "animation_names": [animation.get("name") or f"animation-{index}" for index, animation in enumerate(animations)],
        "animation_durations": animation_durations,
        "animation_channel_counts": [len(animation.get("channels", [])) for animation in animations],
        "animated_nodes": len(animated_node_indices),
        "skeletal_animated_nodes": len(skeletal_animated_nodes),
        "morph_weight_channels": target_path_counts.get("weights", 0),
        "semantic_articulated_nodes": len(semantic_animated_nodes),
        "animation_target_path_counts": dict(sorted(target_path_counts.items())),
        "animated_node_names": [
            nodes[index].get("name") or f"node-{index}"
            for index in sorted(animated_node_indices)
            if 0 <= index < len(nodes)
        ][:80],
        "extensions_used": document.get("extensionsUsed", []),
        "extensions_required": document.get("extensionsRequired", []),
        "node_names": [node.get("name") for node in nodes if node.get("name")][:30],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument(
        "--require-skin",
        action="store_true",
        help="Fail unless the GLB has a skin, joints, weights and skinned primitives",
    )
    parser.add_argument(
        "--motion-mode",
        choices=("skeletal", "morph", "articulated", "hybrid"),
        help="Validate concrete motion evidence for the declared motion mode",
    )
    parser.add_argument(
        "--min-animated-nodes",
        type=int,
        default=3,
        help="Minimum semantic nodes for articulated motion (default: 3)",
    )
    parser.add_argument(
        "--min-animations",
        type=int,
        default=0,
        help="Fail unless at least this many animation clips exist",
    )
    args = parser.parse_args()
    path = Path(args.path).expanduser().resolve()
    report = inspect(path)
    failures = []
    if args.require_skin:
        if report["skins"] < 1:
            failures.append("no skin")
        if report["unique_joints"] < 1:
            failures.append("no joints")
        if report["skinned_primitives"] < 1:
            failures.append("no primitives with JOINTS_0 and WEIGHTS_0")
    motion_evidence = {
        "skeletal": (
            report["skins"] > 0
            and report["unique_joints"] > 0
            and report["skinned_primitives"] > 0
            and report["skeletal_animated_nodes"] > 0
        ),
        "morph": (
            report["morph_target_primitives"] > 0
            and report["morph_weight_channels"] > 0
        ),
        "articulated": (
            report["semantic_articulated_nodes"] >= max(2, args.min_animated_nodes)
        ),
    }
    if args.motion_mode:
        if args.motion_mode == "hybrid":
            if sum(motion_evidence.values()) < 2:
                failures.append("hybrid motion requires evidence from at least two motion systems")
        elif not motion_evidence[args.motion_mode]:
            failures.append(f"no valid {args.motion_mode} motion evidence")
    if report["animations"] < args.min_animations:
        failures.append(
            f"only {report['animations']} animations; require {args.min_animations}"
        )
    if args.min_animations and report["animated_nodes"] < 1:
        failures.append("animations target no nodes")
    report["validation_failures"] = failures
    report["requested_motion_mode"] = args.motion_mode
    report["motion_mode_evidence"] = motion_evidence
    report["validation_passed"] = not failures
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
