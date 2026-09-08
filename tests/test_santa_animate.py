"""``santa animate``: PNG → video role → audio role → mux → card.mp4. No cloud."""

from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import imageio_ffmpeg
from typer.testing import CliRunner

from santa.animate import audio_adapter, load_prompts, mood_for, poll_ticket, run
from santa.cli import app
from santa.config import Settings
from santa.models import AdapterError, LocalTracksAdapter, Resilient
from santa.prompts import MOODS

NOENV = Path("/nonexistent")
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
PROMPTS = {
    "motion": "Gentle storybook motion, no faces, no text.",
    "music": {"warm": "warm bells", "playful": "playful pizzicato"},
}


def _ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _clip_bytes(tmp_path: Path) -> bytes:
    path = tmp_path / "src.mp4"
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


def _mp3_bytes(tmp_path: Path) -> bytes:
    path = tmp_path / "src.mp3"
    subprocess.run(
        [
            _ffmpeg(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=330:duration=0.3",
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path.read_bytes()


class FakeVideo:
    def __init__(self, payload: bytes, job_id: str = "job-1"):
        self.payload = payload
        self.job_id = job_id
        self.prompts: list[str] = []
        self.submitted = False
        self.polls = 0
        self.cfg = SimpleNamespace(adapter="fake_video", model="fake", label="video · fake")
        self.last_metrics: dict = {}

    def generate(self, prompt: str, *, image: bytes, seed: int | None = None) -> bytes:
        self.prompts.append(prompt)
        return self.payload

    def submit(self, prompt: str, *, image: bytes, seed: int | None = None) -> str:
        self.prompts.append(prompt)
        self.submitted = True
        return self.job_id

    def poll(self, job_id: str) -> bytes | None:
        self.polls += 1
        if self.polls < 2:
            return None
        return self.payload


class BoomVideo(FakeVideo):
    def generate(self, prompt: str, *, image: bytes, seed: int | None = None) -> bytes:
        raise AdapterError("wan cold")


class FakeAudio:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.moods: list[str] = []
        self.prompts: list[str] = []
        self.cfg = SimpleNamespace(adapter="fake_audio", model="fake", label="audio · fake")
        self.last_metrics: dict = {}

    def generate(self, prompt: str = "", *, mood: str = "warm") -> bytes:
        self.prompts.append(prompt)
        self.moods.append(mood)
        return self.payload


def test_mood_from_sibling_card_json(tmp_path):
    png = tmp_path / "card.png"
    png.write_bytes(PNG_1PX)
    (tmp_path / "card.json").write_text(
        json.dumps({"wish": {"mood": "playful", "text": "Merry Christmas!"}}),
        encoding="utf-8",
    )
    assert mood_for(png) == "playful"


def test_mood_defaults_to_warm(tmp_path):
    png = tmp_path / "card.png"
    png.write_bytes(PNG_1PX)
    assert mood_for(png) == "warm"


def test_animate_writes_card_mp4_using_wish_mood(tmp_path):
    png = tmp_path / "card.png"
    png.write_bytes(PNG_1PX)
    (tmp_path / "card.json").write_text(json.dumps({"wish": {"mood": "playful"}}), encoding="utf-8")
    video = FakeVideo(_clip_bytes(tmp_path))
    audio = FakeAudio(_mp3_bytes(tmp_path))
    dest = run(png, video=video, audio=audio, prompts=PROMPTS)
    assert dest == tmp_path / "card.mp4"
    assert dest.is_file() and dest.stat().st_size > 0
    assert video.prompts == [PROMPTS["motion"]]
    assert audio.moods == ["playful"]
    assert audio.prompts == [PROMPTS["music"]["playful"]]
    probed = subprocess.run(
        [_ffmpeg(), "-i", str(dest), "-f", "null", "-"], capture_output=True, text=True
    )
    assert probed.returncode == 0, probed.stderr


def test_animate_resilient_video_fallback(tmp_path):
    png = tmp_path / "card.png"
    png.write_bytes(PNG_1PX)
    payload = _clip_bytes(tmp_path)
    video = Resilient(
        BoomVideo(b""),
        FakeVideo(payload),
        "auto",
        "video",
    )
    dest = run(png, video=video, audio=FakeAudio(_mp3_bytes(tmp_path)), prompts=PROMPTS)
    assert dest.is_file()
    assert video.used_fallback


def test_audio_adapter_mood_bank_is_local_tracks(monkeypatch):
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", "k")
    monkeypatch.setenv("IMAGE_ENDPOINT_URL", "https://img.example")
    monkeypatch.setenv("IMAGE_ENDPOINT_TOKEN", "t")
    monkeypatch.setenv("AUDIO_ENDPOINT_URL", "https://ace.example")
    monkeypatch.setenv("AUDIO_ENDPOINT_TOKEN", "atok")
    monkeypatch.delenv("SANTA_FALLBACK", raising=False)
    a = audio_adapter(Settings.load(env_file=NOENV), mood_bank=True)
    assert isinstance(a, LocalTracksAdapter)


def test_no_wait_writes_ticket_and_status_finishes(tmp_path):
    png = tmp_path / "card.png"
    png.write_bytes(PNG_1PX)
    video = FakeVideo(_clip_bytes(tmp_path))
    audio = FakeAudio(_mp3_bytes(tmp_path))
    ticket = run(png, video=video, audio=audio, prompts=PROMPTS, wait=False)
    assert isinstance(ticket, dict) and ticket["job_id"] == "job-1"
    ticket_path = tmp_path / "animate.ticket.json"
    assert ticket_path.is_file()
    assert json.loads(ticket_path.read_text())["job_id"] == "job-1"
    assert video.submitted and not (tmp_path / "card.mp4").exists()
    assert poll_ticket(ticket_path, video=video, audio=audio, prompts=PROMPTS) is None
    dest = poll_ticket(ticket_path, video=video, audio=audio, prompts=PROMPTS)
    assert dest == tmp_path / "card.mp4" and dest.is_file()


def test_cli_publish_uploads_mp4(tmp_path, monkeypatch):
    png = tmp_path / "card.png"
    mp4 = tmp_path / "card.mp4"
    png.write_bytes(PNG_1PX)
    mp4.write_bytes(b"mp4-bytes")
    monkeypatch.setenv("SANTA_SERVICE_URL", "http://santa.test")
    monkeypatch.setattr("santa.cli.Settings.load", lambda: object())
    monkeypatch.setattr("santa.cli.run", lambda *a, **k: mp4)
    posted: list[tuple[str, bytes]] = []

    def fake_post(url, files=None, timeout=None):
        name, data, _ctype = files["file"]
        posted.append((name, data))

        class Resp:
            status_code = 200

            def json(self):
                return {"key": f"videos/{name}"}

            def raise_for_status(self):
                return None

        return Resp()

    monkeypatch.setattr("santa.publish.requests.post", fake_post)
    result = CliRunner().invoke(app, ["animate", str(png), "--publish"])
    assert result.exit_code == 0, result.output
    assert posted == [("card.mp4", b"mp4-bytes")]
    assert "videos/card.mp4" in result.output


def test_cli_fresh_music_passed_to_run(tmp_path, monkeypatch):
    png = tmp_path / "card.png"
    png.write_bytes(PNG_1PX)
    seen: dict = {}

    def fake_run(*a, **k):
        seen.update(k)
        return tmp_path / "card.mp4"

    monkeypatch.setattr("santa.cli.Settings.load", lambda: object())
    monkeypatch.setattr("santa.cli.run", fake_run)
    result = CliRunner().invoke(app, ["animate", str(png), "--fresh-music"])
    assert result.exit_code == 0, result.output
    assert seen.get("fresh_music") is True
    assert seen.get("mood_bank") is False


def test_cli_no_wait_prints_ticket(tmp_path, monkeypatch):
    png = tmp_path / "card.png"
    png.write_bytes(PNG_1PX)
    ticket = {"job_id": "job-1", "png": str(png), "out": str(tmp_path / "card.mp4")}

    monkeypatch.setattr("santa.cli.Settings.load", lambda: object())
    monkeypatch.setattr("santa.cli.run", lambda *a, **k: ticket)
    result = CliRunner().invoke(app, ["animate", str(png), "--no-wait"])
    assert result.exit_code == 0
    assert "job-1" in result.output


def test_prompts_yaml_has_motion_and_moods():
    data = load_prompts()
    text = str(data.get("motion", "")).lower()
    assert "no faces" in text or "no people" in text
    assert "no text" in text or "no letters" in text
    assert set(MOODS) <= set(data.get("music") or {})
