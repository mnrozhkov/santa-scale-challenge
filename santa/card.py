"""One kid → gift rec + wish (llm) → illustration (image) → PNG + HTML.

``recommend_gift``, ``write_wish``, ``generate_image`` and ``save_card`` are plain
functions so the agent (issue 06) can bind them as tools. ``make_card`` runs them
in order and records which model answered each role.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from santa.config import REPO_ROOT, Settings
from santa.models import adapter_for
from santa.prompts import MOODS, gift_recommendation_prompt, image_prompt, wish_prompt
from santa.render import write_card
from santa.schemas import CardImage, GiftCard, GiftRecommendation, KidProfile, Wish


class ProfileError(ValueError):
    """The kid profile is not usable; CLI prints this and exits before any model call."""


@dataclass
class CardRun:
    """Result of ``make_card``: the GiftCard, where it landed, and per-call metrics."""

    card: GiftCard
    out_dir: Path
    steps: list[dict[str, Any]] = field(default_factory=list)


def validate_profile(name: str, age: int | str, wish: str = "") -> KidProfile:
    """Reject empty names and ages outside 1–18 before any adapter is constructed."""
    cleaned = (name or "").strip()
    if not cleaned:
        raise ProfileError("Name is required.")
    try:
        age_int = int(age)
    except (TypeError, ValueError) as exc:
        raise ProfileError("Age must be a number between 1 and 18.") from exc
    if age_int < 1 or age_int > 18:
        raise ProfileError("Age must be between 1 and 18.")
    wishlist = [wish.strip()] if (wish or "").strip() else []
    return KidProfile(name=cleaned, age=age_int, wishlist=wishlist)


def _model_label(adapter: Any) -> str:
    """Model id for UI/logs — never include endpoint URLs."""
    cfg = getattr(adapter, "cfg", None)
    if cfg is not None:
        configured = (getattr(cfg, "model", None) or "").strip()
        if configured:
            return configured
        adapter_name = (getattr(cfg, "adapter", None) or "").strip()
        if adapter_name:
            return adapter_name
    raw = str(getattr(adapter, "model_version", None) or "")
    if "@" in raw:
        return raw.split("@", 1)[0].strip()
    return raw or "unknown"


def _step(role: str, adapter: Any) -> dict[str, Any]:
    metrics = dict(getattr(adapter, "last_metrics", None) or {})
    return {
        "role": role,
        "model": _model_label(adapter),
        "fallback": bool(metrics.get("fallback", getattr(adapter, "used_fallback", False))),
        "ms": int(metrics.get("latency_ms") or 0),
    }


def recommend_gift(kid: KidProfile, llm: Any) -> GiftRecommendation:
    data = llm.generate_json(gift_recommendation_prompt(kid))
    gifts = [str(g) for g in data.get("gifts") or []][:5]
    if not gifts:
        raise ValueError("llm returned no gifts")
    return GiftRecommendation(
        kid_id=kid.id,
        gifts=gifts,
        rationale=str(data.get("rationale") or "").strip()
        or "Santa thought of these just for you.",
        model_version=getattr(llm, "model_version", "unknown"),
    )


def write_wish(kid: KidProfile, rec: GiftRecommendation, llm: Any) -> Wish:
    data = llm.generate_json(wish_prompt(kid, rec))
    mood = str(data.get("mood") or "warm").strip().lower()
    if mood not in MOODS:
        mood = "warm"
    return Wish(
        kid_id=kid.id,
        text=str(data.get("wish") or data.get("text") or "").strip(),
        mood=mood,
        model_version=getattr(llm, "model_version", "unknown"),
    )


def generate_image(
    kid: KidProfile,
    rec: GiftRecommendation,
    image: Any,
    *,
    seed: int | None = None,
    prompt_suffix: str = "",
) -> tuple[bytes, CardImage]:
    prompt = image_prompt(kid, rec)
    suffix = (prompt_suffix or "").strip()
    if suffix:
        prompt = f"{prompt.rstrip()}\n{suffix}"
    png = image.generate(prompt, seed=seed)
    cfg = getattr(image, "cfg", None)
    endpoint = getattr(cfg, "base_url", None)
    return png, CardImage(
        kid_id=kid.id,
        path="",
        model_version=_model_label(image),
        prompt=prompt,
        endpoint=endpoint,
    )


def save_card(
    kid: KidProfile,
    rec: GiftRecommendation,
    wish: Wish,
    illustration: bytes,
    image_meta: CardImage,
    out_dir: Path,
) -> GiftCard:
    png_path, html_path = write_card(out_dir, illustration, kid, rec, wish)
    image_meta.path = str(png_path)
    card = GiftCard(
        kid_id=kid.id,
        recommendation=rec,
        wish=wish,
        image=image_meta,
        png_path=str(png_path),
        html_path=str(html_path),
        status="completed",
    )
    (out_dir / "card.json").write_text(card.model_dump_json(indent=2), encoding="utf-8")
    (out_dir / "profile.json").write_text(kid.model_dump_json(indent=2), encoding="utf-8")
    return card


def make_card(
    kid: KidProfile,
    settings: Settings,
    *,
    out_root: Path | str | None = None,
    seed: int | None = None,
    llm: Any = None,
    image: Any = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
) -> CardRun:
    """Gift rec → wish → image → render. Inject ``llm`` / ``image`` in tests."""

    def emit(event: dict[str, Any]) -> None:
        if on_progress is not None:
            on_progress(event)

    llm = llm or adapter_for("llm", settings)
    image = image or adapter_for("image", settings)
    emit({"type": "active", "node": "token"})
    rec = recommend_gift(kid, llm)
    step_gift = _step("llm", llm)
    emit({"type": "step", "step": step_gift})
    wish = write_wish(kid, rec, llm)
    step_wish = _step("llm", llm)
    emit({"type": "step", "step": step_wish})
    llm_ms = step_gift["ms"] + step_wish["ms"]
    emit(
        {
            "type": "done",
            "node": "token",
            "meta": f"{llm_ms / 1000:.1f} s · {step_wish['model']}",
        }
    )
    steps = [step_gift, step_wish]
    emit({"type": "active", "node": "sana"})
    png, meta = generate_image(kid, rec, image, seed=seed)
    step_image = _step("image", image)
    emit({"type": "step", "step": step_image})
    steps.append(step_image)
    if step_image["fallback"]:
        emit({"type": "done", "node": "sana", "status": "failed", "meta": "fallback"})
        emit({"type": "active", "node": "openai"})
        emit(
            {
                "type": "done",
                "node": "openai",
                "meta": f"{step_image['ms'] / 1000:.1f} s · {step_image['model']}",
            }
        )
    else:
        emit(
            {
                "type": "done",
                "node": "sana",
                "meta": f"{step_image['ms'] / 1000:.1f} s · {step_image['model']}",
            }
        )
    out_dir = Path(out_root) / kid.id if out_root is not None else REPO_ROOT / "out" / kid.id
    card = save_card(kid, rec, wish, png, meta, out_dir)
    return CardRun(card=card, out_dir=out_dir, steps=steps)
