"""Pillow PNG + Jinja HTML. No Chrome, no html2image.

The raster is 1024×1400: illustration on top, then the child's name, wish, and gifts.
HTML is a shareable page with Open Graph tags pointing at ``card.png``.
"""

from __future__ import annotations

import io
import textwrap
from pathlib import Path

from jinja2 import Template
from PIL import Image, ImageDraw, ImageFont

from santa.schemas import GiftRecommendation, KidProfile, Wish

CARD_SIZE = (1024, 1400)
_ILLUSTRATION_BOX = (944, 720)
_BG = "#fffaf2"
_INK = "#2c3e50"
_RED = "#b30000"
_GOLD = "#c9a227"

_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/Library/Fonts/DejaVuSans.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
)

_HTML = Template(
    """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta property="og:title" content="A Christmas card for {{ name }}">
<meta property="og:description" content="{{ wish }}">
<meta property="og:image" content="{{ png_name }}">
<meta property="og:type" content="website">
<title>A Christmas card for {{ name }}</title>
<style>
  body { font-family: Georgia, serif; background: #1a3a2a; color: #fffaf2; margin: 0; padding: 2rem; }
  .card { max-width: 32rem; margin: 0 auto; background: #fffaf2; color: #2c3e50; border: 10px solid #b30000;
          border-radius: 16px; overflow: hidden; }
  img { display: block; width: 100%; }
  .body { padding: 1.5rem 2rem 2rem; }
  h1 { font-family: Georgia, serif; color: #b30000; margin: 0 0 1rem; }
  .wish { font-size: 1.15rem; line-height: 1.5; }
  .gifts { margin: 1.25rem 0 0; padding: 0; list-style: none; }
  .gifts li { padding: 0.2rem 0; }
  .sig { margin-top: 1.5rem; color: #b30000; font-style: italic; }
</style>
</head>
<body>
<article class="card">
  <img src="{{ png_name }}" alt="Holiday illustration for {{ name }}">
  <div class="body">
    <h1>To: {{ name }}</h1>
    <p class="wish">{{ wish }}</p>
    <ul class="gifts">
    {% for gift in gifts %}<li>{{ gift }}</li>
    {% endfor %}</ul>
    <p class="sig">— Santa</p>
  </div>
</article>
</body>
</html>
"""
)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    return ImageFont.load_default()


def _fit(im: Image.Image, box: tuple[int, int]) -> Image.Image:
    """Scale ``im`` to fill ``box`` (cover), then centre-crop."""
    bw, bh = box
    scale = max(bw / im.width, bh / im.height)
    resized = im.resize(
        (max(1, round(im.width * scale)), max(1, round(im.height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = (resized.width - bw) // 2
    top = (resized.height - bh) // 2
    return resized.crop((left, top, left + bw, top + bh))


def render_png(illustration: bytes, kid: KidProfile, rec: GiftRecommendation, wish: Wish) -> bytes:
    """Compose a 1024×1400 PNG: illustration + name + wish + gifts."""
    w, h = CARD_SIZE
    card = Image.new("RGB", CARD_SIZE, _BG)
    draw = ImageDraw.Draw(card)
    draw.rectangle([6, 6, w - 7, h - 7], outline=_RED, width=14)
    draw.rectangle([20, 20, w - 21, h - 21], outline=_GOLD, width=3)

    ill = Image.open(io.BytesIO(illustration)).convert("RGB")
    fitted = _fit(ill, _ILLUSTRATION_BOX)
    card.paste(fitted, (40, 40))

    title_font = _font(48)
    body_font = _font(28)
    gift_font = _font(24)
    y = 40 + _ILLUSTRATION_BOX[1] + 28
    draw.text((48, y), f"To: {kid.name}", fill=_RED, font=title_font)
    y += 64

    for line in textwrap.wrap(wish.text, width=42)[:8]:
        draw.text((48, y), line, fill=_INK, font=body_font)
        y += 36
    y += 16
    for gift in rec.gifts[:5]:
        draw.text((48, y), f"• {gift}", fill=_INK, font=gift_font)
        y += 34

    buf = io.BytesIO()
    card.save(buf, format="PNG")
    return buf.getvalue()


def write_card(
    out_dir: Path,
    illustration: bytes,
    kid: KidProfile,
    rec: GiftRecommendation,
    wish: Wish,
    *,
    stem: str = "card",
) -> tuple[Path, Path]:
    """Write ``{stem}.png`` and ``{stem}.html`` into ``out_dir``. Returns both paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    png_path = out_dir / f"{stem}.png"
    html_path = out_dir / f"{stem}.html"
    png_path.write_bytes(render_png(illustration, kid, rec, wish))
    html_path.write_text(
        _HTML.render(name=kid.name, wish=wish.text, gifts=rec.gifts, png_name=png_path.name),
        encoding="utf-8",
    )
    return png_path, html_path
