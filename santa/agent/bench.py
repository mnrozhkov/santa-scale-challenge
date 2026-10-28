"""Pipeline vs agent scorecard for Experiment B."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, Literal

from santa.agent.judge import evaluate_image, evaluate_video
from santa.agent.policy import Policy
from santa.agent.runner import run_kids
from santa.agent.state import Attempt, KidReport, KidState, RunReport
from santa.agent.trace import Tracer
from santa.animate import load_prompts, motion_prompt
from santa.card import generate_image, make_card, recommend_gift, write_wish
from santa.config import Settings
from santa.cost import cost_usd
from santa.models import adapter_for
from santa.schemas import KidProfile

Mode = Literal["pipeline", "pipeline-retry-all", "agent"]


def _compute(settings: Settings, role: str) -> tuple[str, str]:
    from santa.agent.policy import compute_for_role

    return compute_for_role(settings, role)


def _image_attempt(
    kid: KidProfile,
    rec: Any,
    image: Any,
    *,
    n: int,
    out_dir: Path,
    platform: str,
    preset: str,
    seed: int | None = None,
    prompt_suffix: str = "",
    latency_s: float = 12.0,
) -> Attempt:
    t0 = time.time()
    png, meta = generate_image(kid, rec, image, seed=seed, prompt_suffix=prompt_suffix)
    latency = time.time() - t0
    metrics = getattr(image, "last_metrics", {}) or {}
    if "latency_ms" in metrics:
        latency = float(metrics["latency_ms"]) / 1000.0
    elif latency < 0.01:
        latency = latency_s
    path = out_dir / f"image-{n}.png"
    path.write_bytes(png)
    meta.path = str(path)
    cost = cost_usd(platform, preset, latency, preemptible=True)
    return Attempt(
        kind="image",
        n=n,
        seed=seed,
        prompt_suffix=prompt_suffix,
        path=str(path),
        latency_s=latency,
        cost_usd=cost,
        platform=platform,
        preset=preset,
        fallback=bool(getattr(image, "used_fallback", False)),
    )


def _video_attempt(
    img: Attempt,
    video: Any,
    *,
    n: int,
    out_dir: Path,
    platform: str,
    preset: str,
    motion: str,
    seed: int | None = None,
    latency_s: float = 120.0,
) -> Attempt:
    t0 = time.time()
    png = Path(img.path).read_bytes()
    try:
        mp4 = video.generate(motion, image=png, seed=seed)
    except TypeError:
        mp4 = video.generate(motion, image=png)
    latency = time.time() - t0
    metrics = getattr(video, "last_metrics", {}) or {}
    if "latency_ms" in metrics:
        latency = float(metrics["latency_ms"]) / 1000.0
    elif latency < 0.01:
        latency = latency_s
    path = out_dir / f"video-{n}.mp4"
    raw = mp4 if isinstance(mp4, bytes | bytearray) else Path(mp4).read_bytes()
    path.write_bytes(raw)
    cost = cost_usd(platform, preset, latency, preemptible=True)
    return Attempt(
        kind="video",
        n=n,
        seed=seed,
        source_image_n=img.n,
        path=str(path),
        latency_s=latency,
        cost_usd=cost,
        platform=platform,
        preset=preset,
        fallback=bool(getattr(video, "used_fallback", False)),
    )


def run_pipeline(
    kids: list[KidProfile],
    *,
    settings: Settings,
    out_root: Path,
    run_id: str,
    llm: Any,
    image: Any,
    video: Any,
    vlm: Any,
    tracer: Tracer,
    retry_all: bool = False,
) -> RunReport:
    img_plat, img_preset = _compute(settings, "image")
    vid_plat, vid_preset = _compute(settings, "video")
    motion = motion_prompt(load_prompts())
    reports: list[KidReport] = []
    t0 = time.time()
    mode: Mode = "pipeline-retry-all" if retry_all else "pipeline"
    root = out_root / run_id
    root.mkdir(parents=True, exist_ok=True)

    for kid in kids:
        tracer.emit("run_started", kid_id=kid.id, mode=mode)
        out_dir = root / kid.id
        out_dir.mkdir(parents=True, exist_ok=True)
        state = KidState(kid=kid)
        if retry_all:
            rec = recommend_gift(kid, llm)
            wish = write_wish(kid, rec, llm)
            state.rec, state.wish = rec, wish
            for n in (1, 2):
                att = _image_attempt(
                    kid,
                    rec,
                    image,
                    n=n,
                    out_dir=out_dir,
                    platform=img_plat,
                    preset=img_preset,
                    seed=n,
                )
                att.evaluation = evaluate_image(Path(att.path).read_bytes(), kid, rec, vlm)
                state.images.append(att)
            best_img = state.best_image()
            assert best_img is not None
            for n in (1, 2):
                vatt = _video_attempt(
                    best_img,
                    video,
                    n=n,
                    out_dir=out_dir,
                    platform=vid_plat,
                    preset=vid_preset,
                    motion=motion,
                    seed=n,
                )
                vatt.evaluation = evaluate_video(
                    Path(best_img.path).read_bytes(),
                    vatt.path,
                    vlm,
                    frames_dir=out_dir / f"video-{n}.frames",
                )
                state.videos.append(vatt)
            best_vid = state.best_video()
            img_ok = best_img.evaluation and best_img.evaluation.decision == "PASS"
            vid_ok = best_vid and best_vid.evaluation and best_vid.evaluation.decision == "PASS"
            state.accepted_image_n = best_img.n
            state.accepted_video_n = best_vid.n if best_vid else None
            state.status = "accepted" if img_ok and vid_ok else "kept_best"
        else:
            run = make_card(kid, settings, out_root=out_dir, llm=llm, image=image)
            state.rec = run.card.recommendation
            state.wish = run.card.wish
            png_path = Path(run.card.png_path or "")
            # move into image-1.png layout
            img_path = out_dir / "image-1.png"
            if png_path.is_file():
                img_path.write_bytes(png_path.read_bytes())
            att = Attempt(
                kind="image",
                n=1,
                path=str(img_path),
                latency_s=12.0,
                cost_usd=cost_usd(img_plat, img_preset, 12.0, preemptible=True),
                platform=img_plat,
                preset=img_preset,
            )
            # post-hoc judge
            att.evaluation = evaluate_image(img_path.read_bytes(), kid, state.rec, vlm)
            state.images.append(att)
            vatt = _video_attempt(
                att,
                video,
                n=1,
                out_dir=out_dir,
                platform=vid_plat,
                preset=vid_preset,
                motion=motion,
            )
            vatt.evaluation = evaluate_video(
                img_path.read_bytes(),
                vatt.path,
                vlm,
                frames_dir=out_dir / "video-1.frames",
            )
            state.videos.append(vatt)
            img_ok = att.evaluation.decision == "PASS"
            vid_ok = vatt.evaluation.decision == "PASS"
            state.accepted_image_n = 1
            state.accepted_video_n = 1
            state.status = "accepted" if img_ok and vid_ok else "kept_best"
            # Headline: H100 on rejected images = video seconds when image was RETRY
            if att.evaluation.decision == "RETRY":
                # already counted via h100_on_rejected_images()
                pass
        report = state.to_report()
        reports.append(report)
        tracer.emit(
            "run_completed",
            kid_id=kid.id,
            status=report.status,
            cost_usd=report.cost_usd,
        )

    wall = time.time() - t0
    return RunReport(
        run_id=run_id,
        mode=mode,
        policy=Policy(),
        kids=reports,
        totals={
            "accepted": sum(1 for k in reports if k.status == "accepted"),
            "images": sum(k.image_attempts for k in reports),
            "videos": sum(k.video_attempts for k in reports),
            "l40s_s": round(sum(k.gpu_seconds_l40s for k in reports), 3),
            "h100_s": round(sum(k.gpu_seconds_h100 for k in reports), 3),
            "cost": round(sum(k.cost_usd for k in reports), 6),
            "wasted_h100_s": round(sum(k.h100_seconds_on_rejected_images for k in reports), 3),
            "wall_s": round(wall, 3),
            "judge_calls": "post-hoc" if not retry_all else "during",
        },
    )


def scorecard_md(reports: dict[str, RunReport]) -> str:
    cols = [m for m in ("pipeline", "pipeline-retry-all", "agent") if m in reports]
    headers = ["metric"] + cols
    rows = [
        ("Accepted (image PASS ∧ video PASS)", "accepted"),
        ("Images (L40S) · seconds", "l40s_s"),
        ("Videos (H100) · seconds", "h100_s"),
        ("H100 seconds on rejected images", "wasted_h100_s"),
        ("Cost (attributed)", "cost"),
        ("Wall time", "wall_s"),
    ]
    lines = [
        "# Agent vs pipeline scorecard",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for label, key in rows:
        cells = [label]
        for m in cols:
            cells.append(str(reports[m].totals.get(key, "")))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(
        "Cost is *attributed* (gpu_hourly_rate × call_latency); endpoints bill while running."
    )
    return "\n".join(lines) + "\n"


def run_bench(
    kids: list[KidProfile],
    *,
    modes: list[str],
    policy: Policy,
    settings: Settings,
    out_root: Path | str = "out/bench",
    llm: Any = None,
    image: Any = None,
    video: Any = None,
    vlm: Any = None,
    model: Any = None,
) -> Path:
    root = Path(out_root)
    bench_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    dest = root / bench_id
    dest.mkdir(parents=True, exist_ok=True)
    llm = llm or adapter_for("llm", settings)
    image = image or adapter_for("image", settings)
    video = video or adapter_for("video", settings)
    try:
        vlm = vlm or adapter_for("vlm", settings)
    except Exception:
        vlm = vlm or llm

    reports: dict[str, RunReport] = {}
    for mode in modes:
        mode_dir = dest / mode
        mode_dir.mkdir(parents=True, exist_ok=True)
        tracer = Tracer(mode_dir / "events.jsonl", run_id=f"{bench_id}-{mode}", mode=mode)
        if mode == "agent":
            reports[mode] = run_kids(
                kids,
                policy=policy,
                settings=settings,
                out_root=mode_dir,
                run_id="agent",
                llm=llm,
                image=image,
                video=video,
                vlm=vlm,
                model=model,
                tracer=tracer,
            )
        elif mode in ("pipeline", "pipeline-retry-all"):
            reports[mode] = run_pipeline(
                kids,
                settings=settings,
                out_root=mode_dir,
                run_id=mode,
                llm=llm,
                image=image,
                video=video,
                vlm=vlm,
                tracer=tracer,
                retry_all=mode == "pipeline-retry-all",
            )
        else:
            raise ValueError(f"unknown mode {mode!r}")
        (mode_dir / "report.json").write_text(
            reports[mode].model_dump_json(indent=2), encoding="utf-8"
        )

    path = dest / "scorecard.md"
    path.write_text(scorecard_md(reports), encoding="utf-8")
    return path
