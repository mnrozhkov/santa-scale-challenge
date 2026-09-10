"""Bundled Gallery seed: 12 GiftCards under ``data/fallback/gallery/``.

Served at ``/demo/{id}/card.png`` (and ``video.mp4`` when present). Merged into
``GET /api/wall`` so Sim shows them by default; published storage items with the
same id win. Real-mode Gallery filters these ``/demo/`` rows out in the UI.

Catalog lives in ``data/fallback/gallery/catalog.json`` (regenerate with
``scripts/make_gallery.py --install``). Keep ``GALLERY_SEED`` in
``santa/service/ui/src/App.tsx`` in sync for Sim when the API is down.
"""

from __future__ import annotations

import json
from typing import Any

from santa.config import REPO_ROOT

GALLERY_DIR = REPO_ROOT / "data" / "fallback" / "gallery"


def load_catalog() -> list[dict[str, Any]]:
    """Rows from ``catalog.json``. Empty if the file is missing or invalid."""
    path = GALLERY_DIR / "catalog.json"
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict) and row.get("id")]


# Snapshot at import; ``demo_wall_items`` re-reads the file.
DEMO_KIDS: list[dict[str, Any]] = load_catalog()


def demo_wall_items() -> list[dict[str, Any]]:
    """Wall ``items[]`` for bundled demo GiftCards that exist on disk."""
    items: list[dict[str, Any]] = []
    for kid in load_catalog() or DEMO_KIDS:
        kid_id = str(kid["id"])
        png = GALLERY_DIR / kid_id / "card.png"
        if not png.is_file():
            continue
        has_video = (GALLERY_DIR / kid_id / "video.mp4").is_file()
        items.append(
            {
                "id": kid_id,
                "name": kid.get("name") or kid_id,
                "age": kid.get("age") or 8,
                "wish": kid.get("wish") or "",
                "gift": kid.get("gift") or "",
                "mood": kid.get("mood") or "Warm",
                "city": kid.get("city") or "",
                "tags": list(kid.get("tags") or []),
                "has_video": has_video,
                "png_url": f"/demo/{kid_id}/card.png",
                "video_url": f"/demo/{kid_id}/video.mp4" if has_video else None,
                "model": "demo",
            }
        )
    return items


def merge_demo_wall(listing: dict[str, Any]) -> dict[str, Any]:
    """Merge demo + published items; GiftCards with video come first."""
    demos = demo_wall_items()
    by_id: dict[str, dict[str, Any]] = {item["id"]: item for item in demos}
    for item in listing.get("items") or []:
        if not isinstance(item, dict):
            continue
        kid_id = str(item.get("id") or "")
        if not kid_id:
            continue
        by_id[kid_id] = item
    items = list(by_id.values())
    items.sort(key=lambda item: (not bool(item.get("has_video")), str(item.get("id") or "")))
    merged = dict(listing)
    merged["items"] = items
    return merged
