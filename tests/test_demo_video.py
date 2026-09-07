"""S2 — video endpoint on the demo session seam."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from src.data_scheme import KidProfile

from santa_demo.fallbacks import list_fallback_pngs
from santa_demo.session import DemoSession
from santa_demo.video import VideoEndpointConfigError, VideoEndpointError
from tests.test_demo_session import _env, _fake_runner_factory


class FakeVideo:
    def __init__(self, mp4: bytes = b"fake-mp4", fail: bool = False) -> None:
        self.mp4 = mp4
        self.fail = fail
        self.seen: list[bytes] = []

    def animate(self, png_bytes: bytes, prompt: str = "") -> bytes:
        if self.fail:
            raise VideoEndpointError("cold start")
        self.seen.append(png_bytes)
        return self.mp4


def _session(
    monkeypatch, tmp_path: Path, video: FakeVideo, last_png: Path | None = None
) -> DemoSession:
    _env(monkeypatch)
    image = SimpleNamespace(base_url="https://sana.example/v1")
    llm = SimpleNamespace(base_url="https://api.tokenfactory.nebius.com/v1")
    session = DemoSession.from_env(
        llm_client=llm,
        image_client=image,
        card_runner=_fake_runner_factory([]),
        video_client=video,
        output_dir=tmp_path,
    )
    if last_png is not None:
        last_png.write_bytes(b"live-png")
        card = session.generate_card(KidProfile(name="Emma", age=7, wishlist=["stars"]))
        card.png_path = str(last_png)
        session.last_card = card
    return session


def test_animate_uses_live_png(monkeypatch, tmp_path):
    video = FakeVideo(b"mp4-live")
    live = tmp_path / "live.png"
    session = _session(monkeypatch, tmp_path, video, last_png=live)
    out = session.animate()
    assert video.seen == [b"live-png"]
    assert out.read_bytes() == b"mp4-live"
    assert session.last_video_path == str(out)


def test_animate_uses_fallback_when_no_live_card(monkeypatch, tmp_path):
    video = FakeVideo(b"mp4-fallback")
    session = _session(monkeypatch, tmp_path, video)
    assert session.last_card is None
    session.animate()
    fallback = list_fallback_pngs()[0]
    assert video.seen == [fallback.read_bytes()]


def test_animate_endpoint_failure(monkeypatch, tmp_path):
    session = _session(monkeypatch, tmp_path, FakeVideo(fail=True))
    with pytest.raises(VideoEndpointError, match="cold start"):
        session.animate()


def test_animate_missing_env(monkeypatch, tmp_path):
    monkeypatch.delenv("VIDEO_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("VIDEO_ENDPOINT_TOKEN", raising=False)
    _env(monkeypatch)
    image = SimpleNamespace(base_url="https://sana.example/v1")
    llm = SimpleNamespace(base_url="https://api.tokenfactory.nebius.com/v1")
    session = DemoSession.from_env(
        llm_client=llm,
        image_client=image,
        card_runner=_fake_runner_factory([]),
        output_dir=tmp_path,
    )
    with pytest.raises(VideoEndpointConfigError):
        session.animate()
