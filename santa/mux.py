"""Mux silent MP4 + mp3 → MP4 using the bundled imageio-ffmpeg binary (never PATH ffmpeg)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg  # type: ignore[import-untyped]


class MuxError(RuntimeError):
    """ffmpeg failed to combine video and audio."""


def ffmpeg_exe() -> str:
    return str(imageio_ffmpeg.get_ffmpeg_exe())


def mux(video: Path | str, audio: Path | str, dest: Path | str) -> Path:
    """Copy video, encode audio as AAC, stop at the shorter stream (``-shortest``)."""
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_exe(),
        "-y",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(dest_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "")[-400:]
        raise MuxError(f"ffmpeg mux failed: {detail}") from exc
    if not dest_path.is_file() or dest_path.stat().st_size == 0:
        raise MuxError(f"ffmpeg produced no output at {dest_path}")
    return dest_path
