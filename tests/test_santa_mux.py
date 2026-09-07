"""Mux: bundled imageio-ffmpeg, -shortest, AAC. No system ffmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg

from santa.mux import mux


def _ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _make_video(path: Path) -> Path:
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=32x32:d=0.2:r=16",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def _make_audio(path: Path) -> Path:
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.4",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def _probe(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_ffmpeg(), "-i", str(path), "-f", "null", "-"],
        capture_output=True,
        text=True,
    )


def test_mux_writes_playable_mp4_with_aac(tmp_path):
    video = _make_video(tmp_path / "clip.mp4")
    audio = _make_audio(tmp_path / "bed.mp3")
    dest = tmp_path / "card.mp4"
    assert mux(video, audio, dest) == dest
    assert dest.is_file() and dest.stat().st_size > 0
    probed = _probe(dest)
    assert probed.returncode == 0, probed.stderr
    log = probed.stderr.lower()
    assert "audio: aac" in log
    assert "video:" in log
    # imageio-ffmpeg ships ffmpeg only, not ffprobe — same binary is the probe.
