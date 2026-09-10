"""Service session — injectable card runner, adapters, and storage."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from santa.card import CardRun, ProfileError, make_card
from santa.config import REPO_ROOT, ConfigError, Settings
from santa.schemas import KidProfile
from santa.storage import (
    DiskStorage,
    StorageError,
    card_html_key,
    card_json_key,
    card_png_key,
    card_profile_key,
    card_video_key,
    id_from_card_png_key,
    storage_for_service,
)

CardRunner = Callable[..., CardRun]

_TAG_WORDS: dict[str, tuple[str, ...]] = {
    "space": ("space", "star", "telescope", "rocket", "planet", "astronaut"),
    "dinosaurs": ("dino", "t-rex", "trex", "fossil", "paleo"),
    "art": ("art", "paint", "watercolour", "watercolor", "canvas", "brush"),
    "music": ("music", "piano", "ukulele", "drum", "song", "guitar"),
    "football": ("football", "soccer", "ball", "goal"),
    "robots": ("robot", "coding", "code", "sensor", "program"),
    "animals": ("animal", "bunny", "elephant", "fox", "bunny", "plush"),
    "books": ("book", "story", "encyclopedia", "atlas", "read"),
    "lego": ("lego", "brick", "building block"),
    "ocean": ("ocean", "sea", "underwater", "fish", "sail"),
}


class StorageLike(Protocol):
    def upload(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        ...

    def exists(self, key: str) -> bool:
        ...

    def list(self, prefix: str = "") -> list[str]:
        ...

    def list_with_mtime(self, prefix: str = "") -> list[tuple[str, float]]:
        ...

    def download(self, key: str) -> bytes:
        ...


def _adapter_url(adapter: Any) -> str:
    cfg = getattr(adapter, "cfg", None)
    return str(getattr(cfg, "base_url", None) or getattr(adapter, "base_url", "") or "")


def _load_json(storage: StorageLike, key: str) -> dict[str, Any] | None:
    try:
        raw = json.loads(storage.download(key))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _name_from_wish(text: str) -> str:
    for prefix in ("Dear ", "Merry Christmas, "):
        if text.startswith(prefix):
            rest = text[len(prefix) :]
            name = rest.split(",")[0].split("!")[0].strip()
            name = re.sub(r"\s+", " ", name)
            if name and len(name) < 40:
                return name
    return ""


def _infer_tags(*parts: str) -> list[str]:
    blob = " ".join(parts).lower()
    found: list[str] = []
    for tag, words in _TAG_WORDS.items():
        if any(word in blob for word in words):
            found.append(tag)
    return found[:3]


def _mood_label(mood: str) -> str:
    raw = (mood or "warm").strip()
    if not raw:
        return "Warm"
    return raw[:1].upper() + raw[1:]


@dataclass
class BatchResult:
    ids: list[str]
    failures: list[dict[str, str]]


@dataclass
class ServiceSession:
    """Façade the FastAPI app drives. Tests inject fakes; production uses Settings + Storage."""

    settings: Settings
    storage: StorageLike
    llm: Any = None
    image: Any = None
    video: Any = None
    audio: Any = None
    job_service: Any = None
    card_runner: CardRunner = field(default=make_card)
    out_root: Path = field(default_factory=lambda: REPO_ROOT / "out")
    last_run: CardRun | None = None
    last_kid: KidProfile | None = None

    def __post_init__(self) -> None:
        url = _adapter_url(self.image)
        if not url:
            try:
                url = self.settings.role("image").base_url
            except ConfigError:
                url = ""
        if "recraft" in url.lower():
            raise ConfigError(
                "Image role points at Recraft. Set IMAGE_ENDPOINT_URL to the Serverless endpoint."
            )

    @classmethod
    def from_env(
        cls,
        *,
        settings: Settings | None = None,
        storage: StorageLike | None = None,
        llm: Any = None,
        image: Any = None,
        card_runner: CardRunner | None = None,
        out_root: Path | None = None,
        video: Any = None,
        audio: Any = None,
        job_service: Any = None,
    ) -> ServiceSession:
        resolved = settings or Settings.load()
        root = out_root or REPO_ROOT / "out"
        return cls(
            settings=resolved,
            storage=storage or storage_for_service(root),
            llm=llm,
            image=image,
            video=video,
            audio=audio,
            job_service=job_service,
            card_runner=card_runner or make_card,
            out_root=root,
        )

    def generate_card(self, kid: KidProfile) -> CardRun:
        run = self._run_card(kid)
        self.last_run = run
        self.last_kid = kid
        try:
            self._upload_card(kid.id, run, kid=kid)
        except StorageError:
            pass
        return run

    def generate_batch(self, kids: list[KidProfile], *, max_workers: int = 4) -> BatchResult:
        ids: list[str] = []
        failures: list[dict[str, str]] = []
        workers = max(1, min(max_workers, len(kids))) if kids else 1
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(self._run_and_upload, kid): kid for kid in kids}
            for fut in as_completed(futs):
                kid = futs[fut]
                try:
                    ids.append(fut.result())
                except Exception as exc:
                    failures.append({"id": kid.id, "error": str(exc)})
        return BatchResult(ids=ids, failures=failures)

    def _run_card(self, kid: KidProfile) -> CardRun:
        if not (kid.name or "").strip():
            raise ProfileError("Name is required.")
        return self.card_runner(
            kid,
            self.settings,
            out_root=self.out_root,
            llm=self.llm,
            image=self.image,
        )

    def _run_and_upload(self, kid: KidProfile) -> str:
        try:
            exists = self.storage.exists(card_png_key(kid.id))
        except StorageError:
            exists = False
        if exists:
            return kid.id
        run = self._run_card(kid)
        try:
            self._upload_card(kid.id, run, kid=kid)
        except StorageError:
            pass
        return kid.id

    def _upload_card(self, kid_id: str, run: CardRun, kid: KidProfile | None = None) -> None:
        png = Path(run.card.png_path) if run.card.png_path else None
        if png is not None and png.is_file():
            self.storage.upload(card_png_key(kid_id), png.read_bytes(), content_type="image/png")
        html = Path(run.card.html_path) if run.card.html_path else None
        if html is not None and html.is_file():
            self.storage.upload(card_html_key(kid_id), html.read_bytes(), content_type="text/html")
        json_path = png.parent / "card.json" if png is not None else None
        if json_path is not None and json_path.is_file():
            payload = json_path.read_bytes()
        else:
            payload = run.card.model_dump_json().encode()
        self.storage.upload(card_json_key(kid_id), payload, content_type="application/json")
        profile_path = png.parent / "profile.json" if png is not None else None
        if profile_path is not None and profile_path.is_file():
            self.storage.upload(
                card_profile_key(kid_id), profile_path.read_bytes(), content_type="application/json"
            )
        elif kid is not None:
            self.storage.upload(
                card_profile_key(kid_id),
                kid.model_dump_json().encode(),
                content_type="application/json",
            )

    def publish(self, filename: str, data: bytes, content_type: str = "") -> str:
        from santa.publish import content_type_for, object_key

        key = object_key(filename, content_type=content_type)
        stored_type = content_type or content_type_for(filename)
        if stored_type == "application/octet-stream":
            stored_type = "video/mp4" if key.endswith(".mp4") else "image/png"
        self.storage.upload(key, data, content_type=stored_type)
        return key

    def read_object(self, key: str) -> bytes:
        try:
            return self.storage.download(key)
        except StorageError:
            return DiskStorage(self.out_root).download(key)

    def wall(self) -> dict[str, Any]:
        try:
            return self._wall_from(self.storage)
        except StorageError:
            return self._wall_from(DiskStorage(self.out_root))

    def _wall_from(self, storage: StorageLike) -> dict[str, Any]:
        keys = storage.list("cards/")
        cards = [k for k in keys if k.endswith("/card.png")]
        videos = [k for k in keys if k.endswith("/video.mp4")]
        listed = storage.list_with_mtime("runs/")
        summaries = [(k, t) for k, t in listed if k.endswith("/summary.json")]
        summary: Any = None
        if summaries:
            key = max(summaries, key=lambda item: item[1])[0]
            summary = json.loads(storage.download(key))
        items = [self._wall_item(storage, kid_id, videos) for kid_id in _ids_from_png_keys(cards)]
        return {
            "cards": cards,
            "videos": videos,
            "items": items,
            "summary": summary,
            "counter": _wall_counter(summary),
        }

    def _wall_item(self, storage: StorageLike, kid_id: str, videos: list[str]) -> dict[str, Any]:
        png_key = card_png_key(kid_id)
        video_key = card_video_key(kid_id)
        has_video = video_key in videos or storage.exists(video_key)
        profile = _load_json(storage, card_profile_key(kid_id)) or {}
        card = _load_json(storage, card_json_key(kid_id)) or {}
        wish = card.get("wish") if isinstance(card.get("wish"), dict) else {}
        rec = card.get("recommendation") if isinstance(card.get("recommendation"), dict) else {}
        image = card.get("image") if isinstance(card.get("image"), dict) else {}
        gifts = rec.get("gifts") if isinstance(rec.get("gifts"), list) else []
        gift = str(gifts[0]) if gifts else ""
        wish_text = str(wish.get("text") or "")
        wishlist = profile.get("wishlist") if isinstance(profile.get("wishlist"), list) else []
        wish_line = str(wishlist[0]) if wishlist else wish_text
        name = str(profile.get("name") or "").strip() or _name_from_wish(wish_text) or kid_id[:8]
        age_raw = profile.get("age")
        try:
            age = int(age_raw) if age_raw is not None else 0
        except (TypeError, ValueError):
            age = 0
        mood = _mood_label(str(wish.get("mood") or "warm"))
        tags = _infer_tags(wish_line, gift, wish_text)
        return {
            "id": kid_id,
            "name": name,
            "age": age or 8,
            "wish": wish_line,
            "gift": gift,
            "mood": mood,
            "city": "",
            "tags": tags,
            "has_video": has_video,
            "png_url": f"/media/{png_key}",
            "video_url": f"/media/{video_key}" if has_video else None,
            "model": str(image.get("model_version") or ""),
        }

    def animate_card(self, kid_id: str, *, mood_bank: bool = True) -> dict[str, Any]:
        from santa.animate import run as animate_run

        png = self._ensure_local_png(kid_id)
        dest = animate_run(
            png,
            settings=self.settings,
            mood_bank=mood_bank,
            video=self.video,
            audio=self.audio,
        )
        path = Path(dest)
        if path.is_file():
            try:
                self.storage.upload(
                    card_video_key(kid_id), path.read_bytes(), content_type="video/mp4"
                )
            except StorageError:
                pass
        return {"id": kid_id, "video_url": f"/media/{card_video_key(kid_id)}"}

    def _ensure_local_png(self, kid_id: str) -> Path:
        png = self.out_root / kid_id / "card.png"
        if png.is_file():
            return png
        png.parent.mkdir(parents=True, exist_ok=True)
        png.write_bytes(self.read_object(card_png_key(kid_id)))
        card_json = self.out_root / kid_id / "card.json"
        if not card_json.is_file():
            try:
                card_json.write_bytes(self.read_object(card_json_key(kid_id)))
            except Exception:
                pass
        return png

    def submit_run(self, *, jobs: int = 4) -> dict[str, Any]:
        from santa.batch import require_card_ids, run_jobs_phase
        from santa.nebius_jobs import SdkJobService
        from santa.storage import local_run_dir

        ids = require_card_ids(self.storage)
        rid = uuid.uuid4().hex[:10]
        run_dir = local_run_dir(rid, root=self.out_root)
        run_dir.mkdir(parents=True, exist_ok=True)
        svc = self.job_service or SdkJobService.from_env()
        return run_jobs_phase(
            kids=ids,
            n_jobs=jobs,
            run_id=rid,
            run_dir=run_dir,
            storage=self.storage,
            settings=self.settings,
            service=svc,
            wait=False,
        )

    def run_status(self, run_id: str) -> dict[str, Any]:
        from santa.nebius_jobs import SdkJobService
        from santa.storage import local_run_dir

        run_dir = local_run_dir(run_id, root=self.out_root)
        ticket_path = run_dir / "ticket.json"
        if not ticket_path.is_file():
            ticket_path.parent.mkdir(parents=True, exist_ok=True)
            ticket_path.write_bytes(self.storage.download(f"runs/{run_id}/ticket.json"))
        ticket = json.loads(ticket_path.read_text(encoding="utf-8"))
        svc = self.job_service or SdkJobService.from_env()
        jobs: list[dict[str, Any]] = []
        for meta in ticket.get("jobs") or []:
            if not isinstance(meta, dict):
                continue
            state = ""
            try:
                state = str(svc.get(str(meta["job_id"])))
            except Exception as exc:
                state = f"ERROR: {exc}"
            jobs.append({**meta, "state": state})
        summary: Any = None
        summary_path = run_dir / "summary.json"
        if summary_path.is_file():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        else:
            loaded = _load_json(self.storage, f"runs/{run_id}/summary.json")
            if loaded is not None:
                summary = loaded
        return {
            "run_id": run_id,
            "kids": ticket.get("kids") or [],
            "jobs": jobs,
            "summary": summary,
        }


def _ids_from_png_keys(cards: list[str]) -> list[str]:
    ids: list[str] = []
    for key in cards:
        kid_id = id_from_card_png_key(key)
        if kid_id:
            ids.append(kid_id)
    return ids


def _wall_counter(summary: Any) -> int | None:
    """Live counter: ``totals.done`` if present, else ``kids``."""
    if not isinstance(summary, dict):
        return None
    totals = summary.get("totals")
    if isinstance(totals, dict) and totals.get("done") is not None:
        try:
            return int(totals["done"])
        except (TypeError, ValueError):
            pass
    kids = summary.get("kids")
    if isinstance(kids, list):
        return len(kids)
    if kids is not None:
        try:
            return int(kids)
        except (TypeError, ValueError):
            return None
    return None
