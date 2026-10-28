#!/usr/bin/env python3
"""Generate Christmas kids instrumentals via the audio role for Animate.

Writes ``out/audio_samples/<id>.mp3`` plus ``catalog.json``. ``--install`` copies
the chosen takes into ``data/fallback/audio_samples/`` (mood-named files for
``local_tracks`` / ``--mood-bank``) and ``data/fallback/moods/``.

Prompts match ``config/prompts.yaml`` ``music:`` so the notebook, ``santa animate
--fresh-music``, and ``scripts/make_mood_bank.py`` reproduce the same tracks.

ACE-Step is single-worker — samples run one at a time.

    uv run scripts/make_audio_samples.py
    uv run scripts/make_audio_samples.py --from-yaml
    uv run scripts/make_audio_samples.py --install
    uv run scripts/make_audio_samples.py --force
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Protocol

from santa.animate import load_prompts
from santa.config import REPO_ROOT
from santa.prompts import MOODS

DEFAULT_DEST = REPO_ROOT / "out" / "audio_samples"
FALLBACK_SAMPLES = REPO_ROOT / "data" / "fallback" / "audio_samples"
FALLBACK_MOODS = REPO_ROOT / "data" / "fallback" / "moods"

# Tag-style ACE-Step prompts: kids Christmas, instrumental, no vocals.
# Kept in lockstep with config/prompts.yaml music: (see tests).
SAMPLES: tuple[tuple[str, str, str], ...] = (
    (
        "01-storybook-warm",
        "warm",
        "children storybook, christmas, warm orchestra, soft strings, music box, "
        "twinkling chimes, gentle, kids, instrumental, no vocals",
    ),
    (
        "02-lullaby-piano",
        "calm",
        "christmas lullaby, kids, soft piano, celesta, warm bells, sleepy, gentle, "
        "instrumental, no vocals",
    ),
    (
        "03-playful-sleigh",
        "playful",
        "playful kids christmas, pizzicato strings, woodwinds, light sleigh bells, "
        "cheerful, bright, instrumental, no vocals",
    ),
    (
        "04-musicbox-magic",
        "magical",
        "magical music box, harp sparkles, christmas wonder, children, twinkle, "
        "instrumental, no vocals",
    ),
    (
        "05-cozy-guitar",
        "cozy",
        "cozy fireplace christmas, acoustic guitar, low strings, warm, kids, "
        "instrumental, no vocals",
    ),
    (
        "06-joyful-carol",
        "joyful",
        "joyful sleigh-bell carol, bright strings, kids christmas, cheerful, "
        "instrumental, no vocals",
    ),
    (
        "07-dreamy-snow",
        "dreamy",
        "dreamy falling snow, celesta, soft pad, silent night, children, gentle, "
        "instrumental, no vocals",
    ),
    (
        "08-adventure-trek",
        "adventurous",
        "gentle adventure theme, soft brass, strings, snowy christmas trek, kids, "
        "hopeful, instrumental, no vocals",
    ),
)


class AudioLike(Protocol):
    def generate(self, prompt: str, *, mood: str = "warm") -> bytes:
        ...


def yaml_samples(prompts: dict[str, Any] | None = None) -> list[tuple[str, str, str]]:
    """Current ``config/prompts.yaml`` music lines, one file per mood tag."""
    raw = prompts if prompts is not None else load_prompts()
    table = raw.get("music") if isinstance(raw, dict) else {}
    if not isinstance(table, dict):
        return []
    out: list[tuple[str, str, str]] = []
    for i, tag in enumerate(MOODS, start=1):
        prompt = str(table.get(tag) or "").strip()
        if not prompt:
            continue
        out.append((f"{i:02d}-yaml-{tag}", tag, prompt))
    return out


def _metrics(audio: AudioLike) -> dict[str, Any]:
    raw = getattr(audio, "last_metrics", None)
    return dict(raw) if isinstance(raw, dict) else {}


def write_samples(
    *,
    audio: AudioLike,
    dest_dir: Path,
    samples: list[tuple[str, str, str]] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Call the audio role for each sample and write mp3 + catalog.json."""
    chosen = list(samples) if samples is not None else list(SAMPLES)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    catalog: list[dict[str, Any]] = []
    written = 0
    skipped = 0
    for sample_id, mood, prompt in chosen:
        path = dest / f"{sample_id}.mp3"
        if path.is_file() and not force:
            skipped += 1
            catalog.append(
                {
                    "id": sample_id,
                    "mood": mood,
                    "file": path.name,
                    "prompt": prompt,
                    "bytes": path.stat().st_size,
                    "skipped": True,
                }
            )
            continue
        started = time.time()
        try:
            data = audio.generate(prompt, mood=mood)
        except Exception as exc:  # AdapterError or transport — keep going
            catalog.append(
                {
                    "id": sample_id,
                    "mood": mood,
                    "file": path.name,
                    "prompt": prompt,
                    "error": str(exc),
                    "skipped": False,
                }
            )
            print(f"  {path.name}  {mood}  FAILED  {exc}")
            continue
        elapsed_ms = round((time.time() - started) * 1000)
        path.write_bytes(data)
        written += 1
        metrics = _metrics(audio)
        catalog.append(
            {
                "id": sample_id,
                "mood": mood,
                "file": path.name,
                "prompt": prompt,
                "bytes": len(data),
                "latency_ms": metrics.get("latency_ms", elapsed_ms),
                "fallback": bool(metrics.get("fallback", False)),
                "skipped": False,
            }
        )
        print(f"  {path.name}  {mood}  {len(data)} B  {elapsed_ms} ms")
    (dest / "catalog.json").write_text(
        json.dumps({"dest": str(dest), "samples": catalog}, indent=2) + "\n",
        encoding="utf-8",
    )
    return {"written": written, "skipped": skipped, "total": len(chosen), "catalog": catalog}


def install_fallback(
    *,
    source_dir: Path,
    samples: list[tuple[str, str, str]] | None = None,
    samples_dir: Path = FALLBACK_SAMPLES,
    moods_dir: Path = FALLBACK_MOODS,
) -> dict[str, Any]:
    """Copy chosen takes into the bundled fallback dirs (mood-named + catalog)."""
    chosen = list(samples) if samples is not None else list(SAMPLES)
    src_root = Path(source_dir)
    dest_samples = Path(samples_dir)
    dest_moods = Path(moods_dir)
    dest_samples.mkdir(parents=True, exist_ok=True)
    dest_moods.mkdir(parents=True, exist_ok=True)
    catalog: list[dict[str, Any]] = []
    installed = 0
    warm_bytes: bytes | None = None
    for sample_id, mood, prompt in chosen:
        src = src_root / f"{sample_id}.mp3"
        if not src.is_file():
            raise FileNotFoundError(f"missing sample {src}")
        data = src.read_bytes()
        (dest_samples / f"{sample_id}.mp3").write_bytes(data)
        (dest_samples / f"{mood}.mp3").write_bytes(data)
        (dest_moods / f"{mood}.mp3").write_bytes(data)
        if mood == "warm":
            warm_bytes = data
        installed += 1
        catalog.append(
            {
                "id": sample_id,
                "mood": mood,
                "file": f"{sample_id}.mp3",
                "mood_file": f"{mood}.mp3",
                "prompt": prompt,
                "bytes": len(data),
            }
        )
    default = warm_bytes or (src_root / f"{chosen[0][0]}.mp3").read_bytes()
    (dest_samples / "default.mp3").write_bytes(default)
    (dest_moods / "default.mp3").write_bytes(default)
    payload = {
        "model": "ACE-Step/Ace-Step1.5",
        "options": {
            "audio_duration": 8,
            "inference_steps": 8,
            "audio_format": "mp3",
            "thinking": False,
        },
        "samples": catalog,
    }
    (dest_samples / "catalog.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    return {"installed": installed, "samples_dir": str(dest_samples), "moods_dir": str(dest_moods)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_DEST,
        help="Directory for mp3 + catalog.json (default: out/audio_samples)",
    )
    parser.add_argument(
        "--from-yaml",
        action="store_true",
        help="Generate the current config/prompts.yaml music lines instead of the kids set",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even when the mp3 already exists",
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help="Copy existing takes into data/fallback/audio_samples and data/fallback/moods",
    )
    args = parser.parse_args(argv)

    samples = yaml_samples() if args.from_yaml else list(SAMPLES)
    if not args.install or args.force or args.from_yaml:
        from santa.config import Settings
        from santa.models import adapter_for

        try:
            import truststore

            truststore.inject_into_ssl()
        except Exception:
            pass

        label = "prompts.yaml moods" if args.from_yaml else "kids Christmas candidates"
        print(f"audio samples ({label}) → {args.out}")
        audio = adapter_for("audio", Settings.load())
        result = write_samples(audio=audio, dest_dir=args.out, samples=samples, force=args.force)
        used_fallback = any(
            row.get("fallback") for row in result["catalog"] if not row.get("skipped")
        )
        if used_fallback:
            print(
                "warning: at least one sample came from the audio fallback "
                "(bundled tracks), not ACE-Step. Set AUDIO_ENDPOINT_* and "
                "SANTA_FALLBACK=off to hear the model."
            )
        print(
            f"done: wrote {result['written']}, skipped {result['skipped']} "
            f"of {result['total']} → {args.out}/catalog.json"
        )
    if args.install:
        installed = install_fallback(source_dir=args.out, samples=list(SAMPLES))
        print(
            f"installed {installed['installed']} tracks → "
            f"{installed['samples_dir']} and {installed['moods_dir']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
