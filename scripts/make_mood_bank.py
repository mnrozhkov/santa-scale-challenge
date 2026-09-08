#!/usr/bin/env python3
"""Generate one short instrumental track per mood tag via the audio role.

Writes ``data/fallback/moods/<tag>.mp3`` and uploads ``audio/moods/<tag>.mp3``
so jobs and ``santa animate --mood-bank`` can pick a track without queueing
200 ACE-Step calls on a single-worker endpoint.

    uv run scripts/make_mood_bank.py
    uv run scripts/make_mood_bank.py --force
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Protocol

from santa.animate import load_prompts
from santa.config import REPO_ROOT
from santa.prompts import MOODS

DEFAULT_LOCAL_DIR = REPO_ROOT / "data" / "fallback" / "moods"
PREFIX = "audio/moods"


class AudioLike(Protocol):
    def generate(self, prompt: str, *, mood: str = "warm") -> bytes:
        ...


class StorageLike(Protocol):
    def upload(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        ...


def _music_table(prompts: dict[str, Any] | None) -> dict[str, str]:
    raw = prompts if prompts is not None else load_prompts()
    table = raw.get("music") if isinstance(raw, dict) and "music" in raw else raw
    if not isinstance(table, dict):
        return {}
    return {str(k): str(v).strip() for k, v in table.items()}


def make_mood_bank(
    *,
    audio: AudioLike,
    storage: StorageLike,
    prompts: dict[str, Any] | None = None,
    local_dir: Path,
    force: bool = False,
) -> dict[str, int]:
    """Generate mood tracks locally and upload them. Skip existing files unless ``force``."""
    table = _music_table(prompts)
    tags = [tag for tag in MOODS if tag in table] or list(table)
    dest_dir = Path(local_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    uploaded = 0
    skipped = 0
    for tag in tags:
        dest = dest_dir / f"{tag}.mp3"
        if dest.is_file() and not force:
            skipped += 1
            continue
        prompt = table.get(tag) or tag
        data = audio.generate(prompt, mood=tag)
        dest.write_bytes(data)
        written += 1
        storage.upload(f"{PREFIX}/{tag}.mp3", data, content_type="audio/mpeg")
        uploaded += 1
    return {"written": written, "uploaded": uploaded, "skipped": skipped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local-dir",
        type=Path,
        default=DEFAULT_LOCAL_DIR,
        help="Local mood-track directory (default: data/fallback/moods)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate tracks even when the local mp3 already exists",
    )
    args = parser.parse_args(argv)
    from santa.config import Settings
    from santa.models import adapter_for
    from santa.storage import Storage

    audio = adapter_for("audio", Settings.load())
    store = Storage.from_env()
    result = make_mood_bank(
        audio=audio,
        storage=store,
        local_dir=args.local_dir,
        force=args.force,
    )
    print(
        f"mood bank: wrote {result['written']}, uploaded {result['uploaded']}, "
        f"skipped {result['skipped']} → {args.local_dir} and {PREFIX}/"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
