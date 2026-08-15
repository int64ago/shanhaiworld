#!/usr/bin/env python3
"""Initialize one Shanhaiworld creature collection from only its Chinese name."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUBDIRECTORIES = (
    "concepts",
    "views",
    "models",
    "animations",
    "scene",
    "reports",
    "production/research",
    "production/prompts/concepts",
    "production/prompts/views",
    "production/prompts/scenes",
    "production/prompts/previews",
    "production/prompts/audio",
    "production/generations/concepts",
    "production/generations/views",
    "production/generations/scenes",
    "production/generations/previews",
    "production/providers/tripo/requests",
    "production/providers/tripo/responses",
    "production/providers/rodin/requests",
    "production/providers/rodin/responses",
    "production/logs",
)
ASCII_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalized_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug or not ASCII_SLUG.fullmatch(slug):
        raise ValueError(
            "--slug must contain only lowercase ASCII letters, digits, and hyphens"
        )
    return slug


def choose_slug(name: str, requested: str | None) -> str:
    if requested:
        return normalized_slug(requested)

    candidate = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if candidate and ASCII_SLUG.fullmatch(candidate):
        return candidate

    # The skill normally supplies a readable pinyin slug. This deterministic
    # fallback keeps direct name-only CLI usage valid without extra libraries.
    digest = hashlib.sha256(name.strip().encode("utf-8")).hexdigest()[:10]
    return f"shenshou-{digest}"


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object in {path}")
    return value


def write_json(path: Path, payload: dict[str, Any], force: bool = False) -> bool:
    if path.exists() and not force:
        return False
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return True


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def update_catalog(project_root: Path, creature_id: str, name: str) -> Path:
    catalog_path = project_root / "assets" / "data" / "collections.json"
    catalog = read_json(catalog_path)
    collections = catalog.get("collections")
    if not isinstance(collections, list):
        raise RuntimeError(f"Expected 'collections' to be an array in {catalog_path}")

    defaults: dict[str, Any] = {
        "id": creature_id,
        "name": name,
        "subtitle": "山海神兽",
        "summary": "",
        "body_type": "unknown",
        "preview": f"./collections/{creature_id}/preview.webp",
        "href": f"./collections/{creature_id}/index.html",
        "status": "draft",
    }

    position = next(
        (
            index
            for index, item in enumerate(collections)
            if isinstance(item, dict) and item.get("id") == creature_id
        ),
        None,
    )
    if position is None:
        collections.append(defaults)
    else:
        existing = collections[position]
        collections[position] = {
            **defaults,
            **existing,
            "id": creature_id,
            "name": name,
            "preview": defaults["preview"],
            "href": defaults["href"],
        }

    catalog["schema_version"] = 1
    write_json_atomic(catalog_path, catalog)
    return catalog_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize a Shanhaiworld creature collection from its name."
    )
    parser.add_argument("name", help="Creature name, for example 九尾狐")
    parser.add_argument(
        "--project-root",
        default=".",
        help="Shanhaiworld project root (default: current directory)",
    )
    parser.add_argument(
        "--slug",
        help="Optional readable ASCII slug chosen internally by the skill, e.g. jiuweihu",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Refresh generated JSON and the collection HTML template",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    name = args.name.strip()
    if not name:
        raise SystemExit("Creature name must not be empty")

    try:
        creature_id = choose_slug(name, args.slug)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    project_root = Path(args.project_root).expanduser().resolve()
    template_root = project_root / "assets" / "templates" / "collection"
    template_html = template_root / "index.html"
    template_config = template_root / "collection.json"
    if not template_html.is_file() or not template_config.is_file():
        raise SystemExit(
            "Collection templates are missing. Run this inside the Shanhaiworld project root."
        )

    root = project_root / "collections" / creature_id
    root.mkdir(parents=True, exist_ok=True)
    for directory in SUBDIRECTORIES:
        (root / directory).mkdir(parents=True, exist_ok=True)

    created_at = now_iso()
    spec = {
        "schema_version": 1,
        "creature_id": creature_id,
        "name": name,
        "input_mode": "name_only",
        "status": "initialized",
        "created_at": created_at,
        "intent": {
            "platform": "desktop_web",
            "renderer": "threejs",
            "interaction": "mouse",
            "autonomous_motion": True,
            "rich_actions": True,
            "coherent_scene": True,
            "visual_target": "high_fidelity_pc",
            "quality_priority": "quality_over_credits",
            "preferred_motion_mode": "skeletal",
            "accepted_motion_modes": [
                "skeletal",
                "morph",
                "articulated",
                "hybrid",
            ],
            "hard_quality_gates": [
                "reference",
                "model",
                "detail",
                "motion_system",
                "animation",
            ],
        },
        "design": {
            "body_type": "unknown",
            "locked_traits": [],
            "anatomy_profile": {
                "counted_features": [],
                "continuous_features": [],
                "articulated_regions": [],
                "surface_features": [],
                "locomotion_modes": [],
                "not_applicable": [],
            },
        },
        "creative_brief": None,
        "production": {
            "concept_provider": "codex_imagegen",
            "model_provider": "hyper3d_rodin_gen2",
            "animation_provider": "best_available_motion_system",
            "required_env": ["RODIN_API_KEY", "TRIPO_API_KEY"],
            "optional_env": ["MESHY_API_KEY"],
            "env_file": ".env",
        },
    }

    manifest = {
        "schema_version": 1,
        "creature_id": creature_id,
        "name": name,
        "status": "initialized",
        "created_at": created_at,
        "updated_at": created_at,
        "artifacts": [],
        "checks": [
            {"id": "reference_quality", "status": "pending", "evidence": None},
            {"id": "model_quality", "status": "pending", "evidence": None},
            {"id": "detail_quality", "status": "pending", "evidence": None},
            {"id": "motion_system_quality", "status": "pending", "evidence": None},
            {"id": "animation_quality", "status": "pending", "evidence": None},
        ],
        "notes": [],
    }

    quality_reports = {
        "reference-qc.json": [
            "anatomy_profile_defined",
            "applicable_counts",
            "continuous_structure_integrity",
            "articulation_visibility",
            "cross_view_consistency",
            "material_legibility",
            "clean_background",
            "provider_input_suitability",
        ],
        "model-qc.json": [
            "locked_traits",
            "topology_and_connections",
            "silhouette",
            "turntable_and_closeups",
        ],
        "detail-qc.json": [
            "face_and_signature_details",
            "surface_directionality",
            "pbr_channels",
            "optimization_retention",
        ],
        "rig-qc.json": [
            "motion_mode_declared",
            "skeletal_attempt_recorded",
            "motion_targets_present",
            "articulated_region_coverage",
            "deformation_quality",
        ],
        "animation-qc.json": [
            "minimum_six_actions",
            "semantic_match",
            "body_region_deformation",
            "locomotion_match",
            "timing_and_recovery",
            "action_variety",
            "transitions_and_loops",
        ],
    }

    production_audit = {
        "schema_version": 1,
        "creature_id": creature_id,
        "name": name,
        "created_at": created_at,
        "updated_at": created_at,
        "runs": [],
        "selections": {
            "concept": None,
            "views": {},
            "scene_background": None,
            "preview": None,
            "model": None,
        },
    }

    research_sources = {
        "schema_version": 1,
        "creature_id": creature_id,
        "name": name,
        "sources": [],
    }

    provider_tasks = {
        "schema_version": 1,
        "creature_id": creature_id,
        "provider": "tripo",
        "tasks": [],
    }

    rodin_tasks = {
        "schema_version": 1,
        "creature_id": creature_id,
        "provider": "hyper3d_rodin_gen2",
        "tasks": [],
    }

    collection_config = read_json(template_config)
    collection_config.update(
        {
            "id": creature_id,
            "name": name,
            "status": "draft",
            "viewer_ui": "shared-v1",
            "kid_mode": True,
            "preview": "./preview.webp",
            "model": {
                "path": "./models/web.glb",
                "target_height": 2.6,
                "facing_offset": 0,
                "in_place_root_motion": True,
            },
            "animation": {
                "mode": "skeletal",
                "min_actions": 6,
                "min_animated_nodes": 3,
            },
        }
    )

    written = []
    if write_json(root / "spec.json", spec, force=args.force):
        written.append(str(root / "spec.json"))
    if write_json(root / "manifest.json", manifest, force=args.force):
        written.append(str(root / "manifest.json"))
    if write_json(root / "collection.json", collection_config, force=args.force):
        written.append(str(root / "collection.json"))
    # Audit history is append-only production evidence. Even --force must not
    # erase existing prompts, generations, provider records, or selections.
    if write_json(root / "production" / "audit.json", production_audit):
        written.append(str(root / "production" / "audit.json"))
    if write_json(root / "production" / "research" / "sources.json", research_sources):
        written.append(str(root / "production" / "research" / "sources.json"))
    for filename, checks in quality_reports.items():
        quality_report = {
            "schema_version": 1,
            "creature_id": creature_id,
            "name": name,
            "status": "pending",
            "checked_at": None,
            "checks": [
                {"id": check, "status": "pending", "evidence": None, "notes": []}
                for check in checks
            ],
            "blocking_failures": [],
        }
        report_path = root / "reports" / filename
        if write_json(report_path, quality_report):
            written.append(str(report_path))
    if write_json(
        root / "production" / "providers" / "tripo" / "tasks.json",
        provider_tasks,
    ):
        written.append(
            str(root / "production" / "providers" / "tripo" / "tasks.json")
        )
    if write_json(
        root / "production" / "providers" / "rodin" / "tasks.json",
        rodin_tasks,
    ):
        written.append(
            str(root / "production" / "providers" / "rodin" / "tasks.json")
        )

    collection_html = root / "index.html"
    if args.force or not collection_html.exists():
        shutil.copyfile(template_html, collection_html)
        written.append(str(collection_html))

    catalog_path = update_catalog(project_root, creature_id, name)

    result = {
        "creature_id": creature_id,
        "name": name,
        "collection_root": str(root),
        "entry_html": str(collection_html),
        "catalog": str(catalog_path),
        "production_audit": str(root / "production" / "audit.json"),
        "written": written,
        "next": "Complete every QC report in order. Do not call the next paid stage or publish until all hard gates pass.",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
