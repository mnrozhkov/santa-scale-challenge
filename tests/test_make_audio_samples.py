"""scripts/make_audio_samples.py: kids Christmas prompts → out/audio_samples. No network."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from santa.prompts import MOODS

ROOT = Path(__file__).resolve().parents[1]


def _mod():
    path = ROOT / "scripts" / "make_audio_samples.py"
    spec = importlib.util.spec_from_file_location("make_audio_samples", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeAudio:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.last_metrics: dict[str, object] = {"latency_ms": 3, "fallback": False}

    def generate(self, prompt: str, *, mood: str = "warm") -> bytes:
        self.calls.append((prompt, mood))
        return f"ID3{mood}".encode()


def test_write_samples_writes_mp3s_and_catalog(tmp_path: Path) -> None:
    mod = _mod()
    audio = FakeAudio()
    dest = tmp_path / "audio_samples"
    samples = [
        ("01-storybook-warm", "warm", "warm bells"),
        ("03-playful-sleigh", "playful", "playful pizzicato"),
    ]

    result = mod.write_samples(audio=audio, dest_dir=dest, samples=samples)

    assert result["written"] == 2
    assert result["skipped"] == 0
    assert (dest / "01-storybook-warm.mp3").read_bytes() == b"ID3warm"
    assert (dest / "03-playful-sleigh.mp3").read_bytes() == b"ID3playful"
    catalog = json.loads((dest / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["samples"][0]["prompt"] == "warm bells"
    assert catalog["samples"][0]["fallback"] is False
    assert [mood for _prompt, mood in audio.calls] == ["warm", "playful"]


def test_write_samples_skips_existing_unless_force(tmp_path: Path) -> None:
    mod = _mod()
    dest = tmp_path / "audio_samples"
    dest.mkdir()
    (dest / "01-storybook-warm.mp3").write_bytes(b"OLD")
    samples = [("01-storybook-warm", "warm", "warm bells")]

    first = mod.write_samples(audio=FakeAudio(), dest_dir=dest, samples=samples, force=False)
    assert first["skipped"] == 1
    assert first["written"] == 0
    assert (dest / "01-storybook-warm.mp3").read_bytes() == b"OLD"

    forced = mod.write_samples(audio=FakeAudio(), dest_dir=dest, samples=samples, force=True)
    assert forced == {
        "written": 1,
        "skipped": 0,
        "total": 1,
        "catalog": forced["catalog"],
    }
    assert (dest / "01-storybook-warm.mp3").read_bytes() == b"ID3warm"


def test_default_samples_cover_each_mood() -> None:
    mod = _mod()
    moods = [mood for _sid, mood, _prompt in mod.SAMPLES]
    assert set(moods) == set(MOODS)
    assert all("instrumental" in prompt and "no vocals" in prompt for _s, _m, prompt in mod.SAMPLES)


def test_yaml_samples_use_prompts_table() -> None:
    mod = _mod()
    rows = mod.yaml_samples({"music": {"warm": "warm bells", "playful": "playful pizzicato"}})
    assert rows[0] == ("01-yaml-warm", "warm", "warm bells")
    assert ("02-yaml-playful", "playful", "playful pizzicato") in rows


def test_samples_match_prompts_yaml() -> None:
    from santa.animate import load_prompts

    mod = _mod()
    table = load_prompts()["music"]
    assert {mood: prompt for _sid, mood, prompt in mod.SAMPLES} == {
        tag: str(table[tag]).strip() for tag in MOODS
    }


def test_install_fallback_copies_mood_named_files(tmp_path: Path) -> None:
    mod = _mod()
    source = tmp_path / "out"
    source.mkdir()
    samples = [
        ("01-storybook-warm", "warm", "warm bells"),
        ("03-playful-sleigh", "playful", "playful pizzicato"),
    ]
    (source / "01-storybook-warm.mp3").write_bytes(b"WARM")
    (source / "03-playful-sleigh.mp3").write_bytes(b"PLAY")
    dest = tmp_path / "audio_samples"
    moods = tmp_path / "moods"

    result = mod.install_fallback(
        source_dir=source, samples=samples, samples_dir=dest, moods_dir=moods
    )

    assert result["installed"] == 2
    assert (dest / "01-storybook-warm.mp3").read_bytes() == b"WARM"
    assert (dest / "warm.mp3").read_bytes() == b"WARM"
    assert (dest / "default.mp3").read_bytes() == b"WARM"
    assert (moods / "warm.mp3").read_bytes() == b"WARM"
    assert (moods / "playful.mp3").read_bytes() == b"PLAY"
    catalog = json.loads((dest / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["model"] == "ACE-Step/Ace-Step1.5"
    assert catalog["samples"][0]["prompt"] == "warm bells"
