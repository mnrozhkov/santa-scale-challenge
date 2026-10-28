"""Policy-gated tools for Experiment B (evaluate-before-escalate).

Keeps ``santa.agent.tools.card_tools`` untouched for the sequential NL demo.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic_ai import ModelRetry, RunContext, Tool

from santa import card as card_mod
from santa.agent import judge as judge_mod
from santa.agent.policy import (
    Budget,
    BudgetExceeded,
    GateError,
    Policy,
    PolicyError,
    compute_for_role,
    estimate_cost_usd,
)
from santa.agent.state import Attempt, KidState
from santa.agent.trace import Tracer
from santa.animate import audio_adapter, load_prompts, mood_for, motion_prompt
from santa.cost import cost_usd
from santa.mux import mux
from santa.schemas import KidProfile


@dataclass
class KidDeps:
    state: KidState
    policy: Policy
    budget: Budget
    llm: Any
    image: Any
    video: Any
    vlm: Any
    settings: Any
    out_dir: Path
    tracer: Tracer
    publish: bool = False
    clock: Any | None = None  # optional FakeClock with .time()
    image_compute: tuple[str, str] = ("gpu-l40s-a", "1gpu-8vcpu-32gb")
    video_compute: tuple[str, str] = ("gpu-h100-sxm", "1gpu-16vcpu-200gb")
    preemptible: bool = True
    decision_log: list[str] = field(default_factory=list)

    def now(self) -> float:
        if self.clock is not None:
            return float(self.clock.time())
        return time.time()


def _retry(exc: BaseException) -> ModelRetry:
    return ModelRetry(str(exc))


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if hasattr(data, "model_dump"):
        path.write_text(data.model_dump_json(indent=2), encoding="utf-8")
    else:
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def stamp_agent_card(out_dir: Path) -> None:
    """Mark card.json so Gallery can filter agent-generated GiftCards."""
    path = out_dir / "card.json"
    if not path.is_file():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    data["source"] = "agent"
    tags = [t for t in (data.get("tags") or []) if isinstance(t, str)]
    if "agent" not in tags:
        tags.insert(0, "agent")
    data["tags"] = tags
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


def _render_silent_video(
    d: KidDeps,
    image_n: int,
    *,
    seed: int | None = None,
    motion_hint: str = "",
    bypass_gate: bool = False,
) -> dict[str, Any]:
    """Generate a silent MP4 from image ``image_n``. Raises Policy/Budget/Gate (not ModelRetry)."""
    kid_id = d.state.kid.id
    img = d.state.image(image_n)
    if img is None:
        raise PolicyError(f"unknown image attempt {image_n}")
    if d.policy.gate_video_on_image_pass and not bypass_gate:
        ev = img.evaluation
        if ev is None or ev.decision != "PASS":
            detail = (
                f"image {image_n} is {ev.decision if ev else 'unevaluated'} "
                "— evaluate a PASS image first"
            )
            d.tracer.emit(
                "policy_check",
                kid_id=kid_id,
                check="gate_video_on_image_pass",
                result="refused",
                detail=detail,
            )
            raise GateError(detail)
        d.tracer.emit(
            "policy_check",
            kid_id=kid_id,
            check="gate_video_on_image_pass",
            result="allowed",
            detail=f"image {image_n} PASS",
        )
    elif bypass_gate:
        score = img.evaluation.score if img.evaluation else None
        d.tracer.emit(
            "policy_check",
            kid_id=kid_id,
            check="keep_best_animate",
            result="allowed",
            detail=f"animate best image {image_n}"
            + (f" score={score}" if score is not None else " (no PASS)"),
        )
    d.policy.check_video_attempts(len(d.state.videos))
    platform, preset = d.video_compute
    est = estimate_cost_usd(
        platform, preset, d.policy.estimate_video_seconds, preemptible=d.preemptible
    )
    d.budget.reserve(est)
    n = len(d.state.videos) + 1
    prompts = load_prompts()
    motion = motion_prompt(prompts)
    hint = (motion_hint or "").strip()
    if hint:
        motion = f"{motion.rstrip()}\n{hint}"
    d.tracer.emit(
        "endpoint_call_started",
        kid_id=kid_id,
        role="video",
        attempt=n,
        platform=platform,
    )
    start = d.now()
    try:
        png_bytes = Path(img.path).read_bytes()
        try:
            mp4 = d.video.generate(motion, image=png_bytes, seed=seed)
        except TypeError:
            mp4 = d.video.generate(motion, image=png_bytes)
    except Exception:
        d.budget.release(est)
        raise
    latency = max(0.0, d.now() - start)
    metrics = getattr(d.video, "last_metrics", {}) or {}
    if "latency_ms" in metrics:
        latency = float(metrics["latency_ms"]) / 1000.0
    fallback = bool(getattr(d.video, "used_fallback", False))
    actual = 0.0 if fallback else cost_usd(platform, preset, latency, preemptible=d.preemptible)
    d.budget.commit(actual, reserved_usd=est)
    path = d.out_dir / f"video-{n}.mp4"
    path.write_bytes(mp4 if isinstance(mp4, bytes | bytearray) else Path(mp4).read_bytes())
    attempt = Attempt(
        kind="video",
        n=n,
        seed=seed,
        motion_hint=hint,
        source_image_n=image_n,
        path=str(path),
        latency_s=latency,
        cost_usd=actual,
        platform=platform,
        preset=preset,
        fallback=fallback,
        gate_bypassed=bypass_gate,
    )
    d.state.videos.append(attempt)
    snap = d.budget.snapshot()
    d.tracer.emit(
        "endpoint_call_completed",
        kid_id=kid_id,
        role="video",
        attempt=n,
        latency_s=latency,
        cost_usd=actual,
        platform=platform,
        fallback=fallback,
    )
    d.tracer.emit(
        "artifact_created",
        kid_id=kid_id,
        kind="video",
        attempt=n,
        path=str(path),
        source_image_n=image_n,
    )
    d.tracer.emit(
        "budget_updated",
        kid_id=kid_id,
        spent=snap["spent"],
        remaining=snap["remaining"],
    )
    return {
        "n": n,
        "image_n": image_n,
        "latency_s": latency,
        "cost_usd": actual,
        "budget_remaining": snap["remaining"],
        "path": str(path),
    }


def kid_tools(deps: KidDeps) -> list[Any]:
    """Build unbound tool functions closed over ``deps`` via RunContext."""

    def recommend_gift(ctx: RunContext[KidDeps]) -> dict[str, Any]:
        d = ctx.deps
        d.tracer.emit("tool_call", kid_id=d.state.kid.id, tool="recommend_gift", args={})
        rec = card_mod.recommend_gift(d.state.kid, d.llm)
        d.state.rec = rec
        d.state.decision_log.append(f"recommended gifts: {', '.join(rec.gifts[:2])}")
        return rec.model_dump()

    def write_wish(ctx: RunContext[KidDeps]) -> dict[str, Any]:
        d = ctx.deps
        d.tracer.emit("tool_call", kid_id=d.state.kid.id, tool="write_wish", args={})
        if d.state.rec is None:
            raise _retry(PolicyError("call recommend_gift before write_wish"))
        wish = card_mod.write_wish(d.state.kid, d.state.rec, d.llm)
        d.state.wish = wish
        return wish.model_dump()

    def generate_image(
        ctx: RunContext[KidDeps],
        seed: int | None = None,
        prompt_suffix: str = "",
    ) -> dict[str, Any]:
        d = ctx.deps
        kid_id = d.state.kid.id
        d.tracer.emit(
            "tool_call",
            kid_id=kid_id,
            tool="generate_image",
            attempt=len(d.state.images) + 1,
            args={"seed": seed, "prompt_suffix": prompt_suffix},
        )
        if d.state.rec is None:
            raise _retry(PolicyError("call recommend_gift before generate_image"))
        try:
            d.policy.check_image_attempts(len(d.state.images))
        except PolicyError as exc:
            d.tracer.emit(
                "policy_check",
                kid_id=kid_id,
                check="max_image_attempts",
                result="refused",
                detail=str(exc),
            )
            raise _retry(exc) from exc
        platform, preset = d.image_compute
        est = estimate_cost_usd(
            platform, preset, d.policy.estimate_image_seconds, preemptible=d.preemptible
        )
        try:
            d.budget.reserve(est)
        except BudgetExceeded as exc:
            d.tracer.emit(
                "policy_check",
                kid_id=kid_id,
                check="budget",
                result="refused",
                detail=str(exc),
            )
            raise _retry(exc) from exc
        n = len(d.state.images) + 1
        d.tracer.emit(
            "endpoint_call_started",
            kid_id=kid_id,
            role="image",
            attempt=n,
            platform=platform,
        )
        start = d.now()
        try:
            png, meta = card_mod.generate_image(
                d.state.kid, d.state.rec, d.image, seed=seed, prompt_suffix=prompt_suffix
            )
        except Exception as exc:
            d.budget.release(est)
            raise _retry(exc) from exc
        latency = max(0.0, d.now() - start)
        metrics = getattr(d.image, "last_metrics", {}) or {}
        if "latency_ms" in metrics:
            latency = float(metrics["latency_ms"]) / 1000.0
        fallback = bool(getattr(d.image, "used_fallback", False))
        actual = 0.0 if fallback else cost_usd(platform, preset, latency, preemptible=d.preemptible)
        d.budget.commit(actual, reserved_usd=est)
        path = d.out_dir / f"image-{n}.png"
        path.write_bytes(png)
        meta.path = str(path)
        _write_json(d.out_dir / f"image-{n}.json", meta)
        attempt = Attempt(
            kind="image",
            n=n,
            seed=seed,
            prompt_suffix=prompt_suffix or "",
            path=str(path),
            latency_s=latency,
            cost_usd=actual,
            platform=platform,
            preset=preset,
            fallback=fallback,
        )
        d.state.images.append(attempt)
        snap = d.budget.snapshot()
        d.tracer.emit(
            "endpoint_call_completed",
            kid_id=kid_id,
            role="image",
            attempt=n,
            latency_s=latency,
            cost_usd=actual,
            platform=platform,
            fallback=fallback,
        )
        d.tracer.emit(
            "artifact_created",
            kid_id=kid_id,
            kind="image",
            attempt=n,
            path=str(path),
        )
        d.tracer.emit(
            "budget_updated",
            kid_id=kid_id,
            spent=snap["spent"],
            remaining=snap["remaining"],
        )
        if prompt_suffix:
            d.tracer.emit(
                "retry_decided",
                kid_id=kid_id,
                kind="image",
                attempt=n,
                why="judge: fix=prompt",
            )
        elif n > 1:
            d.tracer.emit(
                "retry_decided",
                kid_id=kid_id,
                kind="image",
                attempt=n,
                why="judge: fix=seed" if seed is not None else "retry",
            )
        return {
            "n": n,
            "seed": seed,
            "latency_s": latency,
            "cost_usd": actual,
            "budget_remaining": snap["remaining"],
            "path": str(path),
        }

    def evaluate_image(ctx: RunContext[KidDeps], n: int) -> dict[str, Any]:
        d = ctx.deps
        kid_id = d.state.kid.id
        d.tracer.emit("tool_call", kid_id=kid_id, tool="evaluate_image", attempt=n, args={"n": n})
        attempt = d.state.image(n)
        if attempt is None:
            raise _retry(PolicyError(f"unknown image attempt {n}"))
        if d.state.rec is None:
            raise _retry(PolicyError("missing recommendation"))
        png = Path(attempt.path).read_bytes()
        evaluation = judge_mod.evaluate_image(png, d.state.kid, d.state.rec, d.vlm)
        attempt.evaluation = evaluation
        _write_json(d.out_dir / f"image-{n}.eval.json", evaluation)
        d.tracer.emit(
            "artifact_evaluated",
            kid_id=kid_id,
            kind="image",
            attempt=n,
            decision=evaluation.decision,
            score=evaluation.score,
            reasons=evaluation.reasons,
            passed=evaluation.passed,
            failed=evaluation.failed,
            fix=evaluation.fix,
        )
        passed_s = ", ".join(evaluation.passed) if evaluation.passed else "—"
        failed_s = ", ".join(evaluation.failed) if evaluation.failed else "—"
        d.state.decision_log.append(
            f"image {n}: {evaluation.decision} ({evaluation.score}) "
            f"pass=[{passed_s}] fail=[{failed_s}] — {'; '.join(evaluation.reasons[:2])}"
        )
        return evaluation.model_dump()

    def generate_video(
        ctx: RunContext[KidDeps],
        image_n: int,
        seed: int | None = None,
        motion_hint: str = "",
    ) -> dict[str, Any]:
        d = ctx.deps
        kid_id = d.state.kid.id
        d.tracer.emit(
            "tool_call",
            kid_id=kid_id,
            tool="generate_video",
            args={"image_n": image_n, "seed": seed, "motion_hint": motion_hint},
        )
        try:
            return _render_silent_video(
                d, image_n, seed=seed, motion_hint=motion_hint, bypass_gate=False
            )
        except PolicyError as exc:
            if "video attempts" in str(exc):
                d.tracer.emit(
                    "policy_check",
                    kid_id=kid_id,
                    check="max_video_attempts",
                    result="refused",
                    detail=str(exc),
                )
            raise _retry(exc) from exc
        except BudgetExceeded as exc:
            d.tracer.emit(
                "policy_check",
                kid_id=kid_id,
                check="budget",
                result="refused",
                detail=str(exc),
            )
            raise _retry(exc) from exc
        except GateError as exc:
            raise _retry(exc) from exc
        except Exception as exc:
            raise _retry(exc) from exc

    def evaluate_video(ctx: RunContext[KidDeps], n: int) -> dict[str, Any]:
        d = ctx.deps
        kid_id = d.state.kid.id
        d.tracer.emit("tool_call", kid_id=kid_id, tool="evaluate_video", args={"n": n})
        attempt = d.state.video(n)
        if attempt is None:
            raise _retry(PolicyError(f"unknown video attempt {n}"))
        src_n = attempt.source_image_n
        img = d.state.image(src_n) if src_n is not None else None
        if img is None:
            raise _retry(PolicyError(f"video {n} has no source image"))
        frames_dir = d.out_dir / f"video-{n}.frames"
        evaluation = judge_mod.evaluate_video(
            Path(img.path).read_bytes(),
            attempt.path,
            d.vlm,
            frames_dir=frames_dir,
        )
        attempt.evaluation = evaluation
        _write_json(d.out_dir / f"video-{n}.eval.json", evaluation)
        d.tracer.emit(
            "artifact_evaluated",
            kid_id=kid_id,
            kind="video",
            attempt=n,
            decision=evaluation.decision,
            score=evaluation.score,
            reasons=evaluation.reasons,
            passed=evaluation.passed,
            failed=evaluation.failed,
            cause=evaluation.cause,
            motion_metric=evaluation.motion_metric,
        )
        passed_s = ", ".join(evaluation.passed) if evaluation.passed else "—"
        failed_s = ", ".join(evaluation.failed) if evaluation.failed else "—"
        d.state.decision_log.append(
            f"video {n}: {evaluation.decision} cause={evaluation.cause} ({evaluation.score}) "
            f"pass=[{passed_s}] fail=[{failed_s}]"
        )
        return evaluation.model_dump()

    def budget(ctx: RunContext[KidDeps]) -> dict[str, Any]:
        d = ctx.deps
        snap = d.budget.snapshot()
        return {
            **snap,
            "image_attempts": len(d.state.images),
            "video_attempts": len(d.state.videos),
            "max_image_attempts": d.policy.max_image_attempts,
            "max_video_attempts": d.policy.max_video_attempts,
        }

    def _mux_accept(
        d: KidDeps,
        image_n: int,
        video_n: int,
        *,
        kept_best: bool,
        reason: str,
    ) -> dict[str, str]:
        img = d.state.image(image_n)
        vid = d.state.video(video_n)
        if img is None or vid is None:
            raise PolicyError("accept requires existing image and video attempts")
        if d.state.rec is None or d.state.wish is None:
            raise PolicyError("accept requires recommend_gift and write_wish")
        if not kept_best:
            if img.evaluation is None or img.evaluation.decision != "PASS":
                raise PolicyError(f"image {image_n} is not PASS")
            if vid.evaluation is None or vid.evaluation.decision != "PASS":
                if not (
                    d.budget.exhausted
                    or len(d.state.images) >= d.policy.max_image_attempts
                    or len(d.state.videos) >= d.policy.max_video_attempts
                ):
                    raise PolicyError(f"video {video_n} is not PASS")
                kept_best = True
        png_bytes = Path(img.path).read_bytes()
        meta_path = d.out_dir / f"image-{image_n}.json"
        from santa.schemas import CardImage

        if meta_path.is_file():
            meta = CardImage.model_validate_json(meta_path.read_text(encoding="utf-8"))
        else:
            meta = CardImage(
                kid_id=d.state.kid.id,
                path=img.path,
                model_version="unknown",
                prompt="",
            )
        gift = card_mod.save_card(
            d.state.kid, d.state.rec, d.state.wish, png_bytes, meta, d.out_dir
        )
        # Mux mood-bank track onto silent video → card.mp4
        silent = Path(vid.path)
        prompts = load_prompts()
        mood = d.state.wish.mood if d.state.wish else mood_for(Path(gift.png_path or img.path))
        audio = audio_adapter(d.settings, mood_bank=True)
        dest = d.out_dir / "card.mp4"
        tmp_a = d.out_dir / ".accept.audio.tmp.mp3"
        try:
            from santa.animate import music_prompt

            mp3 = audio.generate(music_prompt(prompts, mood), mood=mood)
            tmp_a.write_bytes(mp3)
            mux(silent, tmp_a, dest)
        finally:
            tmp_a.unlink(missing_ok=True)
        stamp_agent_card(d.out_dir)
        d.state.accepted_image_n = image_n
        d.state.accepted_video_n = video_n
        d.state.kept_best = kept_best
        d.state.status = "kept_best" if kept_best else "accepted"
        d.state.decision_log.append(f"{'keep_best' if kept_best else 'accept'}: {reason}")
        d.tracer.emit(
            "run_completed",
            kid_id=d.state.kid.id,
            status=d.state.status,
            cost_usd=d.state.cost_total(),
            reason=reason,
        )
        return {
            "png": gift.png_path or "",
            "html": gift.html_path or "",
            "mp4": str(dest),
            "status": d.state.status,
        }

    def accept(
        ctx: RunContext[KidDeps],
        image_n: int,
        video_n: int,
        reason: str,
    ) -> dict[str, str]:
        d = ctx.deps
        d.tracer.emit(
            "tool_call",
            kid_id=d.state.kid.id,
            tool="accept",
            args={"image_n": image_n, "video_n": video_n, "reason": reason},
        )
        try:
            return _mux_accept(d, image_n, video_n, kept_best=False, reason=reason)
        except PolicyError as exc:
            raise _retry(exc) from exc

    def keep_best(ctx: RunContext[KidDeps], reason: str) -> dict[str, str]:
        """Finish with highest-score image. Always animate it when no video yet (even without PASS)."""
        d = ctx.deps
        d.tracer.emit(
            "tool_call",
            kid_id=d.state.kid.id,
            tool="keep_best",
            args={"reason": reason},
        )
        img = d.state.best_image()
        if img is None:
            raise _retry(PolicyError("nothing generated yet"))
        if d.state.rec is None:
            raise _retry(PolicyError("call recommend_gift before keep_best"))
        if d.state.wish is None:
            # Finish path: complete wish so we can mux mood-bank audio.
            d.state.wish = card_mod.write_wish(d.state.kid, d.state.rec, d.llm)
            d.state.decision_log.append(f"auto write_wish for keep_best mood={d.state.wish.mood}")
        vid = d.state.best_video()
        if vid is None:
            try:
                rendered = _render_silent_video(d, img.n, bypass_gate=True)
                vid_n = int(rendered["n"])
                d.state.decision_log.append(
                    f"keep_best animate image {img.n} "
                    f"(score={img.evaluation.score if img.evaluation else '?'})"
                )
            except (BudgetExceeded, PolicyError) as exc:
                d.tracer.emit(
                    "policy_check",
                    kid_id=d.state.kid.id,
                    check="keep_best_animate",
                    result="refused",
                    detail=str(exc),
                )
                # Fall back to PNG-only if video cannot run.
                from santa.schemas import CardImage

                png_bytes = Path(img.path).read_bytes()
                meta = CardImage(
                    kid_id=d.state.kid.id,
                    path=img.path,
                    model_version="unknown",
                    prompt="",
                )
                gift = card_mod.save_card(
                    d.state.kid, d.state.rec, d.state.wish, png_bytes, meta, d.out_dir
                )
                stamp_agent_card(d.out_dir)
                d.state.accepted_image_n = img.n
                d.state.status = "kept_best"
                d.state.kept_best = True
                d.state.decision_log.append(f"keep_best (image only): {reason} ({exc})")
                d.tracer.emit(
                    "run_completed",
                    kid_id=d.state.kid.id,
                    status="kept_best",
                    cost_usd=d.state.cost_total(),
                    reason=reason,
                )
                return {
                    "png": gift.png_path or "",
                    "html": gift.html_path or "",
                    "mp4": "",
                    "status": "kept_best",
                }
            except Exception as exc:
                raise _retry(exc) from exc
            try:
                return _mux_accept(d, img.n, vid_n, kept_best=True, reason=reason)
            except PolicyError as exc:
                raise _retry(exc) from exc
        try:
            return _mux_accept(d, img.n, vid.n, kept_best=True, reason=reason)
        except PolicyError as exc:
            raise _retry(exc) from exc

    return [
        Tool(recommend_gift),
        Tool(write_wish),
        Tool(generate_image),
        Tool(evaluate_image),
        Tool(generate_video),
        Tool(evaluate_video),
        Tool(budget),
        Tool(accept),
        Tool(keep_best),
    ]


def build_deps(
    kid: KidProfile,
    *,
    policy: Policy,
    budget: Budget,
    llm: Any,
    image: Any,
    video: Any,
    vlm: Any,
    settings: Any,
    out_dir: Path,
    tracer: Tracer,
    publish: bool = False,
    clock: Any | None = None,
) -> KidDeps:
    image_compute = compute_for_role(settings, "image")
    video_compute = compute_for_role(settings, "video")
    return KidDeps(
        state=KidState(kid=kid),
        policy=policy,
        budget=budget,
        llm=llm,
        image=image,
        video=video,
        vlm=vlm,
        settings=settings,
        out_dir=out_dir,
        tracer=tracer,
        publish=publish,
        clock=clock,
        image_compute=image_compute,
        video_compute=video_compute,
    )
