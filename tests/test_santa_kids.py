"""Kid CSV generator: 200 profiles, santa schema, load_kids round-trip."""

from __future__ import annotations

import random
from pathlib import Path

from santa.batch import load_kids
from santa.config import REPO_ROOT
from santa.kids import generate_kids, generate_kids_csv

COMMITTED = REPO_ROOT / "data" / "kids.csv"


def test_generate_kids_200_valid_unique_profiles() -> None:
    kids = generate_kids(200, rng=random.Random(0))
    assert len(kids) == 200
    assert len({k.id for k in kids}) == 200
    for kid in kids:
        assert 1 <= kid.age <= 18
        assert kid.name.strip()
        assert kid.wishlist and all(w.strip() for w in kid.wishlist)


def test_generate_kids_csv_is_deterministic(tmp_path: Path) -> None:
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    generate_kids_csv(a, 200, rng=random.Random(7))
    generate_kids_csv(b, 200, rng=random.Random(7))
    assert a.read_bytes() == b.read_bytes()


def test_load_kids_reads_generated_csv(tmp_path: Path) -> None:
    path = tmp_path / "kids.csv"
    generate_kids_csv(path, 200, rng=random.Random(1))
    kids = load_kids(path, 200)
    assert len(kids) == 200


def test_committed_kids_csv_has_200_rows() -> None:
    lines = [ln for ln in COMMITTED.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 201
    assert lines[0] == "id,name,age,wishlist"
    kids = load_kids(COMMITTED, 200)
    assert len(kids) == 200
    assert kids[0].id == "k01" and kids[0].name == "Emma"
    assert kids[0].wishlist == ["a telescope"]
    assert kids[23].id == "k24" and kids[23].name == "Alma"
