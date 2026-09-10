#!/usr/bin/env python3
"""Regenerate the 12 bundled Gallery GiftCards and their mood-bank animations.

Default writes ``out/gallery/{id}/card.png|html|json`` plus ``video.mp4``.
``--install`` copies into ``data/fallback/gallery/`` and refreshes ``catalog.json``.

    uv run scripts/make_gallery.py
    uv run scripts/make_gallery.py --skip-animate
    uv run scripts/make_gallery.py --install
    uv run scripts/make_gallery.py --force
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from santa.config import REPO_ROOT
from santa.schemas import KidProfile

DEFAULT_DEST = REPO_ROOT / "out" / "gallery"
GALLERY_DIR = REPO_ROOT / "data" / "fallback" / "gallery"

# Names + cities stay the Sim seed identities. Ages/tags/wishlists are spread
# across the Gallery filters so the wall is not 12 copies of "age 8, LEGO".
GALLERY_KIDS: tuple[dict[str, Any], ...] = (
    {
        "id": "g1",
        "name": "Emma",
        "age": 8,
        "wish": "picture books and bedtime stories",
        "tags": ["books"],
        "city": "Oslo",
    },
    {
        "id": "g2",
        "name": "Lucas",
        "age": 8,
        "wish": "LEGO city streets and spaceships",
        "tags": ["lego"],
        "city": "Stockholm",
    },
    {
        "id": "g3",
        "name": "Sofia",
        "age": 7,
        "wish": "paints, crayons, and a sketchbook",
        "tags": ["art"],
        "city": "Helsinki",
    },
    {
        "id": "g4",
        "name": "Noah",
        "age": 10,
        "wish": "a robot I can program myself",
        "tags": ["robots"],
        "city": "Copenhagen",
    },
    {
        "id": "g5",
        "name": "Ingrid",
        "age": 6,
        "wish": "plush animals and a little farm set",
        "tags": ["animals"],
        "city": "Bergen",
    },
    {
        "id": "g6",
        "name": "Felix",
        "age": 9,
        "wish": "a telescope and glow-in-the-dark stars",
        "tags": ["space"],
        "city": "Malmö",
    },
    {
        "id": "g7",
        "name": "Astrid",
        "age": 8,
        "wish": "a keyboard and jingle bells",
        "tags": ["music"],
        "city": "Gothenburg",
    },
    {
        "id": "g8",
        "name": "Oliver",
        "age": 11,
        "wish": "a football and a backyard goal",
        "tags": ["football"],
        "city": "Espoo",
    },
    {
        "id": "g9",
        "name": "Nick",
        "age": 5,
        "wish": "LEGO dinosaurs and animals",
        "tags": ["dinosaurs", "lego"],
        "city": "Turku",
    },
    {
        "id": "g10",
        "name": "Elias",
        "age": 8,
        "wish": "sea animals and a toy boat",
        "tags": ["ocean"],
        "city": "Aarhus",
    },
    {
        "id": "g11",
        "name": "Freya",
        "age": 7,
        "wish": "LEGO flowers and a drawing set",
        "tags": ["lego", "art"],
        "city": "Odense",
    },
    {
        "id": "g12",
        "name": "Viktor",
        "age": 9,
        "wish": "magnetic tiles and a robot kit",
        "tags": ["robots", "lego"],
        "city": "Tampere",
    },
)


def _kid(spec: dict[str, Any]) -> KidProfile:
    return KidProfile(
        id=str(spec["id"]),
        name=str(spec["name"]),
        age=int(spec["age"]),
        wishlist=[str(spec["wish"])],
    )


def _preview(text: str, limit: int = 140) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _mood_label(mood: str) -> str:
    tag = (mood or "warm").strip()
    return tag[:1].upper() + tag[1:].lower() if tag else "Warm"


def catalog_entry(spec: dict[str, Any], card_dir: Path) -> dict[str, Any]:
    """Build one catalog row from a generated ``card.json`` (and optional MP4)."""
    payload: dict[str, Any] = {}
    card_json = card_dir / "card.json"
    if card_json.is_file():
        try:
            loaded = json.loads(card_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            payload = loaded
    rec = payload.get("recommendation") if isinstance(payload.get("recommendation"), dict) else {}
    gifts = rec.get("gifts") if isinstance(rec.get("gifts"), list) else []
    wish = payload.get("wish") if isinstance(payload.get("wish"), dict) else {}
    letter = str(wish.get("text") or spec["wish"])
    return {
        "id": spec["id"],
        "name": spec["name"],
        "age": spec["age"],
        "wish": _preview(letter),
        "tags": list(spec["tags"]),
        "mood": _mood_label(str(wish.get("mood") or "warm")),
        "city": spec["city"],
        "gift": str(gifts[0]) if gifts else "",
        "has_video": (card_dir / "video.mp4").is_file(),
        "src": spec["id"],
    }


def write_catalog(
    dest: Path, kids: tuple[dict[str, Any], ...] | None = None
) -> list[dict[str, Any]]:
    rows = [catalog_entry(spec, dest / str(spec["id"])) for spec in (kids or GALLERY_KIDS)]
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "catalog.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    return rows


def write_cards(
    *,
    dest: Path,
    kids: tuple[dict[str, Any], ...] | None = None,
    force: bool = False,
    make_card_fn: Callable[..., Any] | None = None,
    settings: Any = None,
) -> dict[str, int]:
    """Call ``make_card`` for each kid. Skip existing ``card.png`` unless ``force``."""
    from santa.card import make_card
    from santa.config import Settings

    make = make_card_fn or make_card
    cfg = settings
    specs = kids or GALLERY_KIDS
    dest.mkdir(parents=True, exist_ok=True)
    written = 0
    skipped = 0
    for spec in specs:
        png = dest / str(spec["id"]) / "card.png"
        if png.is_file() and not force:
            skipped += 1
            print(f"  skip card {spec['id']} ({spec['name']})")
            continue
        if cfg is None:
            cfg = Settings.load()
        kid = _kid(spec)
        print(f"  card {spec['id']}: {kid.name}, {kid.age} — {spec['wish']}")
        make(kid, cfg, out_root=dest)
        written += 1
    return {"written": written, "skipped": skipped, "total": len(specs)}


def write_videos(
    *,
    dest: Path,
    kids: tuple[dict[str, Any], ...] | None = None,
    force: bool = False,
    animate_fn: Callable[..., Any] | None = None,
    settings: Any = None,
) -> dict[str, int]:
    """``santa animate --mood-bank`` each card. Skip existing MP4 unless ``force``."""
    from santa.animate import run as animate_run
    from santa.config import Settings

    animate = animate_fn or animate_run
    cfg = settings
    specs = kids or GALLERY_KIDS
    written = 0
    skipped = 0
    missing = 0
    for spec in specs:
        kid_dir = dest / str(spec["id"])
        png = kid_dir / "card.png"
        mp4 = kid_dir / "video.mp4"
        if not png.is_file():
            missing += 1
            print(f"  skip video {spec['id']}: no card.png")
            continue
        if mp4.is_file() and not force:
            skipped += 1
            print(f"  skip video {spec['id']}")
            continue
        if cfg is None:
            cfg = Settings.load()
        print(f"  animate {spec['id']}: {spec['name']}")
        animate(png, settings=cfg, mood_bank=True, out=mp4)
        written += 1
    return {"written": written, "skipped": skipped, "missing": missing, "total": len(specs)}


def install_gallery(src: Path, dest: Path = GALLERY_DIR) -> int:
    """Copy generated card + video files and catalog into the bundled gallery."""
    dest.mkdir(parents=True, exist_ok=True)
    copied = 0
    for spec in GALLERY_KIDS:
        src_dir = src / str(spec["id"])
        dest_dir = dest / str(spec["id"])
        dest_dir.mkdir(parents=True, exist_ok=True)
        for name in ("card.png", "card.html", "card.json", "video.mp4"):
            file = src_dir / name
            if file.is_file():
                shutil.copyfile(file, dest_dir / name)
                copied += 1
    catalog = src / "catalog.json"
    if catalog.is_file():
        shutil.copyfile(catalog, dest / "catalog.json")
        copied += 1
    else:
        write_catalog(dest)
        copied += 1
    return copied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_DEST,
        help="Directory for g1..g12 (default: out/gallery)",
    )
    parser.add_argument(
        "--skip-animate",
        action="store_true",
        help="Write GiftCards only; leave video.mp4 for a later pass.",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help=f"Copy {DEFAULT_DEST.name}/ into data/fallback/gallery/",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even when card.png / video.mp4 already exist.",
    )
    args = parser.parse_args(argv)
    dest = args.out
    print(f"Gallery cards → {dest}")
    cards = write_cards(dest=dest, force=args.force)
    print(f"  cards written={cards['written']} skipped={cards['skipped']}")
    if args.skip_animate:
        print("  videos skipped (--skip-animate)")
    else:
        print("Gallery videos → mood-bank")
        videos = write_videos(dest=dest, force=args.force)
        print(
            f"  videos written={videos['written']} skipped={videos['skipped']} "
            f"missing={videos['missing']}"
        )
    rows = write_catalog(dest)
    ready = sum(1 for row in rows if row["has_video"])
    print(f"  catalog {len(rows)} cards, {ready} with video → {dest / 'catalog.json'}")
    if args.install:
        n = install_gallery(dest)
        print(f"  installed {n} files → {GALLERY_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
