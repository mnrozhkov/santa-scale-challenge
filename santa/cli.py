"""``santa`` — the participant CLI.

santa doctor
santa card …      (issue 02)
santa agent …     (issue 06)
santa batch …     (issues 07, 09)
santa animate …   (issue 05)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
    """Check .env, Token Factory, your endpoints, fallbacks and batch plumbing. Prints what to fix."""
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
) -> None:
    """Gift rec + wish + illustration → Pillow PNG and shareable HTML."""
    from santa.card import ProfileError, make_card
    from santa.config import Settings

    try:
        kid = _kid_from_args(form=form, profile=profile, name=name, age=age, wish=wish)
    except ProfileError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    card_run = make_card(kid, Settings.load(), out_root=out)
    _print_card_run(card_run)


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


@app.command()
def animate(
    png: Path | None = typer.Argument(None, exists=False, readable=False),
    status: Path | None = typer.Option(None, "--status", help="Poll a ticket from --no-wait"),
    motion: str | None = typer.Option(None, "--motion"),
    fresh_music: bool = typer.Option(False, "--fresh-music"),
    mood_bank: bool = typer.Option(False, "--mood-bank"),
    wait: bool = typer.Option(True, "--wait/--no-wait"),
    publish: bool = typer.Option(False, "--publish"),
    out: Path | None = typer.Option(None, "--out"),
) -> None:
    """Submit a card PNG to Wan (or sora-2), add ACE-Step music, mux to card.mp4."""
    if publish:
        console.print("[red]not implemented (issue 10)[/red]")
        raise typer.Exit(code=1)
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


def main() -> None:  # `python -m santa.cli`
    app()


if __name__ == "__main__":
    main()
