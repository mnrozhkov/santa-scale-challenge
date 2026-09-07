"""Adapters: how a role is called. One class per API shape, chosen by ``RoleConfig.adapter``.

* ``openai_chat``    — Token Factory / OpenAI / any OpenAI-compatible chat server (JSON mode).
* ``openai_images``  — cookbook ``endpoint-sana`` or OpenAI Images: ``POST /v1/images/generations``.
* ``wan_omni``       — cookbook ``endpoint-wan22-i2v-a14b`` (issue 05).
* ``openai_video``   — OpenAI Videos API, the video fallback (issue 05).
* ``acestep_audio``  — cookbook ``endpoint-ace-step-1-5`` (issue 05).
* ``local_tracks``   — bundled royalty-free tracks, the audio fallback (issue 05).

``adapter_for(role, settings)`` returns a ``Resilient`` wrapper: primary first, fallback on
``AdapterError`` (or when the primary is not configured), governed by ``SANTA_FALLBACK``.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any, cast

from openai import OpenAI

from santa.config import ConfigError, FallbackPolicy, RoleConfig, Settings, fallback_policy

log = logging.getLogger("santa.models")
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class AdapterError(RuntimeError):
    """A model call failed; message is participant-readable."""


class _Base:
    def __init__(self, cfg: RoleConfig) -> None:
        self.cfg = cfg
        self.last_metrics: dict[str, Any] = {}

    @property
    def model_version(self) -> str:
        return f"{self.cfg.model or self.cfg.adapter}@{self.cfg.base_url}"

    def _client(self) -> OpenAI:
        # The OpenAI SDK refuses an empty key; templates with auth off accept anything.
        return OpenAI(
            base_url=self.cfg.v1, api_key=self.cfg.api_key or "none", timeout=120, max_retries=1
        )

    def _timed(self, start: float, **extra: Any) -> None:
        self.last_metrics = {
            "latency_ms": round((time.time() - start) * 1000),
            "model": self.cfg.model,
            **extra,
        }


class ChatAdapter(_Base):
    """``openai_chat`` — text and JSON generation."""

    def generate(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        opts = self.cfg.options
        kwargs: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": opts.get("temperature", 0.7) if temperature is None else temperature,
            "max_tokens": opts.get("max_tokens", 400) if max_tokens is None else max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        start = time.time()
        try:
            resp = self._client().chat.completions.create(**kwargs)
        except Exception as exc:
            raise AdapterError(
                f"llm call failed ({self.cfg.model} @ {self.cfg.v1}): {exc}"
            ) from exc
        msg = resp.choices[0].message
        text = msg.content if isinstance(msg.content, str) else None
        if not text:  # some Token Factory models put output in reasoning_content
            text = getattr(msg, "reasoning_content", None) or ""
        usage = getattr(resp, "usage", None)
        self._timed(
            start,
            tokens_in=getattr(usage, "prompt_tokens", None),
            tokens_out=getattr(usage, "completion_tokens", None),
        )
        if not text.strip():
            raise AdapterError(f"llm returned empty content ({self.cfg.model})")
        return text.strip()

    def generate_json(self, prompt: str, **kw: Any) -> dict[str, Any]:
        text = self.generate(prompt, json_mode=True, **kw)
        try:
            return cast(dict[str, Any], json.loads(text))
        except json.JSONDecodeError:
            match = _JSON_BLOCK.search(text)  # tolerate ```json fences / prose around the object
            if match:
                try:
                    return cast(dict[str, Any], json.loads(match.group(0)))
                except json.JSONDecodeError:
                    pass
        raise AdapterError(f"llm did not return JSON: {text[:200]!r}")


class ImagesAdapter(_Base):
    """``openai_images`` — text-to-image; returns PNG bytes."""

    def generate(self, prompt: str, *, seed: int | None = None) -> bytes:
        size = self.cfg.options.get("size", "1024x1024")
        kwargs: dict[str, Any] = {"model": self.cfg.model, "prompt": prompt, "size": size, "n": 1}
        if seed is not None:
            kwargs["extra_body"] = {"seed": seed}
        if "api.openai.com" not in self.cfg.base_url:
            kwargs[
                "response_format"
            ] = "b64_json"  # OpenAI's gpt-image-1 always returns b64 and rejects this arg
        start = time.time()
        try:
            resp = self._client().images.generate(**kwargs)
        except Exception as exc:
            raise AdapterError(f"image call failed ({self.cfg.v1}): {exc}") from exc
        item = resp.data[0]
        if getattr(item, "b64_json", None):
            png = base64.b64decode(item.b64_json)
        elif getattr(item, "url", None):
            import requests  # type: ignore[import-untyped]

            png = requests.get(item.url, timeout=60).content
        else:
            raise AdapterError("image endpoint returned neither b64_json nor url")
        self._timed(start, output_size_bytes=len(png), size=size)
        return png


_REGISTRY: dict[str, type[_Base]] = {
    "openai_chat": ChatAdapter,
    "openai_images": ImagesAdapter,
}


def _build(cfg: RoleConfig) -> _Base:
    cls = _REGISTRY.get(cfg.adapter)
    if cls is None:
        raise AdapterError(
            f"Role '{cfg.name}' uses adapter '{cfg.adapter}' which is not available yet "
            f"(known: {', '.join(sorted(_REGISTRY))})."
        )
    return cls(cfg)


class Resilient:
    """Primary adapter with a fallback. Proxies any method; switches on ``AdapterError``.

    ``used_fallback`` tells callers (and metrics) which one answered.
    """

    def __init__(
        self, primary: _Base | None, fallback: _Base | None, policy: FallbackPolicy, role: str
    ) -> None:
        if primary is None and fallback is None:
            raise ConfigError(f"Role '{role}' is not configured and has no usable fallback.")
        self.primary, self.fallback, self.policy, self.role = primary, fallback, policy, role
        self.used_fallback = primary is None or (policy == "only" and fallback is not None)

    @property
    def active(self) -> _Base:
        return self.fallback if self.used_fallback and self.fallback is not None else self.primary  # type: ignore[return-value]

    @property
    def cfg(self) -> RoleConfig:
        return self.active.cfg

    @property
    def last_metrics(self) -> dict[str, Any]:
        return {**self.active.last_metrics, "fallback": self.used_fallback}

    @property
    def model_version(self) -> str:
        return self.active.model_version

    def __getattr__(self, name: str) -> Callable[..., Any]:
        attr = getattr(self.active, name)
        if not callable(attr):
            raise AttributeError(name)

        def call(*args: Any, **kwargs: Any) -> Any:
            if self.used_fallback or self.fallback is None or self.policy == "off":
                return attr(*args, **kwargs)
            try:
                return attr(*args, **kwargs)
            except AdapterError as exc:
                log.warning(
                    "%s: primary failed (%s) — switching to fallback %s",
                    self.role,
                    exc,
                    self.fallback.cfg.label,
                )
                self.used_fallback = True
                return getattr(self.fallback, name)(*args, **kwargs)

        return call


def adapter_for(role: str, settings: Settings) -> Resilient:
    """Resolve ``role`` into a ``Resilient`` adapter honouring ``SANTA_FALLBACK``."""
    policy = fallback_policy()
    primary: _Base | None = None
    fallback: _Base | None = None

    if policy != "only":
        try:
            primary = _build(settings.role(role))
        except ConfigError as exc:
            if policy == "off" or not settings.has_fallback(role):
                raise
            log.warning("%s: %s — using fallback", role, exc)
    if policy != "off":
        fb_cfg = settings.fallback(role)
        fallback = _build(fb_cfg) if fb_cfg else None
    if primary is None and fallback is None:
        raise ConfigError(
            f"Role '{role}' is not configured, and its fallback needs OPENAI_API_KEY (or is disabled). "
            "Set the role's URL/token in .env, or set OPENAI_API_KEY."
        )
    return Resilient(primary, fallback, policy, role)
