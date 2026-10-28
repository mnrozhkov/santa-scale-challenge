"""VLM judges + frame extraction + motion metric for Experiment B."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

from santa.agent.state import Evaluation
from santa.mux import ffmpeg_exe
from santa.schemas import GiftRecommendation, KidProfile

MOTION_STATIC = 0.01
MOTION_BROKE = 0.35

IMAGE_RULES = (
    "gift recognizable",
    "christmas/storybook atmosphere",
    "object-centric composition",
    "no people/faces",
    "text OK (correct English or none)",
)

VIDEO_RULES = (
    "same scene/object as illustration",
    "no new people/faces/bad text",
    "subtle motion (still the illustration)",
)


def image_judge_prompt(kid: KidProfile, rec: GiftRecommendation) -> str:
    main_gift = rec.gifts[0] if rec.gifts else "a wrapped present"
    rules = "; ".join(f"{i + 1}) {r}" for i, r in enumerate(IMAGE_RULES))
    return f"""You review a children's Christmas gift-card illustration. Requested main gift: "{main_gift}". Child: {kid.name}, {kid.age}.
Rules: {rules}.
Text is allowed when it is correct English and relevant (greeting, child's name, short wish). RETRY if garbled/misspelled/random, unrelated, abusive/unsafe, or signatures/watermarks.
Decide RETRY only for a rule violation. Never RETRY for taste, style or minor composition preferences.
If RETRY: `fix` = "seed" when the scene is right but a violation appeared by chance; "prompt" when the gift is missing or wrong — then give a one-line `prompt_suffix` that fixes it without changing style.
Return JSON: {{"decision":"PASS"|"RETRY","score":0-100,"passed":[rule names that pass],"failed":[rule names that fail],"reasons":[≤3 short strings],"fix":"seed"|"prompt"|"none","prompt_suffix":""}}
Use the exact rule name strings from the Rules list above in passed/failed."""


def video_judge_prompt() -> str:
    rules = "; ".join(f"{i + 1}) {r}" for i, r in enumerate(VIDEO_RULES))
    return f"""Compare the three video frames with the original illustration. Rules: {rules}.
`cause` = "motion" if the illustration is fine but the animation broke it; "image" if the illustration itself violates the card rules; "none" if PASS.
Return JSON: {{"decision":"PASS"|"WEAK","score":0-100,"passed":[rule names that pass],"failed":[rule names that fail],"reasons":[≤3],"cause":"motion"|"image"|"none"}}
Use the exact rule name strings from the Rules list above in passed/failed."""


def extract_frames(
    mp4: Path | str, out_dir: Path | str, *, num_frames: int = 81
) -> dict[str, Path]:
    """Extract first / mid / last frames into ``out_dir``.

    Decodes the whole clip to PNGs then picks endpoints — works for short test
    clips and full Wan 81-frame videos alike.
    """
    video = Path(mp4)
    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    pattern = dest / "raw_%05d.png"
    cmd = [
        ffmpeg_exe(),
        "-y",
        "-i",
        str(video),
        "-vsync",
        "0",
        str(pattern),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "")[-300:]
        raise RuntimeError(f"frame extract failed: {detail}") from exc
    frames = sorted(dest.glob("raw_*.png"))
    if not frames:
        raise RuntimeError(f"expected frames from {video}, got none")
    first_i, last_i = 0, len(frames) - 1
    mid_i = last_i // 2
    mapping = {
        "first": dest / "first.png",
        "mid": dest / "mid.png",
        "last": dest / "last.png",
    }
    for key, idx in (("first", first_i), ("mid", mid_i), ("last", last_i)):
        mapping[key].write_bytes(frames[idx].read_bytes())
    return mapping


def motion_metric(first_png: Path | str, last_png: Path | str) -> float:
    """Grayscale 128px mean absolute diff / 255 ∈ [0, 1]."""
    a = Image.open(first_png).convert("L").resize((128, 128))
    b = Image.open(last_png).convert("L").resize((128, 128))
    pa, pb = list(a.getdata()), list(b.getdata())
    if not pa:
        return 0.0
    mean = sum(abs(x - y) for x, y in zip(pa, pb, strict=True)) / (len(pa) * 255.0)
    return float(mean)


def _clip_reasons(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(r) for r in raw][:3]


def _clip_rule_list(raw: Any, *, known: tuple[str, ...], limit: int = 8) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    known_l = {k.lower(): k for k in known}
    for item in raw:
        s = str(item).strip()
        if not s:
            continue
        canon = known_l.get(s.lower(), s)
        if canon not in out:
            out.append(canon)
        if len(out) >= limit:
            break
    return out


def _checks_to_lists(
    data: dict[str, Any], *, known: tuple[str, ...]
) -> tuple[list[str], list[str]]:
    """Accept ``passed``/``failed`` arrays or a ``checks`` map of rule→bool."""
    passed = _clip_rule_list(data.get("passed"), known=known)
    failed = _clip_rule_list(data.get("failed"), known=known)
    checks = data.get("checks")
    if isinstance(checks, dict) and not passed and not failed:
        for key, ok in checks.items():
            label = str(key).strip()
            if not label:
                continue
            canon = next((k for k in known if k.lower() == label.lower()), label)
            if bool(ok):
                if canon not in passed:
                    passed.append(canon)
            elif canon not in failed:
                failed.append(canon)
    return passed, failed


def _parse_image_eval(data: dict[str, Any], *, judge_model: str) -> Evaluation:
    decision = str(data.get("decision") or "RETRY").upper()
    if decision not in ("PASS", "RETRY"):
        decision = "RETRY"
    fix = str(data.get("fix") or "none").lower()
    if fix not in ("seed", "prompt", "none"):
        fix = "none"
    try:
        score = int(data.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))
    passed, failed = _checks_to_lists(data, known=IMAGE_RULES)
    if decision == "PASS" and not passed and not failed:
        passed = list(IMAGE_RULES)
    return Evaluation(
        decision=decision,  # type: ignore[arg-type]
        score=score,
        reasons=_clip_reasons(data.get("reasons")),
        passed=passed,
        failed=failed,
        fix=fix,  # type: ignore[arg-type]
        prompt_suffix=str(data.get("prompt_suffix") or ""),
        judge_model=judge_model,
    )


def _parse_video_eval(
    data: dict[str, Any], *, judge_model: str, metric: float | None
) -> Evaluation:
    decision = str(data.get("decision") or "WEAK").upper()
    if decision not in ("PASS", "WEAK"):
        decision = "WEAK"
    cause = str(data.get("cause") or "none").lower()
    if cause not in ("image", "motion", "none"):
        cause = "none"
    try:
        score = int(data.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))
    passed, failed = _checks_to_lists(data, known=VIDEO_RULES)
    if decision == "PASS" and not passed and not failed:
        passed = list(VIDEO_RULES)
    return Evaluation(
        decision=decision,  # type: ignore[arg-type]
        score=score,
        reasons=_clip_reasons(data.get("reasons")),
        passed=passed,
        failed=failed,
        cause=cause,  # type: ignore[arg-type]
        motion_metric=metric,
        judge_model=judge_model,
    )


def evaluate_image(
    png: bytes | Path,
    kid: KidProfile,
    rec: GiftRecommendation,
    vlm: Any,
) -> Evaluation:
    raw = png if isinstance(png, bytes) else Path(png).read_bytes()
    model = (
        getattr(vlm, "model_version", None)
        or getattr(getattr(vlm, "cfg", None), "model", "")
        or "vlm"
    )
    try:
        data = vlm.generate_json_vision(image_judge_prompt(kid, rec), [raw])
        if not isinstance(data, dict):
            raise ValueError("not a dict")
        return _parse_image_eval(data, judge_model=str(model))
    except Exception as exc:
        return Evaluation(
            decision="RETRY",
            score=0,
            passed=[],
            failed=list(IMAGE_RULES),
            reasons=["judge failed", str(exc)[:120]],
            judge_model=str(model),
            fix="seed",
        )


def evaluate_video(
    illustration_png: bytes | Path,
    mp4: Path | str,
    vlm: Any,
    *,
    frames_dir: Path | str | None = None,
    num_frames: int = 81,
) -> Evaluation:
    ill = (
        illustration_png
        if isinstance(illustration_png, bytes)
        else Path(illustration_png).read_bytes()
    )
    model = (
        getattr(vlm, "model_version", None)
        or getattr(getattr(vlm, "cfg", None), "model", "")
        or "vlm"
    )
    video = Path(mp4)
    if frames_dir is None:
        tmp = tempfile.TemporaryDirectory()
        out = Path(tmp.name)
        cleanup = tmp
    else:
        out = Path(frames_dir)
        cleanup = None
    try:
        frames = extract_frames(video, out, num_frames=num_frames)
        metric = motion_metric(frames["first"], frames["last"])
        frame_bytes = [ill] + [
            p.read_bytes() for p in (frames["first"], frames["mid"], frames["last"])
        ]
        try:
            data = vlm.generate_json_vision(video_judge_prompt(), frame_bytes)
            if not isinstance(data, dict):
                raise ValueError("not a dict")
            evaluation = _parse_video_eval(data, judge_model=str(model), metric=metric)
        except Exception as exc:
            evaluation = Evaluation(
                decision="WEAK",
                score=0,
                passed=[],
                failed=list(VIDEO_RULES),
                reasons=["judge failed", str(exc)[:120]],
                cause="motion",
                motion_metric=metric,
                judge_model=str(model),
            )
        # Deterministic override: static or scene-broke → WEAK cause=motion
        if metric < MOTION_STATIC or metric > MOTION_BROKE:
            reasons = list(evaluation.reasons)
            label = "static frames" if metric < MOTION_STATIC else "scene broke"
            if label not in reasons:
                reasons = ([label] + reasons)[:3]
            failed = list(evaluation.failed)
            motion_rule = "subtle motion (still the illustration)"
            if motion_rule not in failed:
                failed = failed + [motion_rule]
            passed = [p for p in evaluation.passed if p != motion_rule]
            evaluation = evaluation.model_copy(
                update={
                    "decision": "WEAK",
                    "cause": "motion",
                    "reasons": reasons,
                    "passed": passed,
                    "failed": failed,
                    "motion_metric": metric,
                }
            )
        # Persist named frames next to video when frames_dir provided
        if frames_dir is not None:
            for name, path in frames.items():
                target = Path(frames_dir) / f"{name}.png"
                if path.resolve() != target.resolve():
                    target.write_bytes(path.read_bytes())
        return evaluation
    finally:
        if cleanup is not None:
            cleanup.cleanup()
