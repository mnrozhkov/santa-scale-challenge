"""Orchestrator: concurrent per-kid Pydantic AI runs for Experiment B."""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits
from rich.console import Console
from rich.live import Live
from rich.table import Table

from santa.agent.kid_tools import KidDeps, build_deps, kid_tools
from santa.agent.policy import Budget, Policy
from santa.agent.state import KidReport, RunReport
from santa.agent.trace import Tracer
from santa.config import ConfigError, Settings
from santa.models import adapter_for
from santa.schemas import KidProfile

INSTRUCTIONS = """You produce one accepted animated Christmas gift card for {name}, age {age}.
Steps are tools. Policy is enforced by the tools; if a tool refuses, read the reason and choose another action or stop.
Rules you must follow:
1. Call recommend_gift, then write_wish, before any generate_image.
2. Every generated image must be evaluated before any video is made from it.
3. Only call generate_video on an image whose evaluation is PASS.
4. Retry an image only if its evaluation is RETRY; use the judge's fix: new seed, or its prompt_suffix.
5. If a video is WEAK with cause=motion, retry the video with a new seed. If cause=image, go back and regenerate the image.
6. Never exceed max attempts or the budget. If attempts are exhausted with no PASS, call keep_best — it animates the highest-scoring image anyway and finishes.
7. Finish by calling accept (PASS path) or keep_best (exhausted / no PASS). Prefer tool calls over prose.
Do not describe what you would do — call the tools."""


def _agent_model(settings: Settings, model: Any | None = None) -> Any:
    if model is not None:
        return model
    r = settings.role("llm")
    if not r.model:
        raise ConfigError("llm role has no model in config/models.yaml.")
    return OpenAIModel(
        r.model,
        provider=OpenAIProvider(base_url=r.v1, api_key=r.api_key),
    )


def _live_table(
    rows: dict[str, dict[str, Any]], policy: Policy, budget: Budget, footer: dict[str, float]
) -> Table:
    table = Table(title="santa agent")
    table.add_column("kid")
    table.add_column("step")
    table.add_column("images")
    table.add_column("videos")
    table.add_column("last")
    table.add_column("spent")
    for kid_id, row in rows.items():
        table.add_row(
            kid_id,
            str(row.get("step", "")),
            f"{row.get('images', 0)}/{policy.max_image_attempts}",
            f"{row.get('videos', 0)}/{policy.max_video_attempts}",
            str(row.get("last", "")),
            f"${float(row.get('spent', 0)):.3f}",
        )
    snap = budget.snapshot()
    table.caption = (
        f"spent ${snap['spent']:.3f} / ${policy.budget_usd:.2f} · "
        f"L40S {footer.get('l40s_s', 0):.1f}s · H100 {footer.get('h100_s', 0):.1f}s · "
        f"H100 on rejected {footer.get('wasted_h100_s', 0):.1f}s"
    )
    return table


async def _run_one_kid(
    kid: KidProfile,
    *,
    policy: Policy,
    budget: Budget,
    settings: Settings,
    llm: Any,
    image: Any,
    video: Any,
    vlm: Any,
    model: Any,
    out_root: Path,
    tracer: Tracer,
    publish: bool,
    clock: Any | None,
    live_rows: dict[str, dict[str, Any]] | None,
) -> KidReport:
    out_dir = out_root / kid.id
    out_dir.mkdir(parents=True, exist_ok=True)
    deps = build_deps(
        kid,
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
    )
    if live_rows is not None:
        live_rows[kid.id] = {
            "step": "start",
            "images": 0,
            "videos": 0,
            "last": "",
            "spent": 0.0,
        }

    tools = kid_tools(deps)
    instructions = INSTRUCTIONS.format(name=kid.name, age=kid.age)
    agent = Agent(
        model,
        deps_type=KidDeps,
        tools=tools,
        instructions=instructions,
        retries=2,
    )
    tracer.emit("run_started", kid_id=kid.id)
    try:
        await agent.run(
            f"Produce an accepted animated gift card for {kid.name}, age {kid.age}.",
            deps=deps,
            usage_limits=UsageLimits(request_limit=policy.max_steps_per_kid),
        )
        if deps.state.status is None:
            deps.state.status = "failed"
            deps.state.decision_log.append("agent stopped without accept/keep_best")
            tracer.emit(
                "run_completed",
                kid_id=kid.id,
                status="failed",
                cost_usd=deps.state.cost_total(),
            )
    except Exception as exc:
        if deps.state.status is None:
            deps.state.status = "failed"
        deps.state.decision_log.append(f"failed: {exc}")
        tracer.emit(
            "run_completed",
            kid_id=kid.id,
            status=deps.state.status or "failed",
            cost_usd=deps.state.cost_total(),
            detail=str(exc),
        )
    if live_rows is not None:
        live_rows[kid.id] = {
            "step": deps.state.status or "done",
            "images": len(deps.state.images),
            "videos": len(deps.state.videos),
            "last": (deps.state.decision_log[-1] if deps.state.decision_log else ""),
            "spent": deps.state.cost_total(),
        }
    return deps.state.to_report()


def _totals(kids: list[KidReport], wall_s: float) -> dict[str, Any]:
    return {
        "accepted": sum(1 for k in kids if k.status == "accepted"),
        "kept_best": sum(1 for k in kids if k.status == "kept_best"),
        "failed": sum(1 for k in kids if k.status == "failed"),
        "images": sum(k.image_attempts for k in kids),
        "videos": sum(k.video_attempts for k in kids),
        "l40s_s": round(sum(k.gpu_seconds_l40s for k in kids), 3),
        "h100_s": round(sum(k.gpu_seconds_h100 for k in kids), 3),
        "cost": round(sum(k.cost_usd for k in kids), 6),
        "wasted_h100_s": round(sum(k.h100_seconds_on_rejected_images for k in kids), 3),
        "wall_s": round(wall_s, 3),
    }


async def run_kids_async(
    kids: list[KidProfile],
    *,
    policy: Policy | None = None,
    settings: Settings | None = None,
    out_root: Path | str = "out/agent",
    run_id: str | None = None,
    publish: bool = False,
    llm: Any = None,
    image: Any = None,
    video: Any = None,
    vlm: Any = None,
    model: Any = None,
    clock: Any | None = None,
    tracer: Tracer | None = None,
    live: bool = False,
    console: Console | None = None,
    on_event: Any | None = None,
) -> RunReport:
    s = settings or Settings.load()
    pol = policy or Policy.from_file(s.policy)
    rid = run_id or time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    root = Path(out_root) / rid
    root.mkdir(parents=True, exist_ok=True)
    budget = Budget(pol.budget_usd)
    tr = tracer or Tracer(root / "events.jsonl", run_id=rid, mode="agent", on_event=on_event)
    (root / "policy.json").write_text(pol.model_dump_json(indent=2), encoding="utf-8")

    llm = llm or adapter_for("llm", s)
    image = image or adapter_for("image", s)
    video = video or adapter_for("video", s)
    try:
        vlm = vlm or adapter_for("vlm", s)
    except ConfigError:
        vlm = vlm or llm
    agent_model = _agent_model(s, model)

    live_rows: dict[str, dict[str, Any]] = {}
    footer = {"l40s_s": 0.0, "h100_s": 0.0, "wasted_h100_s": 0.0}
    sem = asyncio.Semaphore(max(1, pol.max_parallel_kids))
    t0 = time.time()

    async def guarded(kid: KidProfile) -> KidReport:
        async with sem:
            return await _run_one_kid(
                kid,
                policy=pol,
                budget=budget,
                settings=s,
                llm=llm,
                image=image,
                video=video,
                vlm=vlm,
                model=agent_model,
                out_root=root,
                tracer=tr,
                publish=publish,
                clock=clock,
                live_rows=live_rows if live else None,
            )

    if live:
        con = console or Console()
        with Live(
            _live_table(live_rows, pol, budget, footer), console=con, refresh_per_second=4
        ) as lv:
            tasks = [asyncio.create_task(guarded(k)) for k in kids]
            reports: list[KidReport] = []
            pending = set(tasks)
            while pending:
                done, pending = await asyncio.wait(pending, timeout=0.25)
                for t in done:
                    reports.append(t.result())
                footer["l40s_s"] = sum(r.gpu_seconds_l40s for r in reports)
                footer["h100_s"] = sum(r.gpu_seconds_h100 for r in reports)
                footer["wasted_h100_s"] = sum(r.h100_seconds_on_rejected_images for r in reports)
                lv.update(_live_table(live_rows, pol, budget, footer))
            by_id = {r.kid_id: r for r in reports}
            ordered = [by_id[k.id] for k in kids if k.id in by_id]
    else:
        results = await asyncio.gather(*[guarded(k) for k in kids])
        ordered = list(results)

    wall = time.time() - t0
    report = RunReport(
        run_id=rid,
        mode="agent",
        policy=pol,
        kids=ordered,
        totals=_totals(ordered, wall),
    )
    (root / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return report


def run_kids(kids: list[KidProfile], **kwargs: Any) -> RunReport:
    """Sync entry for CLI / service."""
    return asyncio.run(run_kids_async(kids, **kwargs))
