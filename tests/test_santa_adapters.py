"""Adapters: request shapes, response parsing, and primary→fallback switching. No network."""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from santa.config import ConfigError, RoleConfig, Settings
from santa.models import AdapterError, ChatAdapter, ImagesAdapter, Resilient, adapter_for

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


def test_adapter_for_unknown_adapter_explains(env):
    env.setenv("VIDEO_ENDPOINT_URL", "https://v.example")
    env.setenv("VIDEO_ENDPOINT_TOKEN", "v-token")
    env.setenv("SANTA_FALLBACK", "off")
    with pytest.raises(AdapterError, match="wan_omni.*not available yet"):
        adapter_for("video", Settings.load(env_file=NOENV))
