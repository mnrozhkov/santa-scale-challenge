"""Demo session façade — the single seam for the presenter app and tests."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# prototype/ stays until issue 15; santa_demo still calls process_kid from there.
_PROTOTYPE = Path(__file__).resolve().parent.parent / "prototype"
if str(_PROTOTYPE) not in sys.path:
    sys.path.insert(0, str(_PROTOTYPE))

from santa_workflow import process_kid  # noqa: E402
from src.card_formatter import format_gift_card  # noqa: E402
from src.clients.image_client import ImageClient  # noqa: E402
from src.clients.llm_client import LLMClient  # noqa: E402
from src.data_scheme import GiftCard, GiftRecommendation, KidProfile, Wish  # noqa: E402

from santa_demo.config import DemoConfig, ImageEndpointConfigError  # noqa: E402
from santa_demo.fallbacks import list_fallback_pngs, require_four_fallbacks  # noqa: E402
from santa_demo.jobs import JobResult, JobRunner, NebiusJobRunner  # noqa: E402
from santa_demo.video import VideoClient  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "santa_demo" / "out"
DEFAULT_INTERMEDIATE_DIR = REPO_ROOT / "santa_demo" / "out" / "intermediate"


class ProfileValidationError(ValueError):
    """Raised when the KidProfile form is not usable."""


@dataclass
class DemoCard:
    """One generated GiftCard plus the bits the presenter page needs to show."""

    profile: KidProfile
    gifts: list[str]
    wish_text: str
    html: str
    png_path: str | None
    gift_card: GiftCard
    image_endpoint_url: str


CardRunner = Callable[[KidProfile, LLMClient, ImageClient, Path, Path], DemoCard]


def _default_card_runner(
    profile: KidProfile,
    llm_client: LLMClient,
    image_client: ImageClient,
    output_dir: Path,
    intermediate_dir: Path,
) -> DemoCard:
    gift_card = process_kid(
        kid_profile=profile,
        llm_client=llm_client,
        image_client=image_client,
        output_dir=output_dir,
        intermediate_dir=intermediate_dir,
    )
    if gift_card is None:
        raise RuntimeError(f"process_kid returned no GiftCard for {profile.name}")

    recommendation, wish = _load_intermediates(intermediate_dir, profile.id)
    html = format_gift_card(profile, recommendation, wish, _card_image_stub(profile, gift_card))
    html_path = output_dir / f"{profile.id}.html"
    html_path.write_text(html, encoding="utf-8")

    return DemoCard(
        profile=profile,
        gifts=recommendation.gifts,
        wish_text=wish.text,
        html=html,
        png_path=gift_card.rendered_url,
        gift_card=gift_card,
        image_endpoint_url=image_client.base_url,
    )


def _load_intermediates(intermediate_dir: Path, kid_id: str) -> tuple[GiftRecommendation, Wish]:
    rec_path = intermediate_dir / f"{kid_id}_gift_recommendation.json"
    wish_path = intermediate_dir / f"{kid_id}_wish.json"
    rec_payload = _read_json(rec_path)["recommendation"]
    wish_payload = _read_json(wish_path)["wish"]
    return GiftRecommendation.model_validate(rec_payload), Wish.model_validate(wish_payload)


def _read_json(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _card_image_stub(profile: KidProfile, gift_card: GiftCard):
    from src.data_scheme import CardImage

    return CardImage(
        id=gift_card.image_id,
        kid_id=profile.id,
        image_url=gift_card.rendered_url or "",
        model_version="demo",
    )


def validate_profile(name: str, age: int | str, wish: str) -> KidProfile:
    cleaned_name = (name or "").strip()
    if not cleaned_name:
        raise ProfileValidationError("Name is required.")
    try:
        age_int = int(age)
    except (TypeError, ValueError) as exc:
        raise ProfileValidationError("Age must be a number between 1 and 18.") from exc
    if age_int < 1 or age_int > 18:
        raise ProfileValidationError("Age must be between 1 and 18.")
    wishlist = [wish.strip()] if (wish or "").strip() else []
    return KidProfile(name=cleaned_name, age=age_int, wishlist=wishlist)


@dataclass
class DemoSession:
    config: DemoConfig
    llm_client: LLMClient
    image_client: ImageClient
    card_runner: CardRunner = field(default=_default_card_runner)
    output_dir: Path = field(default_factory=lambda: DEFAULT_OUTPUT_DIR)
    intermediate_dir: Path = field(default_factory=lambda: DEFAULT_INTERMEDIATE_DIR)
    last_card: DemoCard | None = None
    last_video_path: str | None = None
    last_jobs: list[JobResult] = field(default_factory=list)
    video_client: VideoClient | None = None
    job_runner: JobRunner | None = None

    @classmethod
    def from_env(
        cls,
        *,
        llm_client: LLMClient | None = None,
        image_client: ImageClient | None = None,
        card_runner: CardRunner | None = None,
        video_client: VideoClient | None = None,
        job_runner: JobRunner | None = None,
        output_dir: Path | None = None,
        intermediate_dir: Path | None = None,
    ) -> DemoSession:
        config = DemoConfig.from_env()
        resolved_image = image_client or ImageClient(
            base_url=config.image_endpoint_url,
            api_key=config.image_endpoint_token,
            model=config.image_model,
        )
        if "recraft" in resolved_image.base_url.lower():
            raise ImageEndpointConfigError(
                "Image client points at Recraft. Set IMAGE_ENDPOINT_URL to the Serverless endpoint."
            )
        resolved_llm = llm_client or LLMClient(
            base_url=config.token_factory_base_url,
            api_key=config.token_factory_api_key,
            model=config.token_factory_model,
        )
        return cls(
            config=config,
            llm_client=resolved_llm,
            image_client=resolved_image,
            card_runner=card_runner or _default_card_runner,
            output_dir=output_dir or DEFAULT_OUTPUT_DIR,
            intermediate_dir=intermediate_dir or DEFAULT_INTERMEDIATE_DIR,
            video_client=video_client,
            job_runner=job_runner,
        )

    def generate_card(self, profile: KidProfile) -> DemoCard:
        if not (profile.name or "").strip():
            raise ProfileValidationError("Name is required.")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.intermediate_dir.mkdir(parents=True, exist_ok=True)
        card = self.card_runner(
            profile,
            self.llm_client,
            self.image_client,
            self.output_dir,
            self.intermediate_dir,
        )
        card.image_endpoint_url = self.image_client.base_url
        self.last_card = card
        return card

    def png_for_animate(self) -> Path:
        if self.last_card and self.last_card.png_path and Path(self.last_card.png_path).exists():
            return Path(self.last_card.png_path)
        fallbacks = list_fallback_pngs()
        if not fallbacks:
            raise FileNotFoundError("No live GiftCard PNG and no fallback rasters.")
        return fallbacks[0]

    def animate(self, prompt: str = "gentle storybook motion") -> Path:
        client = self.video_client or VideoClient.from_env()
        png = self.png_for_animate()
        mp4 = client.animate(png.read_bytes(), prompt=prompt)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        out = self.output_dir / "last.mp4"
        out.write_bytes(mp4)
        self.last_video_path = str(out)
        return out

    def pngs_for_batch(self, include_last: bool) -> list[Path]:
        fallbacks = require_four_fallbacks()
        live = None
        if self.last_card and self.last_card.png_path:
            live_path = Path(self.last_card.png_path)
            if live_path.exists():
                live = live_path
        if include_last and live is not None:
            return [live, *fallbacks[:3]]
        return fallbacks[:4]

    def batch_videos(self, include_last: bool = False) -> list[JobResult]:
        pngs = self.pngs_for_batch(include_last)
        runner = self.job_runner or NebiusJobRunner.from_env()
        self.last_jobs = runner.submit(pngs)
        return self.last_jobs

    def refresh_jobs(self) -> list[JobResult]:
        if not self.last_jobs:
            return []
        runner = self.job_runner or NebiusJobRunner.from_env()
        self.last_jobs = runner.poll(self.last_jobs)
        return self.last_jobs
