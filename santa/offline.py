"""Bundled fallback assets for ``santa … --offline``.

Copies cards, the sample MP4, and a run summary from ``data/fallback/`` so
workshop steps still produce artifacts when endpoints are unreachable.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from santa.config import REPO_ROOT

FALLBACK_DIR = REPO_ROOT / "data" / "fallback"
CARDS_DIR = FALLBACK_DIR / "cards"
VIDEO_PATH = FALLBACK_DIR / "card.mp4"
SUMMARY_PATH = FALLBACK_DIR / "run_summary.json"
MOODS_DIR = FALLBACK_DIR / "moods"

# Names baked into ``data/fallback/cards/card-0N.html`` by scripts/make_fallbacks.py
CARD_STEMS = {
    "mia": "card-01",
    "leo": "card-02",
    "nora": "card-03",
    "sam": "card-04",
}

DEFAULT_STEM = "card-01"
STUB_RUN_ID = "fallback-offline"


class OfflineError(RuntimeError):
    """A bundled fallback file is missing."""


def pick_card_stem(name: str | None = None) -> str:
    if name and name.strip():
        return CARD_STEMS.get(name.strip().lower(), DEFAULT_STEM)
    return DEFAULT_STEM


def _require(path: Path) -> Path:
    if not path.is_file():
        raise OfflineError(f"Missing fallback asset {path}")
    return path


def copy_fallback_card(
    out_root: Path | str,
    *,
    name: str | None = None,
    kid_id: str | None = None,
) -> tuple[Path, Path]:
    """Copy a bundled PNG+HTML into ``out_root/<id>/card.png|html``."""
    stem = pick_card_stem(name)
    png_src = _require(CARDS_DIR / f"{stem}.png")
    html_src = _require(CARDS_DIR / f"{stem}.html")
    dest_dir = Path(out_root) / (kid_id or "offline")
    dest_dir.mkdir(parents=True, exist_ok=True)
    png_dest = dest_dir / "card.png"
    html_dest = dest_dir / "card.html"
    shutil.copyfile(png_src, png_dest)
    html = html_src.read_text(encoding="utf-8").replace(f"{stem}.png", "card.png")
    html_dest.write_text(html, encoding="utf-8")
    return png_dest, html_dest


def copy_fallback_video(dest: Path | str) -> Path:
    """Copy the bundled ``card.mp4`` to ``dest`` (file or directory)."""
    src = _require(VIDEO_PATH)
    path = Path(dest)
    if path.is_dir() or not path.suffix:
        path.mkdir(parents=True, exist_ok=True)
        path = path / "card.mp4"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, path)
    return path


def copy_fallback_summary(dest: Path | str) -> Path:
    """Copy the bundled ``run_summary.json`` to ``dest``."""
    src = _require(SUMMARY_PATH)
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, path)
    return path


def write_stub_summary(
    dest: Path | str | None = None,
    *,
    kids: int = 200,
    jobs: int = 40,
    run_s: float = 1800.0,
) -> Path:
    """Schema-matching summary for ``--offline``. Replace after a live 40-job run."""
    from santa.batch import DEFAULT_KIDS_CSV, JobRecord, build_run_summary, chunk_ids, load_kids

    profiles = load_kids(DEFAULT_KIDS_CSV, kids)
    ids = [k.id for k in profiles]
    chunks = chunk_ids(ids, jobs)
    records = [
        JobRecord(
            job_id=f"offline-job-{i:02d}",
            chunk=f"runs/{STUB_RUN_ID}/chunks/{i}.json",
            platform="gpu-h100-sxm",
            preset="1gpu-16vcpu-200gb",
            preemptible=True,
            state_transitions=[
                {"state": "PENDING", "at": 0.0},
                {"state": "RUNNING", "at": 8.0},
                {"state": "COMPLETED", "at": run_s},
            ],
            run_s=run_s,
            done=list(chunk),
            skipped=[],
            failed=[],
        )
        for i, chunk in enumerate(chunks)
    ]
    summary = build_run_summary(STUB_RUN_ID, ids, records)
    path = Path(dest) if dest is not None else SUMMARY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return path


def write_stub_video(dest: Path | str | None = None) -> Path:
    """Short MP4 from fallback card-01 + warm mood track (no live Wan)."""
    import subprocess

    from santa.mux import ffmpeg_exe

    png = _require(CARDS_DIR / f"{DEFAULT_STEM}.png")
    audio = _require(MOODS_DIR / "warm.mp3")
    path = Path(dest) if dest is not None else VIDEO_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_exe(),
        "-y",
        "-loop",
        "1",
        "-i",
        str(png),
        "-i",
        str(audio),
        "-t",
        "2",
        "-vf",
        "scale=832:480",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        str(path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "")[-400:]
        raise OfflineError(f"ffmpeg stub video failed: {detail}") from exc
    if not path.is_file() or path.stat().st_size == 0:
        raise OfflineError(f"ffmpeg produced no output at {path}")
    return path
