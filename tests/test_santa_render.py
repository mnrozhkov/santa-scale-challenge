"""Pillow PNG is a shareable card: 1024×1400, HTML has OG tags. No network."""

from __future__ import annotations

import base64
import io

from PIL import Image

from santa.render import CARD_SIZE, render_png, write_card
from santa.schemas import GiftRecommendation, KidProfile, Wish

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _kid() -> KidProfile:
    return KidProfile(name="Mia", age=7, wishlist=["trains"])


def _rec(kid: KidProfile) -> GiftRecommendation:
    return GiftRecommendation(
        kid_id=kid.id,
        gifts=["wooden train", "storybook"],
        rationale="loves trains",
        model_version="fake-llm",
    )


def _wish(kid: KidProfile) -> Wish:
    return Wish(
        kid_id=kid.id,
        text="Dear Mia, may your wooden train race through the snow. Merry Christmas!",
        mood="warm",
        model_version="fake-llm",
    )


def test_render_png_is_1024_by_1400() -> None:
    kid = _kid()
    png = render_png(PNG_1PX, kid, _rec(kid), _wish(kid))
    im = Image.open(io.BytesIO(png))
    assert im.size == CARD_SIZE == (1024, 1400)
    assert im.format == "PNG"


def test_bundled_font_is_truetype() -> None:
    from PIL import ImageFont

    from santa.render import BUNDLED_FONT, _font

    assert BUNDLED_FONT.is_file()
    assert isinstance(_font(28), ImageFont.FreeTypeFont)


def test_write_card_html_has_og_tags(tmp_path) -> None:
    kid = _kid()
    png_path, html_path = write_card(tmp_path, PNG_1PX, kid, _rec(kid), _wish(kid))
    html = html_path.read_text(encoding="utf-8")
    assert png_path.name == "card.png" and png_path.exists()
    assert 'property="og:image"' in html and "card.png" in html
    assert 'property="og:title"' in html and "Mia" in html
    assert "wooden train" in html
    assert Image.open(png_path).size == (1024, 1400)


def test_committed_fallback_cards_are_full_size_with_og_html() -> None:
    from santa.config import REPO_ROOT

    root = REPO_ROOT / "data" / "fallback" / "cards"
    pngs = sorted(root.glob("card-*.png"))
    assert len(pngs) == 4
    for png in pngs:
        assert Image.open(png).size == CARD_SIZE
        html = png.with_suffix(".html").read_text(encoding="utf-8")
        assert 'property="og:image"' in html and png.name in html
        assert 'property="og:title"' in html
