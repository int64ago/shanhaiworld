#!/usr/bin/env python3
"""Generate a public-only static site for GitHub Pages.

The repository keeps production evidence, source models, and local secrets.
This builder copies only the runtime surface a visitor needs: the home page,
shared assets, and ready collections (page, catalog entry, preview, web.glb,
and referenced scene/audio files).
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit


LFS_POINTER_PREFIX = b"version https://git-lfs.github.com/spec/v1"
SKIP_NAMES = {".ds_store", "thumbs.db"}
PUBLIC_ASSET_DIRS = ("css", "js", "vendor")
PUBLIC_ASSET_FILES = ("favicon.svg",)
OPTIONAL_ROOT_FILES = ("CNAME",)
SHARED_VIEWER_UI = "shared-v1"
SHARED_NARRATION_VOICE = "mandarin-tingting-r160-v1"
SHARED_VIEWER_TEMPLATE_MARKERS = (
    'id="toggle-immersive"',
    'class="immersive-toggle back-link bilingual-button"',
    'aria-pressed="false"',
)


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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def strip_asset_query(value: str) -> str:
    return unquote(urlsplit(value).path)


def is_lfs_pointer(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size > 1024:
        return False
    with path.open("rb") as handle:
        return handle.read(len(LFS_POINTER_PREFIX)) == LFS_POINTER_PREFIX


def resolve_collection_asset(collection_root: Path, raw_path: str) -> Path:
    relative = strip_asset_query(raw_path).lstrip("/")
    if not relative or relative.startswith("/") or Path(relative).is_absolute():
        raise RuntimeError(f"Unsafe asset path in collection.json: {raw_path}")
    resolved = (collection_root / relative).resolve()
    try:
        resolved.relative_to(collection_root.resolve())
    except ValueError as exc:
        raise RuntimeError(f"Asset path escapes collection directory: {raw_path}") from exc
    return resolved


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise RuntimeError(f"Required runtime file is missing: {source}")
    if is_lfs_pointer(source):
        raise RuntimeError(
            f"Refusing to publish Git LFS pointer {source}. "
            "GitHub Pages cannot serve LFS objects as ordinary site assets."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_tree(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise RuntimeError(f"Required directory is missing: {source}")
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name.startswith(".") or item.name.lower() in SKIP_NAMES:
            continue
        target = destination / item.name
        if item.is_dir():
            copy_tree(item, target)
        elif item.is_file():
            copy_file(item, target)


def referenced_runtime_paths(collection: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    preview = collection.get("preview")
    if isinstance(preview, str) and preview:
        refs.append(preview)
    model = collection.get("model")
    if isinstance(model, dict) and isinstance(model.get("path"), str):
        refs.append(model["path"])
    scene = collection.get("scene")
    if isinstance(scene, dict):
        for key in ("background", "props"):
            value = scene.get(key)
            if isinstance(value, str) and value:
                refs.append(value)
    narration = collection.get("narration")
    if isinstance(narration, dict) and isinstance(narration.get("audio"), str):
        refs.append(narration["audio"])
    return refs


def render_collection_html(template: str, collection: dict[str, Any]) -> str:
    name = str(collection.get("name") or "神兽")
    summary = str(collection.get("summary") or f"{name}互动 3D 图鉴")
    title = html.escape(f"{name} · 山海万象", quote=False)
    description = html.escape(f"{name}互动 3D 图鉴：{summary}", quote=True)
    safe_name = html.escape(name, quote=False)
    rendered = template
    rendered = rendered.replace(
        'content="山海万象神兽 3D 场景"',
        f'content="{description}"',
    )
    rendered = rendered.replace("<title>神兽 · 山海万象</title>", f"<title>{title}</title>")
    rendered = rendered.replace(
        "点击按钮，朗读神兽的详细介绍。",
        f"点击按钮，朗读{safe_name}的详细介绍。",
    )
    rendered = rendered.replace("正在请神兽出来…", f"正在请{safe_name}出来…")
    return rendered


def render_not_found_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>未找到 · 山海万象</title>
    <link rel="icon" href="./assets/favicon.svg" type="image/svg+xml" />
    <link rel="stylesheet" href="./assets/css/site.css" />
  </head>
  <body class="home-page">
    <main>
      <section class="hero">
        <p class="eyebrow"><span>页面不存在</span></p>
        <h1>未找到这只神兽</h1>
        <p class="hero-copy"><span>它可能还在山海之间，或尚未发布到图鉴。</span></p>
        <a class="hero-link" href="./index.html"><span>返回图鉴首页</span></a>
      </section>
    </main>
  </body>
</html>
"""


def public_catalog_item(item: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "id",
        "name",
        "name_pinyin",
        "subtitle",
        "summary",
        "body_type",
        "preview",
        "href",
        "status",
    )
    return {key: item[key] for key in allowed if key in item}


def validate_shared_viewer_contract(
    collection: dict[str, Any], creature_id: str
) -> None:
    narration = collection.get("narration")
    if (
        collection.get("viewer_ui") != SHARED_VIEWER_UI
        or collection.get("kid_mode") is not True
        or not isinstance(narration, dict)
        or narration.get("voice_profile") != SHARED_NARRATION_VOICE
        or not isinstance(narration.get("audio"), str)
        or not narration["audio"]
        or not isinstance(narration.get("text"), str)
        or not narration["text"].strip()
    ):
        raise RuntimeError(
            f"Ready collection {creature_id} must use the shared viewer UI "
            f"contract {SHARED_VIEWER_UI!r} with kid_mode=true and fixed "
            f"narration {SHARED_NARRATION_VOICE!r}"
        )


def validate_shared_viewer_template(template: str) -> None:
    missing = [marker for marker in SHARED_VIEWER_TEMPLATE_MARKERS if marker not in template]
    if missing:
        raise RuntimeError(
            "Shared collection template is missing required immersive-mode markup: "
            + ", ".join(missing)
        )


def build_site(project_root: Path, output: Path) -> dict[str, Any]:
    home = project_root / "index.html"
    catalog_path = project_root / "assets" / "data" / "collections.json"
    template_html = project_root / "assets" / "templates" / "collection" / "index.html"
    assets_root = project_root / "assets"
    template_source = template_html.read_text(encoding="utf-8")
    validate_shared_viewer_template(template_source)

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    copy_file(home, output / "index.html")
    for filename in OPTIONAL_ROOT_FILES:
        source = project_root / filename
        if source.is_file():
            copy_file(source, output / filename)
    for directory in PUBLIC_ASSET_DIRS:
        copy_tree(assets_root / directory, output / "assets" / directory)
    for filename in PUBLIC_ASSET_FILES:
        copy_file(assets_root / filename, output / "assets" / filename)

    catalog = read_json(catalog_path)
    raw_items = catalog.get("collections")
    if not isinstance(raw_items, list):
        raise RuntimeError(f"Expected 'collections' to be an array in {catalog_path}")

    published: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict) or item.get("status") != "ready":
            continue
        creature_id = item.get("id")
        if not isinstance(creature_id, str) or not creature_id:
            raise RuntimeError("Ready catalog entry is missing a valid id")

        collection_root = project_root / "collections" / creature_id
        collection_config_path = collection_root / "collection.json"
        collection = read_json(collection_config_path)
        if collection.get("status") != "ready":
            raise RuntimeError(
                f"Catalog marks {creature_id} ready, but collection.json status is "
                f"{collection.get('status')!r}"
            )
        validate_shared_viewer_contract(collection, creature_id)

        destination_root = output / "collections" / creature_id
        destination_root.mkdir(parents=True, exist_ok=True)
        copy_file(collection_config_path, destination_root / "collection.json")
        (destination_root / "index.html").write_text(
            render_collection_html(template_source, collection),
            encoding="utf-8",
        )

        copied_assets: list[str] = []
        for raw_path in referenced_runtime_paths(collection):
            source = resolve_collection_asset(collection_root, raw_path)
            relative = source.relative_to(collection_root)
            copy_file(source, destination_root / relative)
            copied_assets.append(str(relative).replace("\\", "/"))

        published.append(
            {
                "id": creature_id,
                "name": collection.get("name"),
                "assets": copied_assets,
            }
        )

    write_json(
        output / "assets" / "data" / "collections.json",
        {
            "schema_version": 1,
            "collections": [public_catalog_item(item) for item in raw_items if isinstance(item, dict) and item.get("status") == "ready"],
        },
    )
    (output / ".nojekyll").write_text("", encoding="utf-8")
    (output / "404.html").write_text(render_not_found_html(), encoding="utf-8")

    return {
        "output": str(output),
        "collections": published,
        "collection_count": len(published),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a public-only static site for GitHub Pages."
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--output", default="dist")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).expanduser().resolve()
    output = Path(args.output)
    if not output.is_absolute():
        output = project_root / output
    result = build_site(project_root, output.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
