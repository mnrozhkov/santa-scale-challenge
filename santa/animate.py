"""``santa animate``: PNG → video role → audio role → mux → ``card.mp4``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from santa.config import REPO_ROOT, RoleConfig, Settings
from santa.models import LocalTracksAdapter, adapter_for
from santa.mux import mux

PROMPTS_YAML = REPO_ROOT / "config" / "prompts.yaml"
TICKET_NAME = "animate.ticket.json"
DEFAULT_MOOD = "warm"


def load_prompts(path: Path | str | None = None) -> dict[str, Any]:
    p = Path(path) if path else PROMPTS_YAML
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        return {}
    return raw


def mood_for(png: Path) -> str:
    """Read ``wish.mood`` from a sibling card.json / profile; default ``warm``."""
    for name in ("card.json", "profile.json", "profile"):
        candidate = png.parent / name
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        wish = data.get("wish")
        if isinstance(wish, dict) and wish.get("mood"):
            return str(wish["mood"])
        if data.get("mood"):
            return str(data["mood"])
    return DEFAULT_MOOD


def motion_prompt(prompts: dict[str, Any], override: str | None = None) -> str:
    if override and override.strip():
        return override.strip()
    raw = prompts.get("motion") or prompts.get("motion_prompt") or ""
    return str(raw).strip()


def music_prompt(prompts: dict[str, Any], mood: str) -> str:
    table = prompts.get("music") or {}
    if isinstance(table, dict):
        return str(table.get(mood) or table.get(DEFAULT_MOOD) or mood)
    return mood


def audio_adapter(settings: Settings, *, mood_bank: bool = False, injected: Any = None) -> Any:
    """Audio role via ``Resilient``, or ``local_tracks`` when ``--mood-bank``."""
    if injected is not None:
        return injected
    if mood_bank:
        fb = settings.fallback("audio")
        opts = (
            dict(fb.options)
            if fb is not None and fb.adapter == "local_tracks"
            else {"dir": "data/fallback/moods"}
        )
        return LocalTracksAdapter(
            RoleConfig(name="audio", adapter="local_tracks", options=opts, is_fallback=True)
        )
    return adapter_for("audio", settings)


def _dest(png: Path, out: Path | str | None) -> Path:
    if out is None:
        return png.with_name("card.mp4")
    path = Path(out)
    if path.exists() and path.is_dir():
        return path / "card.mp4"
    return path


def _finish(mp4: bytes, dest: Path, audio: Any, prompts: dict[str, Any], mood: str) -> Path:
    mp3 = audio.generate(music_prompt(prompts, mood), mood=mood)
    tmp_v = dest.with_name(f".{dest.stem}.video.tmp.mp4")
    tmp_a = dest.with_name(f".{dest.stem}.audio.tmp.mp3")
    try:
        tmp_v.write_bytes(mp4)
        tmp_a.write_bytes(mp3)
        mux(tmp_v, tmp_a, dest)
    finally:
        tmp_v.unlink(missing_ok=True)
        tmp_a.unlink(missing_ok=True)
    return dest


def run(
    png: Path | str,
    *,
    settings: Settings | None = None,
    motion: str | None = None,
    mood_bank: bool = False,
    wait: bool = True,
    out: Path | str | None = None,
    video: Any = None,
    audio: Any = None,
    prompts: dict[str, Any] | None = None,
) -> Path | dict[str, Any]:
    """Turn ``card.png`` into ``card.mp4``. ``wait=False`` returns a ticket dict."""
    png_path = Path(png)
    if not png_path.is_file():
        raise FileNotFoundError(png_path)
    prompts = load_prompts() if prompts is None else prompts
    motion_text = motion_prompt(prompts, motion)
    mood = mood_for(png_path)
    dest = _dest(png_path, out)
    settings = settings or Settings.load()
    video = adapter_for("video", settings) if video is None else video
    audio = audio_adapter(settings, mood_bank=mood_bank, injected=audio)
    image = png_path.read_bytes()
    if not wait:
        job_id = video.submit(motion_text, image=image)
        ticket = {
            "png": str(png_path.resolve()),
            "out": str(dest if dest.is_absolute() else dest.resolve()),
            "job_id": job_id,
            "motion": motion_text,
            "mood": mood,
            "mood_bank": mood_bank,
        }
        ticket_path = png_path.parent / TICKET_NAME
        ticket_path.write_text(json.dumps(ticket, indent=2) + "\n", encoding="utf-8")
        return ticket
    mp4 = video.generate(motion_text, image=image)
    return _finish(mp4, dest, audio, prompts, mood)


def poll_ticket(
    ticket_path: Path | str,
    *,
    settings: Settings | None = None,
    video: Any = None,
    audio: Any = None,
    prompts: dict[str, Any] | None = None,
) -> Path | None:
    """Resume a ``--no-wait`` ticket. ``None`` means the video job is still running."""
    path = Path(ticket_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    settings = settings or Settings.load()
    video = adapter_for("video", settings) if video is None else video
    result = video.poll(data["job_id"])
    if result is None:
        return None
    prompts = load_prompts() if prompts is None else prompts
    audio = audio_adapter(settings, mood_bank=bool(data.get("mood_bank")), injected=audio)
    dest = Path(data["out"])
    return _finish(result, dest, audio, prompts, str(data.get("mood") or DEFAULT_MOOD))
