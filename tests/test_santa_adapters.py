"""Adapters: request shapes, response parsing, and primary→fallback switching. No network."""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from santa.config import ConfigError, RoleConfig, Settings
from santa.models import (
    AceStepAudioAdapter,
    AdapterError,
    ChatAdapter,
    ImagesAdapter,
    LocalTracksAdapter,
    OpenAIVideoAdapter,
    Resilient,
    WanOmniAdapter,
    adapter_for,
)

NOENV = Path("/nonexistent")
TF_KEY = "k"  # pragma: allowlist secret
OA_KEY = "oa"  # pragma: allowlist secret
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class FakeCompletions:
    def __init__(self, content, reasoning=None, fail=None):
        self.calls, self._content, self._reasoning, self._fail = [], content, reasoning, fail

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._fail:
            raise self._fail
        msg = SimpleNamespace(content=self._content, reasoning_content=self._reasoning)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg)],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
        )


class FakeImages:
    def __init__(self, b64=None, url=None):
        self.calls, self._b64, self._url = [], b64, url

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(b64_json=self._b64, url=self._url)])


def _client(completions=None, images=None):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions), images=images)


def llm_cfg(**kw):
    base = {
        "name": "llm",
        "adapter": "openai_chat",
        "base_url": "https://tf.example/v1",
        "api_key": TF_KEY,
        "model": "openai/gpt-oss-120b",
        "options": {"temperature": 0.8, "max_tokens": 400},
    }
    return RoleConfig(**{**base, **kw})


def image_cfg(**kw):
    base = {
        "name": "image",
        "adapter": "openai_images",
        "base_url": "https://img.example",
        "api_key": "",
        "model": "sana",
        "options": {"size": "1024x1024"},
    }
    return RoleConfig(**{**base, **kw})


# ── ChatAdapter ───────────────────────────────────────────────────────────────


def test_chat_json_mode_request_shape(monkeypatch):
    fake = FakeCompletions('{"gifts": ["a"], "rationale": "r"}')
    a = ChatAdapter(llm_cfg())
    monkeypatch.setattr(a, "_client", lambda: _client(completions=fake))
    assert a.generate_json("prompt") == {"gifts": ["a"], "rationale": "r"}
    call = fake.calls[0]
    assert call["model"] == "openai/gpt-oss-120b" and call["response_format"] == {
        "type": "json_object"
    }
    assert call["temperature"] == 0.8 and call["max_tokens"] == 400
    assert a.last_metrics["tokens_in"] == 10


def test_chat_json_tolerates_fences_and_prose(monkeypatch):
    a = ChatAdapter(llm_cfg())
    monkeypatch.setattr(
        a,
        "_client",
        lambda: _client(
            completions=FakeCompletions('Sure!\n```json\n{"wish": "hi", "mood": "warm"}\n```')
        ),
    )
    assert a.generate_json("p") == {"wish": "hi", "mood": "warm"}


def test_chat_falls_back_to_reasoning_content(monkeypatch):
    a = ChatAdapter(llm_cfg())
    monkeypatch.setattr(
        a,
        "_client",
        lambda: _client(
            completions=FakeCompletions(None, reasoning='{"wish": "x", "mood": "calm"}')
        ),
    )
    assert a.generate_json("p")["mood"] == "calm"


def test_chat_non_json_is_adapter_error(monkeypatch):
    a = ChatAdapter(llm_cfg())
    monkeypatch.setattr(a, "_client", lambda: _client(completions=FakeCompletions("no json here")))
    with pytest.raises(AdapterError, match="did not return JSON"):
        a.generate_json("p")


# ── ImagesAdapter ─────────────────────────────────────────────────────────────


def test_images_request_shape_and_b64_decode(monkeypatch):
    fake = FakeImages(b64=base64.b64encode(PNG_1PX).decode())
    a = ImagesAdapter(image_cfg())
    monkeypatch.setattr(a, "_client", lambda: _client(images=fake))
    assert a.generate("a fox", seed=42) == PNG_1PX
    call = fake.calls[0]
    assert call["size"] == "1024x1024" and call["response_format"] == "b64_json" and call["n"] == 1
    assert call["extra_body"] == {"seed": 42}
    assert a.last_metrics["output_size_bytes"] == len(PNG_1PX)


def test_images_openai_fallback_omits_response_format(monkeypatch):
    fake = FakeImages(b64=base64.b64encode(PNG_1PX).decode())
    a = ImagesAdapter(
        image_cfg(base_url="https://api.openai.com/v1", model="gpt-image-1", api_key=OA_KEY)
    )
    monkeypatch.setattr(a, "_client", lambda: _client(images=fake))
    a.generate("x")
    assert "response_format" not in fake.calls[0] and "extra_body" not in fake.calls[0]


def test_images_empty_response_is_adapter_error(monkeypatch):
    a = ImagesAdapter(image_cfg())
    monkeypatch.setattr(a, "_client", lambda: _client(images=FakeImages()))
    with pytest.raises(AdapterError, match="neither b64_json nor url"):
        a.generate("x")


# ── Resilient / adapter_for ───────────────────────────────────────────────────


class Boom(ChatAdapter):
    def generate_json(self, prompt, **kw):
        raise AdapterError("primary down")


class Fine(ChatAdapter):
    def generate_json(self, prompt, **kw):
        self.last_metrics = {"model": self.cfg.model}
        return {"from": self.cfg.model}


def test_resilient_switches_on_adapter_error():
    r = Resilient(
        Boom(llm_cfg()), Fine(llm_cfg(model="gpt-4o-mini", is_fallback=True)), "auto", "llm"
    )
    assert r.used_fallback is False
    assert r.generate_json("p") == {"from": "gpt-4o-mini"}
    assert r.used_fallback is True and r.last_metrics == {"model": "gpt-4o-mini", "fallback": True}
    assert r.cfg.is_fallback


def test_resilient_off_policy_raises():
    r = Resilient(Boom(llm_cfg()), Fine(llm_cfg(model="fb")), "off", "llm")
    with pytest.raises(AdapterError, match="primary down"):
        r.generate_json("p")


def test_resilient_only_policy_skips_primary():
    r = Resilient(Boom(llm_cfg()), Fine(llm_cfg(model="fb")), "only", "llm")
    assert r.generate_json("p") == {"from": "fb"} and r.used_fallback


def test_resilient_without_fallback_propagates():
    r = Resilient(Boom(llm_cfg()), None, "auto", "llm")
    with pytest.raises(AdapterError):
        r.generate_json("p")


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("TOKEN_FACTORY_API_KEY", TF_KEY)
    for var in ("IMAGE_ENDPOINT_URL", "IMAGE_ENDPOINT_TOKEN", "OPENAI_API_KEY", "SANTA_FALLBACK"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


def test_adapter_for_uses_fallback_when_primary_unconfigured(env):
    env.setenv("OPENAI_API_KEY", OA_KEY)
    r = adapter_for("image", Settings.load(env_file=NOENV))  # no IMAGE_ENDPOINT_URL
    assert r.used_fallback and r.cfg.model == "gpt-image-1" and r.primary is None


def test_adapter_for_unconfigured_and_no_key_explains(env):
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        adapter_for("image", Settings.load(env_file=NOENV))


def test_adapter_for_off_policy_requires_primary(env):
    env.setenv("OPENAI_API_KEY", OA_KEY)
    env.setenv("SANTA_FALLBACK", "off")
    with pytest.raises(ConfigError, match="IMAGE_ENDPOINT_URL"):
        adapter_for("image", Settings.load(env_file=NOENV))


def test_adapter_for_video_is_wan_omni(env):
    env.setenv("VIDEO_ENDPOINT_URL", "https://v.example")
    env.setenv("VIDEO_ENDPOINT_TOKEN", "v-token")
    env.setenv("SANTA_FALLBACK", "off")
    r = adapter_for("video", Settings.load(env_file=NOENV))
    assert r.cfg.adapter == "wan_omni" and isinstance(r.active, WanOmniAdapter)


# ── WanOmniAdapter ────────────────────────────────────────────────────────────

MP4_FAKE = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32


class FakeResp:
    def __init__(self, status_code=200, content=b"", headers=None, json_data=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self._json = json_data
        self.text = (
            content.decode("utf-8", "replace") if isinstance(content, bytes) else str(content)
        )

    def json(self):
        if self._json is not None:
            return self._json
        raise ValueError("not json")

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            err = requests.HTTPError(f"{self.status_code}")
            err.response = self
            raise err


def video_cfg(**kw):
    base = {
        "name": "video",
        "adapter": "wan_omni",
        "base_url": "https://wan.example",
        "api_key": "tok",  # pragma: allowlist secret
        "model": "Wan-AI/Wan2.2-I2V-A14B-Diffusers",
        "options": {
            "size": "832x480",
            "num_frames": 81,
            "fps": 16,
            "num_inference_steps": 20,
            "guidance_scale": 1.0,
            "guidance_scale_2": 1.0,
            "flow_shift": 12.0,
            "boundary_ratio": 0.875,
        },
    }
    return RoleConfig(**{**base, **kw})


def test_wan_sync_multipart_sends_input_reference_and_returns_mp4(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        if url.endswith("/videos") and not url.endswith("/videos/sync"):
            return FakeResp(status_code=404, content=b"no async")
        captured["url"] = url
        captured["data"] = kwargs.get("data")
        captured["files"] = kwargs.get("files")
        captured["headers"] = kwargs.get("headers")
        return FakeResp(content=MP4_FAKE, headers={"content-type": "video/mp4"})

    monkeypatch.setattr("santa.models.requests.post", fake_post)
    monkeypatch.setattr(
        "santa.models.requests.get",
        lambda url, **kw: FakeResp(json_data={"data": []}, content=b"{}"),
    )
    a = WanOmniAdapter(video_cfg())
    assert a.generate("gentle snow", image=PNG_1PX, seed=7) == MP4_FAKE
    assert captured["url"] == "https://wan.example/v1/videos/sync"
    assert captured["headers"]["Authorization"] == "Bearer tok"
    assert "input_reference" in captured["files"]
    name, blob, ctype = captured["files"]["input_reference"]
    assert name.endswith(".png") and ctype == "image/png"
    data = blob.getvalue() if hasattr(blob, "getvalue") else blob
    assert data == PNG_1PX
    fields = captured["data"]
    assert fields["model"] == "Wan-AI/Wan2.2-I2V-A14B-Diffusers"
    assert fields["prompt"] == "gentle snow"
    assert fields["size"] == "832x480"
    assert fields["num_frames"] == "81"
    assert fields["fps"] == "16"
    assert fields["num_inference_steps"] == "20"
    assert fields["guidance_scale"] == "1.0"
    assert fields["guidance_scale_2"] == "1.0"
    assert fields["flow_shift"] == "12.0"
    assert fields["boundary_ratio"] == "0.875"
    assert fields["seed"] == "7"
    assert a.last_metrics["output_size_bytes"] == len(MP4_FAKE)


def test_wan_models_404_skips_async_and_posts_sync(monkeypatch):
    posts: list[str] = []

    def fake_post(url, **kwargs):
        posts.append(url)
        return FakeResp(content=MP4_FAKE, headers={"content-type": "video/mp4"})

    monkeypatch.setattr("santa.models.requests.post", fake_post)
    monkeypatch.setattr(
        "santa.models.requests.get",
        lambda url, **kw: FakeResp(status_code=404, content=b"no models"),
    )
    a = WanOmniAdapter(video_cfg())
    assert a.generate("gentle snow", image=PNG_1PX) == MP4_FAKE
    assert posts == ["https://wan.example/v1/videos/sync"]


def test_wan_async_submit_polls_then_downloads_mp4(monkeypatch):
    posts: list[str] = []
    gets: list[str] = []
    polls = {"n": 0}

    def fake_post(url, **kwargs):
        posts.append(url)
        assert "input_reference" in kwargs["files"]
        assert url.endswith("/v1/videos")
        return FakeResp(
            json_data={"id": "job-1", "status": "queued"},
            content=b'{"id":"job-1","status":"queued"}',
            headers={"content-type": "application/json"},
        )

    def fake_get(url, **kwargs):
        gets.append(url)
        if url.endswith("/models"):
            return FakeResp(json_data={"data": []}, content=b"{}")
        if url.endswith("/videos/job-1/content"):
            return FakeResp(content=MP4_FAKE, headers={"content-type": "video/mp4"})
        if url.endswith("/videos/job-1"):
            polls["n"] += 1
            status = "in_progress" if polls["n"] < 2 else "completed"
            return FakeResp(
                json_data={"id": "job-1", "status": status},
                content=b"{}",
                headers={"content-type": "application/json"},
            )
        return FakeResp(status_code=404, content=b"missing")

    monkeypatch.setattr("santa.models.requests.post", fake_post)
    monkeypatch.setattr("santa.models.requests.get", fake_get)
    monkeypatch.setattr("santa.models.time.sleep", lambda s: None)
    a = WanOmniAdapter(video_cfg())
    assert a.generate("gentle snow", image=PNG_1PX) == MP4_FAKE
    assert posts == ["https://wan.example/v1/videos"]
    assert any(u.endswith("/videos/job-1") for u in gets)
    assert any(u.endswith("/videos/job-1/content") for u in gets)


def test_wan_submit_returns_ticket_id_without_waiting(monkeypatch):
    def fake_post(url, **kwargs):
        return FakeResp(
            json_data={"id": "job-9", "status": "queued"},
            content=b'{"id":"job-9"}',
            headers={"content-type": "application/json"},
        )

    monkeypatch.setattr("santa.models.requests.post", fake_post)
    monkeypatch.setattr(
        "santa.models.requests.get",
        lambda url, **kw: FakeResp(json_data={"data": []}, content=b"{}"),
    )
    a = WanOmniAdapter(video_cfg())
    assert a.submit("motion", image=PNG_1PX) == "job-9"


def test_wan_poll_none_until_complete(monkeypatch):
    states = iter(
        [
            FakeResp(
                json_data={"id": "job-1", "status": "in_progress"},
                content=b"{}",
                headers={"content-type": "application/json"},
            ),
            FakeResp(
                json_data={"id": "job-1", "status": "completed"},
                content=b"{}",
                headers={"content-type": "application/json"},
            ),
            FakeResp(content=MP4_FAKE, headers={"content-type": "video/mp4"}),
        ]
    )

    def fake_get(url, **kwargs):
        return next(states)

    monkeypatch.setattr("santa.models.requests.get", fake_get)
    a = WanOmniAdapter(video_cfg())
    assert a.poll("job-1") is None
    assert a.poll("job-1") == MP4_FAKE


def test_wan_submit_errors_when_async_unsupported(monkeypatch):
    monkeypatch.setattr(
        "santa.models.requests.post",
        lambda url, **kw: FakeResp(status_code=404, content=b"nope"),
    )
    monkeypatch.setattr(
        "santa.models.requests.get",
        lambda url, **kw: FakeResp(json_data={"data": []}, content=b"{}"),
    )
    a = WanOmniAdapter(video_cfg())
    with pytest.raises(AdapterError, match="does not support async"):
        a.submit("motion", image=PNG_1PX)


# ── AceStepAudioAdapter ───────────────────────────────────────────────────────

MP3_FAKE = b"ID3\x04\x00\x00" + b"\x00" * 24


def audio_cfg(**kw):
    base = {
        "name": "audio",
        "adapter": "acestep_audio",
        "base_url": "https://ace.example",
        "api_key": "atok",  # pragma: allowlist secret
        "model": "ACE-Step/Ace-Step1.5",
        "options": {
            "audio_duration": 8,
            "inference_steps": 8,
            "audio_format": "mp3",
            "thinking": False,
        },
    }
    return RoleConfig(**{**base, **kw})


def test_acestep_json_shape_returns_mp3_bytes(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        captured["headers"] = kwargs.get("headers")
        return FakeResp(content=MP3_FAKE, headers={"content-type": "audio/mpeg"})

    monkeypatch.setattr("santa.models.requests.post", fake_post)
    a = AceStepAudioAdapter(audio_cfg())
    assert a.generate("warm bells, instrumental") == MP3_FAKE
    assert captured["url"] == "https://ace.example/v1/audio/generations"
    assert captured["headers"]["Authorization"] == "Bearer atok"
    body = captured["json"]
    assert body["task_type"] == "text2music"
    assert body["thinking"] is False
    assert body["audio_duration"] == 8
    assert body["inference_steps"] == 8
    assert body["audio_format"] == "mp3"
    assert body["model"] == "ACE-Step/Ace-Step1.5"
    assert body["prompt"] == "warm bells, instrumental"
    assert a.last_metrics["output_size_bytes"] == len(MP3_FAKE)


# ── OpenAIVideoAdapter ────────────────────────────────────────────────────────


def sora_cfg(**kw):
    base = {
        "name": "video",
        "adapter": "openai_video",
        "base_url": "https://api.openai.com/v1",
        "api_key": OA_KEY,
        "model": "sora-2",
        "options": {"size": "1280x720", "seconds": 4},
        "is_fallback": True,
    }
    return RoleConfig(**{**base, **kw})


def test_openai_video_create_poll_download_uses_input_reference(monkeypatch):
    posts: list[dict] = []
    gets: list[str] = []
    polls = {"n": 0}

    def fake_post(url, **kwargs):
        posts.append({"url": url, **kwargs})
        return FakeResp(
            json_data={"id": "video_abc", "status": "queued"},
            content=b'{"id":"video_abc","status":"queued"}',
            headers={"content-type": "application/json"},
        )

    def fake_get(url, **kwargs):
        gets.append(url)
        if url.endswith("/videos/video_abc/content"):
            return FakeResp(content=MP4_FAKE, headers={"content-type": "video/mp4"})
        polls["n"] += 1
        status = "in_progress" if polls["n"] < 2 else "completed"
        return FakeResp(
            json_data={"id": "video_abc", "status": status},
            content=b"{}",
            headers={"content-type": "application/json"},
        )

    monkeypatch.setattr("santa.models.requests.post", fake_post)
    monkeypatch.setattr("santa.models.requests.get", fake_get)
    monkeypatch.setattr("santa.models.time.sleep", lambda s: None)
    a = OpenAIVideoAdapter(sora_cfg())
    assert a.generate("gentle drift", image=PNG_1PX) == MP4_FAKE
    call = posts[0]
    assert call["url"] == "https://api.openai.com/v1/videos"
    assert "input_reference" in call["files"]
    assert call["data"]["model"] == "sora-2"
    assert call["data"]["prompt"] == "gentle drift"
    assert call["data"]["size"] == "1280x720"
    assert call["data"]["seconds"] == "4"
    assert any(u.endswith("/videos/video_abc") for u in gets)
    assert any(u.endswith("/videos/video_abc/content") for u in gets)


# ── LocalTracksAdapter ────────────────────────────────────────────────────────


def test_local_tracks_picks_mood_file_else_default(tmp_path):
    moods = tmp_path / "moods"
    moods.mkdir()
    (moods / "playful.mp3").write_bytes(b"PLAYFUL")
    (moods / "default.mp3").write_bytes(b"DEFAULT")
    a = LocalTracksAdapter(
        RoleConfig(
            name="audio",
            adapter="local_tracks",
            options={"dir": str(moods)},
            is_fallback=True,
        )
    )
    assert a.generate("", mood="playful") == b"PLAYFUL"
    assert a.generate("", mood="warm") == b"DEFAULT"


def test_local_tracks_errors_when_nothing_on_disk(tmp_path):
    empty = tmp_path / "moods"
    empty.mkdir()
    a = LocalTracksAdapter(
        RoleConfig(name="audio", adapter="local_tracks", options={"dir": str(empty)})
    )
    with pytest.raises(AdapterError, match="no track"):
        a.generate("", mood="warm")
