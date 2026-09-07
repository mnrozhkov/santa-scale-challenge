"""``santa batch`` cards phase: pick kids, make cards, upload, write job chunks.

GPU job submission (issue 09) uses the payloads and ``create_and_wait`` from
``santa.nebius_jobs``.
"""

from __future__ import annotations

import csv
import json
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from santa.config import REPO_ROOT, Settings
from santa.schemas import KidProfile

DEFAULT_KIDS_CSV = REPO_ROOT / "data" / "kids.csv"


class StorageLike(Protocol):
    def exists(self, key: str) -> bool:
        ...

    def upload(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        ...


def chunk_ids(ids: list[str], k: int) -> list[list[str]]:
    """Split ``ids`` into ``k`` consecutive chunks. Empty trailing chunks are dropped."""
    if k < 1:
        raise ValueError("jobs must be >= 1")
    n = len(ids)
    if n == 0:
        return []
    k = min(k, n)
    base, extra = divmod(n, k)
    chunks: list[list[str]] = []
    i = 0
    for c in range(k):
        size = base + (1 if c < extra else 0)
        chunks.append(ids[i : i + size])
        i += size
    return chunks


def load_kids(path: Path | str, n: int) -> list[KidProfile]:
    """Read the first ``n`` kid profiles from a CSV (columns: id, name, age, wishlist)."""
    p = Path(path)
    kids: list[KidProfile] = []
    with p.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if len(kids) >= n:
                break
            name = (row.get("name") or row.get("Your Name (Optional)") or "").strip()
            if not name:
                continue
            age_raw = (row.get("age") or "8").strip() or "8"
            wish = (
                row.get("wishlist") or row.get("What did you want for Christmas as a child?") or ""
            ).strip()
            kid_id = (row.get("id") or "").strip() or str(uuid.uuid4())
            kids.append(
                KidProfile(
                    id=kid_id,
                    name=name,
                    age=int(age_raw),
                    wishlist=[wish] if wish else [],
                )
            )
    if len(kids) < n:
        raise ValueError(f"{p} has {len(kids)} usable rows; need {n}")
    return kids


def skip_existing(
    kids: list[KidProfile], storage: StorageLike
) -> tuple[list[KidProfile], list[str]]:
    """Kids whose ``cards/{id}.png`` already exists are skipped."""
    todo, skipped = [], []
    for kid in kids:
        if storage.exists(f"cards/{kid.id}.png"):
            skipped.append(kid.id)
        else:
            todo.append(kid)
    return todo, skipped


def write_chunks(run_dir: Path, chunks: list[list[dict[str, str]]]) -> list[Path]:
    """Write ``runs/<run_id>/chunks/<k>.json`` — list of ``{id, mood}``."""
    dest = run_dir / "chunks"
    dest.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, chunk in enumerate(chunks):
        path = dest / f"{i}.json"
        path.write_text(json.dumps(chunk, indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


@dataclass
class CardsPhase:
    run_id: str
    run_dir: Path
    kids: list[str]
    made: list[str]
    skipped: list[str]
    chunks: list[Path] = field(default_factory=list)
    used_service: bool = False


def run_cards_phase(
    *,
    kids: list[KidProfile],
    n_jobs: int,
    run_id: str,
    run_dir: Path,
    storage: StorageLike,
    settings: Settings,
    local: bool = True,
    service_url: str = "",
    make_card: Callable[..., Any] | None = None,
    post_batch: Callable[[str, list[KidProfile]], list[str]] | None = None,
    max_workers: int = 4,
) -> CardsPhase:
    """Select kids → cards (service or local) → upload → chunk files."""
    todo, skipped = skip_existing(kids, storage)
    made: list[str] = []
    moods: dict[str, str] = {}
    use_service = bool(service_url) and not local
    if use_service:
        post = post_batch or _post_service_batch
        ids = post(service_url, todo)
        made = list(ids)
        for kid in todo:
            moods[kid.id] = "warm"
    else:
        from santa.card import make_card as _make

        fn = make_card or _make
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futs = {
                pool.submit(_local_one, kid, settings, run_dir, storage, fn): kid for kid in todo
            }
            for fut in as_completed(futs):
                kid_id, mood = fut.result()
                made.append(kid_id)
                moods[kid_id] = mood
    ordered = [k.id for k in kids]
    chunk_lists = chunk_ids(ordered, n_jobs)
    packed = [[{"id": i, "mood": moods.get(i, "warm")} for i in ch] for ch in chunk_lists]
    paths = write_chunks(run_dir, packed)
    for path in paths:
        storage.upload(
            f"runs/{run_id}/chunks/{path.name}",
            path.read_bytes(),
            content_type="application/json",
        )
    return CardsPhase(
        run_id=run_id,
        run_dir=run_dir,
        kids=ordered,
        made=made,
        skipped=skipped,
        chunks=paths,
        used_service=use_service,
    )


def _local_one(
    kid: KidProfile,
    settings: Settings,
    run_dir: Path,
    storage: StorageLike,
    make_card: Callable[..., Any],
) -> tuple[str, str]:
    run = make_card(kid, settings, out_root=run_dir / "cards")
    png = Path(run.card.png_path)
    storage.upload(f"cards/{kid.id}.png", png.read_bytes(), content_type="image/png")
    html = run.card.html_path
    if html and Path(html).is_file():
        storage.upload(f"cards/{kid.id}.html", Path(html).read_bytes(), content_type="text/html")
    card_json = png.parent / "card.json"
    if card_json.is_file():
        storage.upload(
            f"cards/{kid.id}.json", card_json.read_bytes(), content_type="application/json"
        )
    mood = getattr(run.card.wish, "mood", None) or "warm"
    return kid.id, str(mood)


def _post_service_batch(url: str, kids: list[KidProfile]) -> list[str]:
    import requests

    resp = requests.post(
        f"{url.rstrip('/')}/api/cards/batch",
        json={"kids": [k.model_dump() for k in kids]},
        timeout=600,
    )
    resp.raise_for_status()
    data = resp.json()
    return [str(i) for i in data.get("ids") or []]
