"""``santa batch``: cards phase then K GPU Jobs → ``run_summary.json``."""

from __future__ import annotations

import asyncio
import csv
import json
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol

from santa.config import REPO_ROOT, Settings
from santa.cost import cost_usd, on_demand_cost_usd
from santa.nebius_jobs import (
    JobPayload,
    JobService,
    JobWait,
    NebiusJobError,
    cancel_job,
    job_payload,
    wait_for_job,
)
from santa.schemas import KidProfile

DEFAULT_KIDS_CSV = REPO_ROOT / "data" / "kids.csv"


class StorageLike(Protocol):
    def exists(self, key: str) -> bool:
        ...

    def list(self, prefix: str = "") -> list[str]:
        ...

    def upload(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        ...

    def download(self, key: str) -> bytes:
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
            name = (row.get("name") or "").strip()
            if not name:
                continue
            age_raw = (row.get("age") or "8").strip() or "8"
            wish = (row.get("wishlist") or "").strip()
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
    existing = set(storage.list("cards/"))
    todo, skipped = [], []
    for kid in kids:
        if f"cards/{kid.id}.png" in existing:
            skipped.append(kid.id)
        else:
            todo.append(kid)
    return todo, skipped


def ids_missing_videos(ids: list[str], storage: StorageLike) -> tuple[list[str], list[str]]:
    """Ids whose ``videos/{id}.mp4`` is missing, plus those already on the bucket."""
    existing = set(storage.list("videos/"))
    missing, have = [], []
    for kid_id in ids:
        if f"videos/{kid_id}.mp4" in existing:
            have.append(kid_id)
        else:
            missing.append(kid_id)
    return missing, have


def mood_from_storage(storage: StorageLike, kid_id: str) -> str:
    """Read ``wish.mood`` from ``cards/{id}.json`` in the bucket; default ``warm``."""
    try:
        raw = storage.download(f"cards/{kid_id}.json")
    except Exception:
        return "warm"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "warm"
    if not isinstance(data, dict):
        return "warm"
    wish = data.get("wish")
    if isinstance(wish, dict) and wish.get("mood"):
        return str(wish["mood"])
    return str(data.get("mood") or "warm")


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
    local: bool = False,
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
            moods[kid.id] = mood_from_storage(storage, kid.id)
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
    for kid_id in skipped:
        moods[kid_id] = mood_from_storage(storage, kid_id)
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


@dataclass
class JobRecord:
    """One GPU job as it appears in ``run_summary.json``."""

    job_id: str
    chunk: str
    platform: str
    preset: str
    preemptible: bool
    state_transitions: list[dict[str, Any]]
    run_s: float
    done: list[str]
    skipped: list[str]
    failed: list[str]
    cost_usd: float = 0.0
    on_demand_cost_usd: float = 0.0

    def with_costs(self) -> JobRecord:
        return replace(
            self,
            cost_usd=cost_usd(self.platform, self.preset, self.run_s, preemptible=self.preemptible),
            on_demand_cost_usd=on_demand_cost_usd(self.platform, self.preset, self.run_s),
        )

    def as_dict(self) -> dict[str, Any]:
        rec = self.with_costs()
        return {
            "job_id": rec.job_id,
            "chunk": rec.chunk,
            "platform": rec.platform,
            "preset": rec.preset,
            "preemptible": rec.preemptible,
            "state_transitions": rec.state_transitions,
            "run_s": rec.run_s,
            "cost_usd": rec.cost_usd,
            "on_demand_cost_usd": rec.on_demand_cost_usd,
            "done": rec.done,
            "skipped": rec.skipped,
            "failed": rec.failed,
        }


def build_run_summary(run_id: str, kids: list[str], jobs: list[JobRecord]) -> dict[str, Any]:
    """Assemble ``run_summary.json``: per-job cost, totals, preemptible savings."""
    priced = [j.with_costs() for j in jobs]
    done = sum(len(j.done) for j in priced)
    skipped = sum(len(j.skipped) for j in priced)
    failed = sum(len(j.failed) for j in priced)
    cost = round(sum(j.cost_usd for j in priced), 6)
    on_demand = round(sum(j.on_demand_cost_usd for j in priced), 6)
    return {
        "run_id": run_id,
        "kids": kids,
        "jobs": [j.as_dict() for j in priced],
        "totals": {
            "done": done,
            "skipped": skipped,
            "failed": failed,
            "run_s": round(sum(j.run_s for j in priced), 3),
            "cost_usd": cost,
            "on_demand_cost_usd": on_demand,
        },
        "savings_usd": round(on_demand - cost, 6),
    }


def _chunk_rows(path: Path) -> list[dict[str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [row for row in raw if isinstance(row, dict) and row.get("id")]


def _write_json(
    run_dir: Path, name: str, run_id: str, storage: StorageLike, payload: dict[str, Any]
) -> Path:
    path = run_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2) + "\n"
    path.write_text(data, encoding="utf-8")
    storage.upload(f"runs/{run_id}/{name}", data.encode(), content_type="application/json")
    return path


def _ids_from_status(
    storage: StorageLike,
    run_id: str,
    chunk_k: str,
    chunk_ids: list[str],
    *,
    job_failed: bool,
) -> tuple[list[str], list[str], list[str]]:
    try:
        raw = json.loads(storage.download(f"runs/{run_id}/jobs/{chunk_k}.json"))
    except Exception:
        return ([], [], list(chunk_ids)) if job_failed else ([], [], [])
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return ([], [], list(chunk_ids)) if job_failed else ([], [], [])
    done = [str(i["id"]) for i in items if isinstance(i, dict) and i.get("status") == "done"]
    skipped = [str(i["id"]) for i in items if isinstance(i, dict) and i.get("status") == "skipped"]
    failed = [str(i["id"]) for i in items if isinstance(i, dict) and i.get("status") == "failed"]
    if job_failed:
        seen = set(done + skipped + failed)
        failed = failed + [i for i in chunk_ids if i not in seen]
    return done, skipped, failed


def _wait_result(result: JobWait | NebiusJobError | BaseException) -> tuple[JobWait | None, bool]:
    if isinstance(result, NebiusJobError):
        return result.wait, True
    if isinstance(result, JobWait):
        fail = result.state.upper() in {"FAILED", "ERROR", "CANCELLED", "CANCELED"}
        return result, fail
    return None, True


def _wait_jobs(
    service: JobService,
    job_ids: list[str],
    *,
    poll_s: float,
    sleep: Callable[[float], None],
    on_state: Callable[[str, str], None] | None,
) -> list[JobWait | NebiusJobError]:
    async def one(jid: str) -> JobWait | NebiusJobError:
        try:
            return await asyncio.to_thread(
                wait_for_job,
                service,
                jid,
                poll_s=poll_s,
                sleep=sleep,
                on_state=on_state,
            )
        except NebiusJobError as exc:
            return exc

    async def all_jobs() -> list[JobWait | NebiusJobError]:
        raw = await asyncio.gather(*[one(j) for j in job_ids], return_exceptions=True)
        out: list[JobWait | NebiusJobError] = []
        for item in raw:
            if isinstance(item, KeyboardInterrupt):
                raise item
            if isinstance(item, asyncio.CancelledError):
                raise KeyboardInterrupt()
            if isinstance(item, BaseException) and not isinstance(item, NebiusJobError):
                raise item
            out.append(item)
        return out

    return asyncio.run(all_jobs())


def _create_jobs(service: JobService, payloads: list[JobPayload]) -> list[str]:
    async def one(payload: JobPayload) -> str:
        return await asyncio.to_thread(service.create, payload)

    async def all_creates() -> list[str]:
        raw = await asyncio.gather(*[one(p) for p in payloads], return_exceptions=True)
        ids: list[str] = []
        for item in raw:
            if isinstance(item, BaseException):
                for jid in ids:
                    cancel_job(service, jid)
                raise item
            ids.append(str(item))
        return ids

    return asyncio.run(all_creates())


def run_jobs_phase(
    *,
    kids: list[str],
    n_jobs: int,
    run_id: str,
    run_dir: Path,
    storage: StorageLike,
    settings: Settings,
    service: JobService,
    wait: bool = True,
    poll_s: float = 5.0,
    sleep: Callable[[float], None] | None = None,
    on_state: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Filter existing videos, chunk the rest, submit K jobs, wait, write ``summary.json``."""
    sleeper = sleep if sleep is not None else time.sleep
    missing, _have = ids_missing_videos(kids, storage)
    moods = {i: mood_from_storage(storage, i) for i in missing}
    packed = [
        [{"id": i, "mood": moods.get(i, "warm")} for i in ch] for ch in chunk_ids(missing, n_jobs)
    ]
    paths = write_chunks(run_dir, packed)
    for path in paths:
        storage.upload(
            f"runs/{run_id}/chunks/{path.name}",
            path.read_bytes(),
            content_type="application/json",
        )
    payloads: list[JobPayload] = []
    for path in paths:
        chunk_key = f"runs/{run_id}/chunks/{path.name}"
        payloads.append(
            job_payload(
                settings, run_id=run_id, chunk=chunk_key, name=f"santa-{run_id}-{path.stem}"
            )
        )
    job_ids = _create_jobs(service, payloads) if payloads else []
    submitted = list(zip(paths, job_ids, payloads, strict=True))
    ticket = {
        "run_id": run_id,
        "kids": kids,
        "jobs": [
            {
                "job_id": jid,
                "chunk": f"runs/{run_id}/chunks/{path.name}",
                "ids": [str(r["id"]) for r in _chunk_rows(path)],
            }
            for path, jid, _ in submitted
        ],
        "platform": settings.job.platform,
        "preset": settings.job.preset,
        "preemptible": settings.job.preemptible,
    }
    _write_json(run_dir, "ticket.json", run_id, storage, ticket)
    if not wait:
        return {"run_id": run_id, "kids": kids, "jobs": ticket["jobs"], "waiting": True}
    try:
        waits = _wait_jobs(
            service,
            [jid for _, jid, _ in submitted],
            poll_s=poll_s,
            sleep=sleeper,
            on_state=on_state,
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        for _, jid, _ in submitted:
            cancel_job(service, jid)
        raise
    records: list[JobRecord] = []
    for (path, jid, payload), result in zip(submitted, waits, strict=True):
        wait_obj, failed_job = _wait_result(result)
        ids = [str(r["id"]) for r in _chunk_rows(path)]
        done, skipped, failed = _ids_from_status(
            storage, run_id, path.stem, ids, job_failed=failed_job
        )
        transitions = (
            [{"state": t.state, "at": t.at} for t in wait_obj.timeline] if wait_obj else []
        )
        records.append(
            JobRecord(
                job_id=jid,
                chunk=f"runs/{run_id}/chunks/{path.name}",
                platform=payload.platform,
                preset=payload.preset,
                preemptible=payload.preemptible,
                state_transitions=transitions,
                run_s=wait_obj.run_s if wait_obj else 0.0,
                done=done,
                skipped=skipped,
                failed=failed,
            )
        )
    summary = build_run_summary(run_id, kids, records)
    _write_json(run_dir, "summary.json", run_id, storage, summary)
    return summary


def resume_jobs_phase(
    *,
    ticket: dict[str, Any],
    run_dir: Path,
    storage: StorageLike,
    settings: Settings,
    service: JobService,
    poll_s: float = 5.0,
    sleep: Callable[[float], None] | None = None,
    on_state: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Resume ``--no-wait``: poll ticket job ids, then write ``summary.json``."""
    sleeper = sleep if sleep is not None else time.sleep
    run_id = str(ticket["run_id"])
    jobs_meta = list(ticket.get("jobs") or [])
    job_ids = [str(j["job_id"]) for j in jobs_meta]
    try:
        waits = _wait_jobs(service, job_ids, poll_s=poll_s, sleep=sleeper, on_state=on_state)
    except (KeyboardInterrupt, asyncio.CancelledError):
        for jid in job_ids:
            cancel_job(service, jid)
        raise
    spec = settings.job
    records: list[JobRecord] = []
    for meta, result in zip(jobs_meta, waits, strict=True):
        wait_obj, failed_job = _wait_result(result)
        ids = [str(i) for i in (meta.get("ids") or [])]
        chunk = str(meta["chunk"])
        done, skipped, failed = _ids_from_status(
            storage, run_id, Path(chunk).stem, ids, job_failed=failed_job
        )
        transitions = (
            [{"state": t.state, "at": t.at} for t in wait_obj.timeline] if wait_obj else []
        )
        records.append(
            JobRecord(
                job_id=str(meta["job_id"]),
                chunk=chunk,
                platform=str(ticket.get("platform") or spec.platform),
                preset=str(ticket.get("preset") or spec.preset),
                preemptible=bool(ticket.get("preemptible", spec.preemptible)),
                state_transitions=transitions,
                run_s=wait_obj.run_s if wait_obj else 0.0,
                done=done,
                skipped=skipped,
                failed=failed,
            )
        )
    kids = [str(k) for k in (ticket.get("kids") or [])]
    summary = build_run_summary(run_id, kids, records)
    _write_json(run_dir, "summary.json", run_id, storage, summary)
    return summary


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
