#!/usr/bin/env python3
"""Regenerate ``data/fallback/cards/*.png|html`` — four real cards, not 1×1 placeholders.

Default path paints synthetic illustrations with Pillow so CI never needs APIs.
``--live`` calls the llm + image roles (requires a configured ``.env``).
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from santa.config import REPO_ROOT
from santa.render import write_card
from santa.schemas import GiftRecommendation, KidProfile, Wish

DEST = REPO_ROOT / "data" / "fallback" / "cards"

_KIDS: list[tuple[str, int, list[str], str, str, tuple[int, int, int]]] = [
    (
        "Mia",
        7,
        ["wooden train", "picture book"],
        "warm",
        "Dear Mia, may your wooden train race through the snow tonight. Merry Christmas!",
        (20, 48, 92),
    ),
    (
        "Leo",
        5,
        ["dinosaur puzzle", "soft blanket"],
        "playful",
        "Dear Leo, a roar of joy is packed with your gifts this year. Merry Christmas!",
        (18, 64, 42),
    ),
    (
        "Nora",
        10,
        ["telescope", "star chart"],
        "dreamy",
        "Dear Nora, the night sky has a new star with your name on it. Merry Christmas!",
        (48, 24, 72),
    ),
    (
        "Sam",
        8,
        ["baking set", "cocoa mug"],
        "cozy",
        "Dear Sam, the kitchen will smell of cinnamon and kindness. Merry Christmas!",
        (92, 28, 28),
    ),
]


def synthetic_illustration(sky: tuple[int, int, int], accent: tuple[int, int, int]) -> bytes:
    """A 1024×1024 night scene: sky, moon, tree, wrapped gift. No faces, no text."""
    im = Image.new("RGB", (1024, 1024), sky)
    draw = ImageDraw.Draw(im)
    # snow ground
    draw.ellipse([(-80, 720), (1100, 1200)], fill=(232, 240, 248))
    # moon
    draw.ellipse([(740, 80), (920, 260)], fill=(255, 244, 200))
    draw.ellipse([(780, 70), (930, 220)], fill=sky)
    # stars
    for x, y, r in ((80, 90, 4), (180, 160, 3), (400, 70, 5), (560, 140, 3), (300, 220, 4)):
        draw.regular_polygon((x, y, r + 6), 4, fill=(255, 250, 220))
    # tree
    for top, half in ((280, 90), (360, 130), (460, 170)):
        draw.polygon(
            [(512, top), (512 - half, top + 140), (512 + half, top + 140)], fill=(18, 90, 48)
        )
    draw.rectangle([(492, 600), (532, 760)], fill=(92, 58, 32))
    # gift
    gx, gy = 300, 780
    draw.rounded_rectangle([gx, gy, gx + 160, gy + 140], radius=12, fill=accent)
    draw.rectangle([gx + 70, gy, gx + 90, gy + 140], fill=(212, 175, 55))
    draw.rectangle([gx, gy + 50, gx + 160, gy + 70], fill=(212, 175, 55))
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _write_one(i: int, kid: KidProfile, rec: GiftRecommendation, wish: Wish, png: bytes) -> None:
    stem = f"card-{i:02d}"
    write_card(DEST, png, kid, rec, wish, stem=stem)
    print(f"  {stem}: {kid.name}")


def write_synthetic() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for i, (name, age, gifts, mood, text, sky) in enumerate(_KIDS, start=1):
        kid = KidProfile(name=name, age=age, wishlist=gifts)
        rec = GiftRecommendation(
            kid_id=kid.id, gifts=gifts, rationale="bundled fallback", model_version="synthetic"
        )
        wish = Wish(kid_id=kid.id, text=text, mood=mood, model_version="synthetic")
        accent = (180, 32, 32) if i % 2 else (32, 96, 160)
        _write_one(i, kid, rec, wish, synthetic_illustration(sky, accent))


def write_live() -> None:
    import shutil

    from santa.card import make_card
    from santa.config import Settings

    settings = Settings.load()
    DEST.mkdir(parents=True, exist_ok=True)
    live_root = DEST / "_live"
    for i, (name, age, gifts, _mood, _text, _sky) in enumerate(_KIDS, start=1):
        kid = KidProfile(name=name, age=age, wishlist=gifts)
        run = make_card(kid, settings, out_root=live_root)
        stem = f"card-{i:02d}"
        png_dest = DEST / f"{stem}.png"
        html_dest = DEST / f"{stem}.html"
        shutil.copy(run.card.png_path, png_dest)
        html_dest.write_text(
            Path(run.card.html_path).read_text(encoding="utf-8").replace("card.png", png_dest.name),
            encoding="utf-8",
        )
        print(f"  {stem}: {kid.name} (live)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call llm + image roles (needs .env). Default: synthetic Pillow art.",
    )
    args = parser.parse_args(argv)
    print(f"Writing fallback cards → {DEST}")
    write_live() if args.live else write_synthetic()
    return 0


if __name__ == "__main__":
    sys.exit(main())
