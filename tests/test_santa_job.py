"""Job entrypoint: fake pipeline on two PNGs → staged MP4s; skip; deterministic mood."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import imageio_ffmpeg
import pytest

from santa.job import run_job


def _ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _silent_mp4(path: Path) -> bytes:
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=32x32:d=0.2:r=16",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path.read_bytes()


def _mp3(path: Path, freq: int) -> None:
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={freq}:duration=0.4",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )


class FakePipeline:
    def __init__(self, mp4: bytes) -> None:
        self.mp4 = mp4
        self.calls: list[tuple[Path, str]] = []

    def render(self, image: Path, prompt: str) -> bytes:
        self.calls.append((image, prompt))
        return self.mp4


def _layout(tmp_path: Path) -> tuple[Path, Path, FakePipeline]:
    data = tmp_path / "data"
    cards = data / "cards"
    moods = data / "audio" / "moods"
    moods.mkdir(parents=True)
    _png(cards / "a.png")
    _png(cards / "b.png")
    _mp3(moods / "playful.mp3", 440)
    _mp3(moods / "warm.mp3", 220)
    chunk = data / "runs" / "r1" / "chunks" / "0.json"
    chunk.parent.mkdir(parents=True)
    chunk.write_text(
        json.dumps([{"id": "a", "mood": "playful"}, {"id": "b", "mood": "warm"}]) + "\n",
        encoding="utf-8",
    )
    silent = _silent_mp4(tmp_path / "silent.mp4")
    return data, chunk, FakePipeline(silent)


def test_fake_pipeline_writes_two_mp4s_via_staged_write(tmp_path: Path) -> None:
    data, chunk, pipe = _layout(tmp_path)
    report = run_job(data_root=data, chunk_path=chunk, run_id="r1", renderer=pipe)
    assert [i.status for i in report.items] == ["done", "done"]
    assert "storybook" in pipe.calls[0][1].lower()
    for kid in ("a", "b"):
        dest = data / "videos" / f"{kid}.mp4"
        assert dest.is_file() and dest.stat().st_size > 0
        assert not (dest.parent / f".{dest.name}.tmp").exists()
    assert len(pipe.calls) == 2
    status = json.loads((data / "runs" / "r1" / "jobs" / "0.json").read_text(encoding="utf-8"))
    assert status["run_id"] == "r1"
    assert [row["id"] for row in status["items"]] == ["a", "b"]


def test_second_run_skips_existing_videos(tmp_path: Path) -> None:
    data, chunk, pipe = _layout(tmp_path)
    run_job(data_root=data, chunk_path=chunk, run_id="r1", renderer=pipe)
    pipe.calls.clear()
    report = run_job(data_root=data, chunk_path=chunk, run_id="r1", renderer=pipe)
    assert [i.status for i in report.items] == ["skipped", "skipped"]
    assert pipe.calls == []
    a = (data / "videos" / "a.mp4").read_bytes()
    b = (data / "videos" / "b.mp4").read_bytes()
    assert a and b


def test_mood_pick_is_deterministic(tmp_path: Path) -> None:
    data, chunk, pipe = _layout(tmp_path)
    run_job(data_root=data, chunk_path=chunk, run_id="r1", renderer=pipe)
    playful = (data / "videos" / "a.mp4").read_bytes()
    warm = (data / "videos" / "b.mp4").read_bytes()
    assert playful != warm

    swapped = data / "runs" / "r1" / "chunks" / "0.json"
    swapped.write_text(
        json.dumps([{"id": "a", "mood": "warm"}, {"id": "b", "mood": "playful"}]) + "\n",
        encoding="utf-8",
    )
    (data / "videos" / "a.mp4").unlink()
    (data / "videos" / "b.mp4").unlink()
    run_job(data_root=data, chunk_path=swapped, run_id="r1", renderer=pipe)
    assert (data / "videos" / "a.mp4").read_bytes() == warm
    assert (data / "videos" / "b.mp4").read_bytes() == playful


def test_partial_card_failure_still_finishes(tmp_path: Path) -> None:
    data, chunk, pipe = _layout(tmp_path)
    (data / "cards" / "b.png").unlink()
    report = run_job(data_root=data, chunk_path=chunk, run_id="r1", renderer=pipe)
    assert [i.status for i in report.items] == ["done", "failed"]
    assert (data / "videos" / "a.mp4").is_file()
    assert not (data / "videos" / "b.mp4").exists()


def test_status_json_updates_after_each_card(tmp_path: Path) -> None:
    data, chunk, _pipe = _layout(tmp_path)
    status_path = data / "runs" / "r1" / "jobs" / "0.json"
    silent = _silent_mp4(tmp_path / "silent2.mp4")

    class MidRunPipeline:
        def render(self, image: Path, prompt: str) -> bytes:
            if image.name == "b.png":
                mid = json.loads(status_path.read_text(encoding="utf-8"))
                assert [row["status"] for row in mid["items"]] == ["done"]
            return silent

    run_job(data_root=data, chunk_path=chunk, run_id="r1", renderer=MidRunPipeline())
    final = json.loads(status_path.read_text(encoding="utf-8"))
    assert [row["status"] for row in final["items"]] == ["done", "done"]


def test_missing_chunk_is_setup_failure(tmp_path: Path) -> None:
    from santa.job import JobSetupError

    with pytest.raises(JobSetupError, match="CHUNK not found"):
        run_job(
            data_root=tmp_path,
            chunk_path=tmp_path / "missing.json",
            run_id="r1",
            renderer=FakePipeline(b""),
        )


def test_main_exits_nonzero_when_chunk_unset(monkeypatch) -> None:
    from santa.job import main

    monkeypatch.delenv("CHUNK", raising=False)
    monkeypatch.delenv("RUN_ID", raising=False)
    assert main([]) == 1


def test_main_exits_nonzero_when_chunk_file_missing(tmp_path: Path, monkeypatch) -> None:
    from santa.job import main

    monkeypatch.setenv("CHUNK", str(tmp_path / "missing.json"))
    monkeypatch.setenv("RUN_ID", "r1")
    assert main(["--data-root", str(tmp_path)]) == 1


def test_main_exits_nonzero_when_chunk_is_not_json(tmp_path: Path, monkeypatch) -> None:
    from santa.job import main

    chunk = tmp_path / "0.json"
    chunk.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("CHUNK", str(chunk))
    monkeypatch.setenv("RUN_ID", "r1")
    assert main(["--data-root", str(tmp_path)]) == 1


def test_pick_mood_track_falls_back_to_default(tmp_path: Path) -> None:
    from santa.job import pick_mood_track

    moods = tmp_path / "moods"
    moods.mkdir()
    (moods / "default.mp3").write_bytes(b"DEF")
    assert pick_mood_track(moods, "warm").name == "default.mp3"
    (moods / "warm.mp3").write_bytes(b"WARM")
    assert pick_mood_track(moods, "warm").name == "warm.mp3"
