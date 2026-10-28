"""``santa`` — the participant CLI.

santa doctor
santa card …      (issue 02) [--publish] [--offline]
santa agent …     (issue 06)
santa animate …   (issue 05) [--publish] [--offline]
santa animate_batch … (issue 16: Jobs over published cards/{id}/card.png) [--offline]
santa publish …   (issue 10)
santa teardown …  (issue 13)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, cast

import typer
from rich.console import Console
from rich.table import Table

from santa import __version__
from santa.animate import poll_ticket, run
from santa.config import Settings
from santa.doctor import failed, run_checks
from santa.schemas import KidProfile


def _use_system_certs() -> None:
    """macOS/corporate laptops often fail TLS with certifi's bundle; trust the OS store instead."""
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:  # pragma: no cover — optional dependency
        pass


_use_system_certs()

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Santa Scale Challenge on Nebius Serverless AI.",
)
console = Console()

_COLOUR = {"OK": "green", "WARN": "yellow", "SKIP": "dim", "FAIL": "red"}


@app.callback()
def _root(version: bool = typer.Option(False, "--version", is_eager=True)) -> None:
    if version:
        console.print(f"santa {__version__}")
        raise typer.Exit()


@app.command()
def doctor() -> None:
    """Check .env, Token Factory, your endpoints, fallbacks and Jobs plumbing. Prints what to fix."""
    checks = run_checks()
    table = Table(show_lines=False, header_style="bold")
    table.add_column("")
    table.add_column("Check")
    table.add_column("Detail")
    table.add_column("Fix")
    for c in checks:
        colour = _COLOUR[c.status]
        table.add_row(f"[{colour}]{c.status}[/{colour}]", c.name, c.detail, "" if c.ok else c.fix)
    console.print(table)
    if failed(checks):
        console.print(
            "[red]Something required is not working — fix the red rows (or set OPENAI_API_KEY for fallbacks).[/red]"
        )
        raise typer.Exit(code=1)
    console.print("[green]All required checks passed. Next: santa card --form[/green]")


@app.command()
def card(
    form: bool = typer.Option(False, "--form", help="Prompt for name, age, and wish."),
    profile: Path | None = typer.Option(None, "--profile", exists=True, dir_okay=False),
    name: str | None = typer.Option(None, "--name"),
    age: int | None = typer.Option(None, "--age"),
    wish: str | None = typer.Option(None, "--wish"),
    out: Path = typer.Option(Path("out"), "--out", help="Directory for out/<id>/card.png"),
    publish: bool = typer.Option(False, "--publish", help="Upload PNG/HTML to the wall."),
    local: bool = typer.Option(
        False, "--local", help="Upload with this laptop's bucket creds instead of the service."
    ),
    offline: bool = typer.Option(
        False, "--offline", help="Copy a bundled fallback card; skip endpoints."
    ),
) -> None:
    """Gift rec + wish + illustration → Pillow PNG and shareable HTML."""
    from santa.card import ProfileError, make_card
    from santa.config import Settings

    if offline:
        from santa.offline import OfflineError, copy_fallback_card

        try:
            png, html = copy_fallback_card(out, name=name)
        except OfflineError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc
        console.print("[yellow]offline[/yellow] — bundled fallback (endpoints not called)")
        console.print(f"[green]Wrote {png}[/green]")
        console.print(f"[green]Wrote {html}[/green]")
        if publish:
            _publish_outputs([png, html], local=local, object_id=png.parent.name)
        return

    try:
        kid = _kid_from_args(form=form, profile=profile, name=name, age=age, wish=wish)
    except ProfileError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    card_run = make_card(kid, Settings.load(), out_root=out)
    _print_card_run(card_run)
    if publish:
        _publish_outputs(
            _card_artifact_paths(card_run.card),
            local=local,
            object_id=card_run.card.kid_id,
        )


@app.command()
def agent(
    request: str | None = typer.Argument(
        None,
        help="Natural-language card request (4-tool demo; mutually exclusive with profile flags).",
    ),
    name: str | None = typer.Option(None, "--name"),
    age: int | None = typer.Option(None, "--age"),
    wish: str | None = typer.Option(None, "--wish"),
    kids: Path | None = typer.Option(
        None,
        "--kids",
        exists=True,
        dir_okay=False,
        help="CSV of KidProfiles (id,name,age,wishlist).",
    ),
    limit: int = typer.Option(4, "--limit", help="First N rows from --kids (default 4)."),
    budget: float | None = typer.Option(None, "--budget", help="Shared USD budget across kids."),
    out: Path = typer.Option(
        Path("out/agent"), "--out", help="Output root (run_id subdir created)."
    ),
    publish: bool = typer.Option(
        False, "--publish", help="Upload accepted card.png + card.mp4 to the wall."
    ),
    local: bool = typer.Option(
        False, "--local", help="Upload with this laptop's bucket creds instead of the service."
    ),
) -> None:
    """Evaluate-before-escalate agent, or the slide-sized free-text 4-tool path."""
    from santa.agent import run_agent, run_kids
    from santa.agent.policy import Policy
    from santa.batch import load_kids
    from santa.card import ProfileError, validate_profile
    from santa.config import Settings

    profile_mode = name is not None or age is not None or bool(wish)
    csv_mode = kids is not None
    text_mode = bool(request and request.strip())
    modes = sum([text_mode, profile_mode, csv_mode])
    if modes != 1:
        console.print(
            "[red]Use exactly one of: free-text request, --name/--age/--wish, or --kids PATH.[/red]"
        )
        raise typer.Exit(code=1)

    if text_mode:
        path = run_agent(request or "", out_root=out if out != Path("out/agent") else Path("out"))
        console.print(f"[green]Wrote {path}[/green]")
        return

    try:
        if profile_mode:
            if name is None or age is None:
                raise ProfileError("--name and --age are required together.")
            kid_list = [validate_profile(name, age, wish or "")]
        else:
            kid_list = load_kids(kids or Path("data/kids.csv"), max(1, limit))
    except (ProfileError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    settings = Settings.load()
    policy = Policy.from_file(settings.policy, budget_usd=budget)
    try:
        report = run_kids(
            kid_list,
            policy=policy,
            settings=settings,
            out_root=out,
            publish=publish,
            live=True,
            console=console,
        )
    except Exception as exc:
        console.print(f"[red]setup failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    run_dir = out / report.run_id
    console.print(
        f"[green]Wrote {run_dir}/report.json[/green] "
        f"({report.totals.get('accepted', 0)} accepted, "
        f"{report.totals.get('kept_best', 0)} kept_best, "
        f"{report.totals.get('failed', 0)} failed)"
    )
    for kid_report in report.kids:
        console.print(f"[bold]{kid_report.kid_id}[/bold] · {kid_report.status}")
        for line in kid_report.decision_log:
            if "pass=[" in line:
                if " PASS " in f" {line} " or ": PASS (" in line:
                    console.print(f"  [green]{line}[/green]")
                else:
                    console.print(f"  [yellow]{line}[/yellow]")
            else:
                console.print(f"  [dim]{line}[/dim]")
    if publish:
        for kid_report in report.kids:
            kid_dir = run_dir / kid_report.kid_id
            from santa.agent.kid_tools import stamp_agent_card

            stamp_agent_card(kid_dir)
            paths = [
                p
                for p in (
                    kid_dir / "card.png",
                    kid_dir / "card.mp4",
                    kid_dir / "card.json",
                    kid_dir / "profile.json",
                )
                if p.is_file()
            ]
            if paths:
                _publish_outputs(paths, local=local, object_id=kid_report.kid_id)


@app.command()
def bench(
    kids: Path = typer.Option(
        Path("data/kids.csv"),
        "--kids",
        exists=True,
        dir_okay=False,
        help="CSV of KidProfiles.",
    ),
    limit: int = typer.Option(8, "--limit", help="First N kids."),
    modes: str = typer.Option(
        "pipeline,pipeline-retry-all,agent",
        "--modes",
        help="Comma-separated: pipeline,pipeline-retry-all,agent",
    ),
    out: Path = typer.Option(Path("out/bench"), "--out"),
    budget: float | None = typer.Option(None, "--budget"),
) -> None:
    """Scorecard: pipeline vs pipeline-retry-all vs agent (same kids, same judges)."""
    from santa.agent.bench import run_bench
    from santa.agent.policy import Policy
    from santa.batch import load_kids
    from santa.config import Settings

    settings = Settings.load()
    policy = Policy.from_file(settings.policy, budget_usd=budget)
    try:
        kid_list = load_kids(kids, max(1, limit))
        mode_list = [m.strip() for m in modes.split(",") if m.strip()]
        path = run_bench(
            kid_list,
            modes=mode_list,
            policy=policy,
            settings=settings,
            out_root=out,
        )
    except Exception as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Wrote {path}[/green]")


def _kid_from_args(
    *,
    form: bool,
    profile: Path | None,
    name: str | None,
    age: int | None,
    wish: str | None,
) -> KidProfile:
    from santa.card import ProfileError, validate_profile

    modes = sum([form, profile is not None, name is not None or age is not None or bool(wish)])
    if modes > 1:
        raise ProfileError("Use only one of --form, --profile, or --name/--age/--wish.")
    if form:
        return validate_profile(
            typer.prompt("Child's name"),
            typer.prompt("Age (1–18)", type=int),
            typer.prompt("Wish (optional)", default=""),
        )
    if profile is not None:
        import json

        data = json.loads(profile.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ProfileError("Profile JSON must be an object with name and age.")
        kid = validate_profile(data.get("name", ""), data.get("age", ""), "")
        wishlist = data.get("wishlist")
        if isinstance(wishlist, list):
            kid.wishlist = [str(item) for item in wishlist if str(item).strip()]
        elif str(data.get("wish") or "").strip():
            kid.wishlist = [str(data["wish"]).strip()]
        if data.get("id"):
            kid.id = str(data["id"])
        return kid
    if name is None or age is None:
        raise ProfileError(
            "Pass --form, --profile PATH, or --name and --age (and optional --wish)."
        )
    return validate_profile(name, age, wish or "")


def _print_card_run(run: Any) -> None:
    seen: dict[str, dict[str, Any]] = {}
    for step in run.steps:
        seen[step["role"]] = step
    for role, step in seen.items():
        kind = "fallback" if step["fallback"] else "primary"
        console.print(f"{role}: {step['model']} ({kind}, {step['ms']}ms)")
    console.print(f"[green]Wrote {run.card.png_path}[/green]")
    console.print(f"[green]Wrote {run.card.html_path}[/green]")


def _card_artifact_paths(card: Any) -> list[Path]:
    paths: list[Path] = []
    png = Path(card.png_path) if getattr(card, "png_path", None) else None
    for raw in (getattr(card, "png_path", None), getattr(card, "html_path", None)):
        if not raw:
            continue
        path = Path(raw)
        if path.is_file():
            paths.append(path)
    if png is not None:
        card_json = png.parent / "card.json"
        if card_json.is_file():
            paths.append(card_json)
    return paths


def _publish_outputs(paths: list[Path], *, local: bool, object_id: str | None = None) -> None:
    from santa.publish import PublishError, publish_files

    if not paths:
        return
    try:
        keys = publish_files(paths, local=local, object_id=object_id)
    except PublishError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    for key in keys:
        console.print(f"[green]published {key}[/green]")


@app.command()
def animate(
    png: Path | None = typer.Argument(None, exists=False, readable=False),
    status: Path | None = typer.Option(None, "--status", help="Poll a ticket from --no-wait"),
    motion: str | None = typer.Option(None, "--motion"),
    fresh_music: bool = typer.Option(False, "--fresh-music"),
    mood_bank: bool = typer.Option(False, "--mood-bank"),
    wait: bool = typer.Option(True, "--wait/--no-wait"),
    publish: bool = typer.Option(False, "--publish", help="Upload the MP4 to the wall."),
    local: bool = typer.Option(
        False, "--local", help="Upload with this laptop's bucket creds instead of the service."
    ),
    out: Path | None = typer.Option(None, "--out"),
    offline: bool = typer.Option(
        False, "--offline", help="Copy the bundled fallback MP4; skip endpoints."
    ),
) -> None:
    """Submit a card PNG to Wan (or sora-2), add ACE-Step music, mux to card.mp4."""
    if offline:
        from santa.offline import OfflineError, copy_fallback_video

        dest = Path(out) if out is not None else Path("out") / "card.mp4"
        try:
            path = copy_fallback_video(dest)
        except OfflineError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc
        console.print("[yellow]offline[/yellow] — bundled fallback (endpoints not called)")
        console.print(str(path))
        if publish:
            _publish_outputs([path], local=local)
        return
    if fresh_music and mood_bank:
        console.print("[red]--fresh-music and --mood-bank cannot be combined[/red]")
        raise typer.Exit(code=1)
    settings = Settings.load()
    if status is not None:
        done = poll_ticket(status, settings=settings)
        if done is None:
            console.print("still running")
            raise typer.Exit()
        console.print(str(done))
        if publish:
            _publish_outputs([Path(done)], local=local)
        raise typer.Exit()
    if png is None:
        console.print("[red]Pass a PNG path, or --status <ticket.json>[/red]")
        raise typer.Exit(code=1)
    result = run(
        png,
        settings=settings,
        motion=motion,
        mood_bank=mood_bank,
        fresh_music=fresh_music,
        wait=wait,
        out=out,
    )
    if isinstance(result, dict):
        console.print_json(data=result)
        return
    console.print(str(result))
    if publish:
        _publish_outputs([Path(result)], local=local)


@app.command("animate_batch")
def animate_batch(
    jobs: int = typer.Option(4, "--jobs", help="How many GPU job chunks to submit."),
    run_id: str | None = typer.Option(None, "--run-id"),
    no_wait: bool = typer.Option(False, "--no-wait", help="Submit jobs and return the run id."),
    status: str | None = typer.Option(None, "--status", help="Resume polling a --no-wait run."),
    out: Path = typer.Option(Path("out"), "--out"),
    offline: bool = typer.Option(
        False, "--offline", help="Copy the bundled run summary; skip endpoints and jobs."
    ),
) -> None:
    """K preemptible GPU Jobs over published ``cards/{id}/card.png`` → ``runs/<run_id>/summary.json``."""
    import uuid

    from santa.batch import BatchError, require_card_ids, run_jobs_phase
    from santa.nebius_jobs import NebiusJobError, SdkJobService
    from santa.storage import Storage, StorageError, local_run_dir

    if status:
        _batch_status(status, out)
        return

    if offline:
        import json

        from santa.offline import OfflineError, copy_fallback_summary

        rid = run_id or "offline"
        run_dir = local_run_dir(rid, root=out)
        try:
            dest = copy_fallback_summary(run_dir / "summary.json")
        except OfflineError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from exc
        summary = json.loads(dest.read_text(encoding="utf-8"))
        console.print("[yellow]offline[/yellow] — bundled fallback (endpoints not called)")
        _print_summary(summary, run_dir)
        return

    rid = run_id or uuid.uuid4().hex[:10]
    settings = Settings.load()
    try:
        store = Storage.from_env()
    except Exception as exc:
        console.print(f"[red]Bucket is required for santa animate_batch: {exc}[/red]")
        console.print("Set NEBIUS_BUCKET_NAME (and AWS_* keys) in .env.")
        raise typer.Exit(code=1) from exc
    try:
        card_ids = require_card_ids(store)
    except (BatchError, StorageError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    run_dir = local_run_dir(rid, root=out)
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        svc = SdkJobService.from_env()
    except NebiusJobError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    try:
        if no_wait:
            result = run_jobs_phase(
                kids=card_ids,
                n_jobs=jobs,
                run_id=rid,
                run_dir=run_dir,
                storage=store,
                settings=settings,
                service=svc,
                wait=False,
            )
            console.print(
                f"[green]submitted {len(result.get('jobs') or [])} jobs[/green] "
                f"— santa animate_batch --status {rid}"
            )
            return
        summary = _wait_jobs_live(
            run_jobs_phase,
            include_wait=True,
            kids=card_ids,
            n_jobs=jobs,
            run_id=rid,
            run_dir=run_dir,
            storage=store,
            settings=settings,
            service=svc,
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("[yellow]cancelled submitted jobs[/yellow]")
        raise typer.Exit(code=1) from None
    except NebiusJobError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    _print_summary(summary, run_dir)


def _jobs_table(states: dict[str, str]) -> Table:
    table = Table(title="GPU jobs", show_lines=False, header_style="bold")
    table.add_column("Job")
    table.add_column("State")
    for jid, state in states.items():
        table.add_row(jid, "QUEUED" if state == "PENDING" else state)
    if not states:
        table.add_row("—", "QUEUED")
    return table


def _wait_jobs_live(fn: Any, *, include_wait: bool = True, **kw: Any) -> dict[str, Any]:
    from rich.live import Live

    states: dict[str, str] = {}
    with Live(_jobs_table(states), console=console, refresh_per_second=4) as live:

        def on_state(job_id: str, state: str) -> None:
            states[job_id] = state
            live.update(_jobs_table(states))

        extra: dict[str, Any] = {"on_state": on_state}
        if include_wait:
            extra["wait"] = True
        return cast(dict[str, Any], fn(**kw, **extra))


def _print_summary(summary: dict[str, Any], run_dir: Path) -> None:
    totals = summary.get("totals") or {}
    console.print(
        f"[green]summary[/green] done {totals.get('done', 0)} skipped {totals.get('skipped', 0)} "
        f"failed {totals.get('failed', 0)} cost ${totals.get('cost_usd', 0)} "
        f"saved ${summary.get('savings_usd', 0)} → {run_dir / 'summary.json'}"
    )


def _batch_status(run_id: str, out: Path) -> None:
    import json

    from santa.batch import resume_jobs_phase
    from santa.nebius_jobs import NebiusJobError, SdkJobService
    from santa.storage import Storage, local_run_dir

    run_dir = local_run_dir(run_id, root=out)
    run_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings.load()
    ticket_path = run_dir / "ticket.json"
    if not ticket_path.is_file():
        try:
            store = Storage.from_env()
            ticket_path.write_bytes(store.download(f"runs/{run_id}/ticket.json"))
        except Exception as exc:
            console.print(f"[red]no ticket for run {run_id}: {exc}[/red]")
            raise typer.Exit(code=1) from exc
    else:
        store = Storage.from_env()
    ticket = json.loads(ticket_path.read_text(encoding="utf-8"))
    try:
        svc = SdkJobService.from_env()
        summary = _wait_jobs_live(
            resume_jobs_phase,
            include_wait=False,
            ticket=ticket,
            run_dir=run_dir,
            storage=store,
            settings=settings,
            service=svc,
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print("[yellow]cancelled submitted jobs[/yellow]")
        raise typer.Exit(code=1) from None
    except NebiusJobError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    _print_summary(summary, run_dir)


@app.command()
def publish(
    paths: list[Path] = typer.Argument(
        ..., exists=True, dir_okay=False, readable=True, help="PNG, HTML, JSON, or MP4 files."
    ),
    local: bool = typer.Option(
        False, "--local", help="Upload with this laptop's bucket creds instead of the service."
    ),
) -> None:
    """Upload files to the bucket so they show on /wall. Default: POST /api/publish."""
    _publish_outputs(paths, local=local)


@app.command()
def teardown(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="List what would stop/cancel without changing anything."
    ),
) -> None:
    """Stop your endpoints, cancel lingering jobs, print leftovers and $/h saved."""
    from santa.nebius_jobs import NebiusJobError
    from santa.teardown import ports_from_env, print_report
    from santa.teardown import run as run_teardown

    try:
        endpoints, jobs = ports_from_env()
        report = run_teardown(dry_run=dry_run, endpoints=endpoints, jobs=jobs)
    except NebiusJobError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    print_report(report)


def main() -> None:  # `python -m santa.cli`
    app()


if __name__ == "__main__":
    main()
