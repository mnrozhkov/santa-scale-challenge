"""scripts/make_mood_bank.py: mood tags → local mp3 + audio/moods/<tag>.mp3. No network."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from santa.prompts import MOODS
from santa.storage import MemoryStorage

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    path = ROOT / "scripts" / "make_mood_bank.py"
    spec = importlib.util.spec_from_file_location("make_mood_bank", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeAudio:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, prompt: str, *, mood: str = "warm") -> bytes:
        self.calls.append((prompt, mood))
        return f"ID3{mood}".encode()


class RecordingStorage(MemoryStorage):
    def __init__(self) -> None:
        super().__init__()
        self.types: dict[str, str] = {}

    def upload(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        if content_type:
            self.types[key] = content_type
        super().upload(key, data, content_type=content_type)


def test_make_mood_bank_writes_eight_mp3s_and_uploads(tmp_path: Path) -> None:
    mod = _mod()
    audio = FakeAudio()
    store = RecordingStorage()
    local = tmp_path / "moods"
    (local / "default.mp3").parent.mkdir(parents=True)
    (local / "default.mp3").write_bytes(b"KEEP")

    result = mod.make_mood_bank(audio=audio, storage=store, local_dir=local)

    assert result == {"written": 8, "uploaded": 8, "skipped": 0}
    assert (local / "default.mp3").read_bytes() == b"KEEP"
    for tag in MOODS:
        payload = f"ID3{tag}".encode()
        assert (local / f"{tag}.mp3").read_bytes() == payload
        assert store.download(f"audio/moods/{tag}.mp3") == payload
        assert store.types[f"audio/moods/{tag}.mp3"] == "audio/mpeg"
    assert [mood for _prompt, mood in audio.calls] == list(MOODS)
    assert all(prompt for prompt, _mood in audio.calls)


def test_make_mood_bank_skips_existing_local_unless_force(tmp_path: Path) -> None:
    mod = _mod()
    audio = FakeAudio()
    store = RecordingStorage()
    local = tmp_path / "moods"
    local.mkdir()
    (local / "warm.mp3").write_bytes(b"OLD")
    prompts = {"warm": "warm bells", "playful": "playful pizzicato"}

    first = mod.make_mood_bank(
        audio=audio, storage=store, prompts=prompts, local_dir=local, force=False
    )
    assert first["skipped"] == 1
    assert first["written"] == 1
    assert first["uploaded"] == 1
    assert (local / "warm.mp3").read_bytes() == b"OLD"
    assert not store.exists("audio/moods/warm.mp3")
    assert store.download("audio/moods/playful.mp3") == b"ID3playful"

    forced = mod.make_mood_bank(
        audio=FakeAudio(), storage=store, prompts=prompts, local_dir=local, force=True
    )
    assert forced == {"written": 2, "uploaded": 2, "skipped": 0}
    assert (local / "warm.mp3").read_bytes() == b"ID3warm"
    assert store.download("audio/moods/warm.mp3") == b"ID3warm"


def test_committed_fallback_moods_cover_all_tags() -> None:
    from santa.config import REPO_ROOT

    moods = REPO_ROOT / "data" / "fallback" / "moods"
    for tag in MOODS:
        assert (moods / f"{tag}.mp3").is_file(), tag
    assert (moods / "default.mp3").is_file()
