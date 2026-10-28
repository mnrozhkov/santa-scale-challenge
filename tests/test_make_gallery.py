"""scripts/make_gallery.py: 12 demo GiftCards + catalog. No network."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from santa.schemas import KidProfile

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    path = ROOT / "scripts" / "make_gallery.py"
    spec = importlib.util.spec_from_file_location("make_gallery", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gallery_kids_are_twelve_distinct_identities() -> None:
    mod = _mod()
    ids = [kid["id"] for kid in mod.GALLERY_KIDS]
    assert ids == [f"g{i}" for i in range(1, 13)]
    assert len({kid["name"] for kid in mod.GALLERY_KIDS}) == 12
    ages = [kid["age"] for kid in mod.GALLERY_KIDS]
    assert any(3 <= age <= 5 for age in ages)
    assert any(6 <= age <= 8 for age in ages)
    assert any(9 <= age <= 12 for age in ages)
    tags = {tag for kid in mod.GALLERY_KIDS for tag in kid["tags"]}
    assert {"books", "lego", "art", "robots", "dinosaurs"}.issubset(tags)


def test_write_cards_and_videos_and_catalog(tmp_path: Path) -> None:
    mod = _mod()
    kids = tuple(mod.GALLERY_KIDS[:2])
    seen: list[str] = []

    def fake_make(kid: KidProfile, settings, *, out_root):
        dest = Path(out_root) / kid.id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "card.png").write_bytes(b"PNG")
        (dest / "card.html").write_text(f"<p>Dear {kid.name}</p>", encoding="utf-8")
        (dest / "card.json").write_text(
            json.dumps(
                {
                    "recommendation": {"gifts": [f"{kid.name} gift"]},
                    "wish": {
                        "text": f"Dear {kid.name}, a quiet wish. Merry Christmas!",
                        "mood": "playful",
                    },
                }
            ),
            encoding="utf-8",
        )
        seen.append(kid.id)
        return object()

    def fake_animate(png, *, settings, mood_bank, out):
        assert mood_bank is True
        Path(out).write_bytes(b"MP4")
        return Path(out)

    dest = tmp_path / "gallery"
    cards = mod.write_cards(dest=dest, kids=kids, make_card_fn=fake_make, settings=object())
    assert cards == {"written": 2, "skipped": 0, "total": 2}
    assert seen == ["g1", "g2"]

    videos = mod.write_videos(dest=dest, kids=kids, animate_fn=fake_animate, settings=object())
    assert videos == {"written": 2, "skipped": 0, "missing": 0, "total": 2}

    rows = mod.write_catalog(dest, kids)
    assert rows[0]["id"] == "g1"
    assert rows[0]["name"] == "Emma"
    assert rows[0]["gift"] == "Emma gift"
    assert rows[0]["mood"] == "Playful"
    assert rows[0]["has_video"] is True
    assert "Dear Emma" in rows[0]["wish"]
    assert (dest / "catalog.json").is_file()


def test_write_cards_skips_existing_unless_force(tmp_path: Path) -> None:
    mod = _mod()
    kids = (mod.GALLERY_KIDS[0],)
    dest = tmp_path / "gallery"
    png = dest / "g1" / "card.png"
    png.parent.mkdir(parents=True)
    png.write_bytes(b"OLD")
    calls = {"n": 0}

    def fake_make(*_args, **_kwargs):
        calls["n"] += 1
        raise AssertionError("should not remake")

    skipped = mod.write_cards(dest=dest, kids=kids, make_card_fn=fake_make, settings=object())
    assert skipped["skipped"] == 1
    assert skipped["written"] == 0
    assert png.read_bytes() == b"OLD"
    assert calls["n"] == 0

    def remake(kid: KidProfile, settings, *, out_root):
        path = Path(out_root) / kid.id / "card.png"
        path.write_bytes(b"NEW")
        return object()

    forced = mod.write_cards(
        dest=dest, kids=kids, force=True, make_card_fn=remake, settings=object()
    )
    assert forced["written"] == 1
    assert png.read_bytes() == b"NEW"


def test_install_gallery_copies_artifacts(tmp_path: Path) -> None:
    mod = _mod()
    src = tmp_path / "src"
    dest = tmp_path / "dest"
    kid = src / "g1"
    kid.mkdir(parents=True)
    (kid / "card.png").write_bytes(b"PNG")
    (kid / "video.mp4").write_bytes(b"MP4")
    (kid / "card.json").write_text("{}", encoding="utf-8")
    (src / "catalog.json").write_text("[]", encoding="utf-8")

    # Only g1 has files; install still walks all 12 ids.
    copied = mod.install_gallery(src, dest)
    assert (dest / "g1" / "card.png").read_bytes() == b"PNG"
    assert (dest / "g1" / "video.mp4").read_bytes() == b"MP4"
    assert (dest / "catalog.json").read_text(encoding="utf-8") == "[]"
    assert copied >= 3
