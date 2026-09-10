"""Bundled Gallery seed: 12 GiftCards under ``data/fallback/gallery/``.

Served at ``/demo/{id}/card.png`` (and ``video.mp4`` when present). Merged into
``GET /api/wall`` so Sim and Real both show them by default; published storage
items with the same id win.
"""

from __future__ import annotations

from typing import Any

from santa.config import REPO_ROOT

GALLERY_DIR = REPO_ROOT / "data" / "fallback" / "gallery"

# Keep in sync with GALLERY_SEED in santa/service/ui/src/App.tsx
DEMO_KIDS: list[dict[str, Any]] = [
    {
        "id": "g1",
        "name": "Emma",
        "age": 8,
        "wish": "Dear Alex, my dear three‑year‑old explorer, I’ve heard about the wonderful wooden car that loves to pull you along sn…",
        "tags": ["books"],
        "mood": "Dreamy",
        "city": "Oslo",
        "gift": "Wooden pull‑along car",
        "has_video": True,
    },
    {
        "id": "g2",
        "name": "Lucas",
        "age": 8,
        "wish": "Dear Kid, being 8 is such a marvelous age for discovering new wonders, and I’ve heard you’ll be building fantastic cr…",
        "tags": ["lego"],
        "mood": "Dreamy",
        "city": "Stockholm",
        "gift": "LEGO Creator 3‑in‑1 Building Set",
        "has_video": False,
    },
    {
        "id": "g3",
        "name": "Sofia",
        "age": 8,
        "wish": "Dear Kid, at the wonderful age of 8 your imagination is already as bright as the twinkling lights on my sleigh. I hea…",
        "tags": ["lego", "robots"],
        "mood": "Dreamy",
        "city": "Helsinki",
        "gift": "LEGO Boost Creative Toolbox (STEM building kit)",
        "has_video": False,
    },
    {
        "id": "g4",
        "name": "Noah",
        "age": 8,
        "wish": "Dear Kid, at 8 years old you’re already a brilliant explorer of imagination! I hear you’ve been crafting marvelous in…",
        "tags": ["robots", "lego"],
        "mood": "Dreamy",
        "city": "Copenhagen",
        "gift": "Interactive STEM building set (e.g., magnetic circuits or robot kit)",
        "has_video": False,
    },
    {
        "id": "g5",
        "name": "Ingrid",
        "age": 8,
        "wish": "Dear Kid, at your wonderful age of 8 you’re already a master of building marvelous structures that snap together, a b…",
        "tags": ["lego"],
        "mood": "Dreamy",
        "city": "Bergen",
        "gift": "Magnetic building tiles set",
        "has_video": False,
    },
    {
        "id": "g6",
        "name": "Felix",
        "age": 8,
        "wish": "Dear Kid, at eight years old you already shine with the curiosity of a thousand stars. I’ve placed a handful of wondr…",
        "tags": ["robots"],
        "mood": "Dreamy",
        "city": "Malmö",
        "gift": "Interactive STEM building set",
        "has_video": False,
    },
    {
        "id": "g7",
        "name": "Astrid",
        "age": 8,
        "wish": "Dear Kid, I hear that being 8 years old fills your days with curiosity and wonder! This year the North Pole elves hav…",
        "tags": ["robots", "lego"],
        "mood": "Dreamy",
        "city": "Gothenburg",
        "gift": "STEM Building Kit (magnetic tiles or simple robotics set)",
        "has_video": False,
    },
    {
        "id": "g8",
        "name": "Oliver",
        "age": 8,
        "wish": "Hello Kid! At eight years old, your curiosity shines brighter than the North Star, and I hear the soft clink of magne…",
        "tags": ["robots", "lego"],
        "mood": "Dreamy",
        "city": "Espoo",
        "gift": "Magnetic STEM Building Kit",
        "has_video": False,
    },
    {
        "id": "g9",
        "name": "Nick",
        "age": 5,
        "wish": "Lego and animals",
        "tags": ["dinosaurs", "lego"],
        "mood": "Dreamy",
        "city": "Turku",
        "gift": "LEGO Dino Adventure Building Set",
        "has_video": False,
    },
    {
        "id": "g10",
        "name": "Elias",
        "age": 8,
        "wish": "Dear Kid, being eight is such a wonderful time when every question feels like a new adventure, and I’ve seen how your…",
        "tags": ["lego", "robots"],
        "mood": "Dreamy",
        "city": "Aarhus",
        "gift": "STEM Building Kit (e.g., LEGO Boost or similar)",
        "has_video": False,
    },
    {
        "id": "g11",
        "name": "Freya",
        "age": 8,
        "wish": "Dear Kid, at the wonderful age of 8 you’re already a true master of imagination. I’ve heard the North Pole elves have…",
        "tags": ["lego"],
        "mood": "Dreamy",
        "city": "Odense",
        "gift": "LEGO Creator 3‑in‑1 Building Set",
        "has_video": False,
    },
    {
        "id": "g12",
        "name": "Viktor",
        "age": 8,
        "wish": "Hello Kid, being eight means your imagination shines brighter than the twinkling lights on my sleigh. I’ve tucked a c…",
        "tags": ["robots", "lego"],
        "mood": "Dreamy",
        "city": "Tampere",
        "gift": "Magnetic STEM Building Tiles",
        "has_video": False,
    },
]


def demo_wall_items() -> list[dict[str, Any]]:
    """Wall ``items[]`` for bundled demo GiftCards that exist on disk."""
    items: list[dict[str, Any]] = []
    for kid in DEMO_KIDS:
        kid_id = str(kid["id"])
        png = GALLERY_DIR / kid_id / "card.png"
        if not png.is_file():
            continue
        has_video = bool(kid.get("has_video")) and (GALLERY_DIR / kid_id / "video.mp4").is_file()
        items.append(
            {
                "id": kid_id,
                "name": kid["name"],
                "age": kid["age"],
                "wish": kid["wish"],
                "gift": kid.get("gift") or "",
                "mood": kid["mood"],
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
