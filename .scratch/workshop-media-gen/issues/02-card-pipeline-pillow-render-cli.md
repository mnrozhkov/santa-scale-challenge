# 02: Step 3 — `santa card`: gift + wish (Token Factory) → image (their endpoint) → PNG + HTML

**What to build:** A participant runs `santa card --form` (or `--profile me.json`, or `--name/--age/--wish`) and gets `out/<id>/card.png` + `out/<id>/card.html` in under 15 s. Text comes from Token Factory, the illustration from the endpoint in `.env`; if either is down, the OpenAI fallback answers and the card metadata records it. No Chrome, no html2image: the PNG is composed with Pillow; the HTML has OG tags so the card is shareable.

**Blocked by:** 01

**Status:** ready-for-human

- [x] `santa/card.py`: `make_card(profile, settings) -> GiftCard` — gift rec → wish → image prompt → image → render; tools `recommend_gift`, `write_wish`, `generate_image`, `save_card` exposed as plain functions (agent reuses them)
- [x] `santa/render.py`: Pillow renderer (illustration + name + wish + gifts, bundled font) → PNG; Jinja HTML with OG tags + embedded PNG path
- [x] `santa card --form | --profile | --name --age --wish [--out]`; validation before any model call (name non-empty, age 1–18); prints which model answered each role (primary/fallback)
- [x] `scripts/make_fallbacks.py` regenerates `data/fallback/cards/*.png|html` (4 real cards) — replaces the 1×1 placeholders
- [x] Tests: GiftCard from fakes, image attributed to configured endpoint, primary failure → fallback recorded, render produces PNG of expected size, invalid profile rejected before adapters are constructed
