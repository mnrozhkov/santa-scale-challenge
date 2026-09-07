"""Service session — injectable card runner, adapters, and storage."""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from santa.card import CardRun, ProfileError, make_card
from santa.config import REPO_ROOT, ConfigError, Settings
from santa.schemas import KidProfile
from santa.storage import Storage

CardRunner = Callable[..., CardRun]


class StorageLike(Protocol):
    def upload(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        ...

    def exists(self, key: str) -> bool:
        ...

    def list(self, prefix: str = "") -> list[str]:
        ...

    def download(self, key: str) -> bytes:
        ...


def _adapter_url(adapter: Any) -> str:
    cfg = getattr(adapter, "cfg", None)
    return str(getattr(cfg, "base_url", None) or getattr(adapter, "base_url", "") or "")


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
    ) -> ServiceSession:
        resolved = settings or Settings.load()
        return cls(
            settings=resolved,
            storage=storage or Storage.from_env(),
            llm=llm,
            image=image,
            card_runner=card_runner or make_card,
            out_root=out_root or REPO_ROOT / "out",
        )

    def generate_card(self, kid: KidProfile) -> CardRun:
        run = self._run_card(kid)
        self.last_run = run
        self.last_kid = kid
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
        run = self._run_card(kid)
        self._upload_card(kid.id, run)
        return kid.id

    def _upload_card(self, kid_id: str, run: CardRun) -> None:
        png = Path(run.card.png_path) if run.card.png_path else None
        if png is not None and png.is_file():
            self.storage.upload(f"cards/{kid_id}.png", png.read_bytes(), content_type="image/png")
        html = Path(run.card.html_path) if run.card.html_path else None
        if html is not None and html.is_file():
            self.storage.upload(f"cards/{kid_id}.html", html.read_bytes(), content_type="text/html")
        json_path = png.parent / "card.json" if png is not None else None
        if json_path is not None and json_path.is_file():
            payload = json_path.read_bytes()
        else:
            payload = run.card.model_dump_json().encode()
        self.storage.upload(f"cards/{kid_id}.json", payload, content_type="application/json")

    def publish(self, filename: str, data: bytes, content_type: str = "") -> str:
        name = Path(filename).name or "upload"
        ctype = content_type.lower()
        if ctype.startswith("video/") or name.lower().endswith(".mp4"):
            key = f"videos/{name}"
            stored_type = content_type or "video/mp4"
        else:
            key = f"cards/{name}"
            stored_type = content_type or "image/png"
        self.storage.upload(key, data, content_type=stored_type)
        return key

    def wall(self) -> dict[str, Any]:
        cards = self.storage.list("cards/")
        videos = self.storage.list("videos/")
        summaries = [k for k in self.storage.list("runs/") if k.endswith("/summary.json")]
        summary: Any = None
        if summaries:
            raw = self.storage.download(max(summaries))
            summary = json.loads(raw)
        return {"cards": cards, "videos": videos, "summary": summary}
