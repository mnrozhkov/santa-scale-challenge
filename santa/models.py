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
from pathlib import Path
from typing import Any, cast

import requests
from openai import OpenAI

from santa.config import (
    REPO_ROOT,
    ConfigError,
    FallbackPolicy,
    RoleConfig,
    Settings,
    fallback_policy,
)

log = logging.getLogger("santa.models")
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class AdapterError(RuntimeError):
    """A model call failed; message is participant-readable."""


def _raw(resp: requests.Response) -> bytes:
    return cast(bytes, resp.content)


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
            png = requests.get(item.url, timeout=60).content
        else:
            raise AdapterError("image endpoint returned neither b64_json nor url")
        self._timed(start, output_size_bytes=len(png), size=size)
        return png


class WanOmniAdapter(_Base):
    """``wan_omni`` — cookbook Wan I2V. Multipart ``POST /v1/videos/sync`` → raw MP4.

    ``generate`` tries async ``POST /v1/videos`` + poll first (after probing ``/v1/models``),
    then falls back to the sync path when the endpoint has no async route.
    """

    _TIMEOUT_S = 600
    _POLL_S = 2
    _DONE = frozenset({"completed", "succeeded", "success", "done"})
    _FAILED = frozenset({"failed", "error", "cancelled", "canceled"})

    def __init__(self, cfg: RoleConfig) -> None:
        super().__init__(cfg)
        self._async_ok: bool | None = None

    def generate(self, prompt: str, *, image: bytes, seed: int | None = None) -> bytes:
        start = time.time()
        if self._async_supported():
            resp = self._post_video(prompt, image, seed, sync=False)
            if resp.status_code in (404, 405, 501):
                resp = self._post_video(prompt, image, seed, sync=True)
        else:
            resp = self._post_video(prompt, image, seed, sync=True)
        if resp.status_code >= 400:
            raise AdapterError(
                f"video call failed ({self.cfg.v1}): HTTP {resp.status_code} {resp.text[:200]}"
            )
        body = self._body_or_wait(resp)
        self._timed(start, output_size_bytes=len(body))
        return body

    def submit(self, prompt: str, *, image: bytes, seed: int | None = None) -> str:
        if not self._async_supported():
            raise AdapterError(
                f"Wan endpoint does not support async POST /v1/videos ({self.cfg.v1}); omit --no-wait"
            )
        resp = self._post_video(prompt, image, seed, sync=False)
        if resp.status_code in (404, 405, 501):
            raise AdapterError(
                f"Wan endpoint does not support async POST /v1/videos ({self.cfg.v1}); omit --no-wait"
            )
        if resp.status_code >= 400:
            raise AdapterError(
                f"video submit failed ({self.cfg.v1}): HTTP {resp.status_code} {resp.text[:200]}"
            )
        job_id = self._job_id(resp)
        if not job_id:
            raise AdapterError(f"async video submit returned no job id ({self.cfg.v1})")
        return job_id

    def poll(self, job_id: str) -> bytes | None:
        status, content = self._poll_once(job_id)
        if status in self._FAILED:
            raise AdapterError(f"video job {job_id} {status}")
        if status in self._DONE:
            return content if content else self._download(job_id)
        return None

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.cfg.api_key}"} if self.cfg.api_key else {}

    def _form(self, prompt: str, seed: int | None) -> dict[str, str]:
        opts = self.cfg.options
        data = {
            "model": self.cfg.model or "",
            "prompt": prompt,
            "size": str(opts.get("size", "832x480")),
            "num_frames": str(opts.get("num_frames", 81)),
            "fps": str(opts.get("fps", 16)),
            "num_inference_steps": str(opts.get("num_inference_steps", 20)),
            "guidance_scale": str(opts.get("guidance_scale", 1.0)),
            "guidance_scale_2": str(opts.get("guidance_scale_2", 1.0)),
            "flow_shift": str(opts.get("flow_shift", 12.0)),
            "boundary_ratio": str(opts.get("boundary_ratio", 0.875)),
        }
        if seed is not None:
            data["seed"] = str(seed)
        return data

    def _files(self, image: bytes) -> dict[str, tuple[str, bytes, str]]:
        return {"input_reference": ("card.png", image, "image/png")}

    def _post_video(
        self, prompt: str, image: bytes, seed: int | None, *, sync: bool
    ) -> requests.Response:
        path = "/videos/sync" if sync else "/videos"
        try:
            return requests.post(
                f"{self.cfg.v1}{path}",
                data=self._form(prompt, seed),
                files=self._files(image),
                headers=self._headers(),
                timeout=self._TIMEOUT_S,
            )
        except requests.RequestException as exc:
            raise AdapterError(f"video call failed ({self.cfg.v1}): {exc}") from exc

    def _async_supported(self) -> bool:
        """GET ``/v1/models``: 404/405/501 means sync-only; otherwise try async first."""
        if self._async_ok is not None:
            return self._async_ok
        try:
            resp = requests.get(f"{self.cfg.v1}/models", headers=self._headers(), timeout=10)
        except requests.RequestException:
            self._async_ok = True
            return True
        self._async_ok = resp.status_code not in (404, 405, 501)
        return self._async_ok

    def _looks_like_mp4(self, resp: requests.Response) -> bool:
        ctype = (resp.headers.get("content-type") or "").lower()
        if "json" in ctype:
            return False
        if not resp.content:
            return False
        if "mp4" in ctype or "octet-stream" in ctype:
            return True
        return b"ftyp" in resp.content[:64]

    def _job_id(self, resp: requests.Response) -> str | None:
        try:
            data = resp.json()
        except ValueError:
            return None
        if not isinstance(data, dict):
            return None
        raw = data.get("id") or data.get("job_id") or data.get("video_id")
        return str(raw) if raw else None

    def _body_or_wait(self, resp: requests.Response) -> bytes:
        if self._looks_like_mp4(resp):
            return _raw(resp)
        job_id = self._job_id(resp)
        if job_id:
            return self._wait(job_id)
        try:
            url = resp.json().get("url") if resp.content else None
        except ValueError:
            url = None
        if url:
            try:
                clip = requests.get(url, headers=self._headers(), timeout=self._TIMEOUT_S)
            except requests.RequestException as exc:
                raise AdapterError(f"video download failed ({url}): {exc}") from exc
            if clip.content:
                return _raw(clip)
        if resp.content:
            return _raw(resp)
        raise AdapterError(f"video endpoint returned no MP4 ({self.cfg.v1})")

    def _wait(self, job_id: str) -> bytes:
        deadline = time.time() + self._TIMEOUT_S
        while time.time() < deadline:
            result = self.poll(job_id)
            if result is not None:
                return result
            time.sleep(self._POLL_S)
        raise AdapterError(f"video job {job_id} timed out")

    def _poll_once(self, job_id: str) -> tuple[str, bytes | None]:
        try:
            resp = requests.get(
                f"{self.cfg.v1}/videos/{job_id}", headers=self._headers(), timeout=30
            )
        except requests.RequestException as exc:
            raise AdapterError(f"video poll failed ({self.cfg.v1}): {exc}") from exc
        if resp.status_code >= 400:
            raise AdapterError(
                f"video poll failed ({self.cfg.v1}): HTTP {resp.status_code} {resp.text[:200]}"
            )
        if self._looks_like_mp4(resp):
            return "completed", _raw(resp)
        try:
            data = resp.json()
        except ValueError:
            return "in_progress", None
        status = str(data.get("status") or data.get("state") or "in_progress").lower()
        if status in self._DONE and data.get("url"):
            try:
                clip = requests.get(data["url"], headers=self._headers(), timeout=self._TIMEOUT_S)
            except requests.RequestException as exc:
                raise AdapterError(f"video download failed: {exc}") from exc
            return status, _raw(clip)
        return status, None

    def _download(self, job_id: str) -> bytes:
        try:
            resp = requests.get(
                f"{self.cfg.v1}/videos/{job_id}/content",
                headers=self._headers(),
                timeout=self._TIMEOUT_S,
            )
        except requests.RequestException as exc:
            raise AdapterError(f"video download failed ({self.cfg.v1}): {exc}") from exc
        if resp.status_code >= 400 or not resp.content:
            raise AdapterError(f"video download failed ({self.cfg.v1}): HTTP {resp.status_code}")
        return _raw(resp)


class AceStepAudioAdapter(_Base):
    """``acestep_audio`` — ``POST /v1/audio/generations`` JSON → mp3 bytes."""

    def generate(self, prompt: str, *, mood: str = "warm") -> bytes:
        start = time.time()
        opts = self.cfg.options
        payload = {
            "model": self.cfg.model,
            "prompt": prompt,
            "task_type": "text2music",
            "thinking": bool(opts.get("thinking", False)),
            "audio_duration": int(opts.get("audio_duration", 8)),
            "inference_steps": int(opts.get("inference_steps", 8)),
            "audio_format": str(opts.get("audio_format", "mp3")),
        }
        headers = {"Authorization": f"Bearer {self.cfg.api_key}"} if self.cfg.api_key else {}
        try:
            resp = requests.post(
                f"{self.cfg.v1}/audio/generations",
                json=payload,
                headers=headers,
                timeout=180,
            )
        except requests.RequestException as exc:
            raise AdapterError(f"audio call failed ({self.cfg.v1}): {exc}") from exc
        if resp.status_code >= 400:
            raise AdapterError(
                f"audio call failed ({self.cfg.v1}): HTTP {resp.status_code} {resp.text[:200]}"
            )
        body = self._mp3_bytes(resp)
        self._timed(start, output_size_bytes=len(body), mood=mood)
        return body

    def _mp3_bytes(self, resp: requests.Response) -> bytes:
        ctype = (resp.headers.get("content-type") or "").lower()
        if "json" in ctype:
            try:
                data = resp.json()
            except ValueError as exc:
                raise AdapterError(f"audio endpoint returned invalid JSON ({self.cfg.v1})") from exc
            raw = data.get("audio") or data.get("b64_json")
            if isinstance(raw, str):
                return base64.b64decode(raw)
            items = data.get("data") or []
            if items and isinstance(items[0], dict) and items[0].get("b64_json"):
                return base64.b64decode(items[0]["b64_json"])
        if resp.content:
            return _raw(resp)
        raise AdapterError(f"audio endpoint returned no mp3 ({self.cfg.v1})")


class OpenAIVideoAdapter(_Base):
    """``openai_video`` — OpenAI Videos API image-to-video (``input_reference``)."""

    _TIMEOUT_S = 600
    _POLL_S = 2
    _DONE = frozenset({"completed", "succeeded", "success", "done"})
    _FAILED = frozenset({"failed", "error", "cancelled", "canceled"})

    def generate(self, prompt: str, *, image: bytes, seed: int | None = None) -> bytes:
        start = time.time()
        job_id = self.submit(prompt, image=image, seed=seed)
        deadline = time.time() + self._TIMEOUT_S
        while time.time() < deadline:
            result = self.poll(job_id)
            if result is not None:
                self._timed(start, output_size_bytes=len(result))
                return result
            time.sleep(self._POLL_S)
        raise AdapterError(f"OpenAI video job {job_id} timed out")

    def submit(self, prompt: str, *, image: bytes, seed: int | None = None) -> str:
        opts = self.cfg.options
        data = {
            "model": self.cfg.model or "",
            "prompt": prompt,
            "size": str(opts.get("size", "1280x720")),
            "seconds": str(opts.get("seconds", 4)),
        }
        headers = {"Authorization": f"Bearer {self.cfg.api_key}"} if self.cfg.api_key else {}
        try:
            resp = requests.post(
                f"{self.cfg.v1}/videos",
                data=data,
                files={"input_reference": ("card.png", image, "image/png")},
                headers=headers,
                timeout=60,
            )
        except requests.RequestException as exc:
            raise AdapterError(f"video call failed ({self.cfg.v1}): {exc}") from exc
        if resp.status_code >= 400:
            raise AdapterError(
                f"video call failed ({self.cfg.v1}): HTTP {resp.status_code} {resp.text[:200]}"
            )
        try:
            job_id = resp.json().get("id")
        except ValueError:
            job_id = None
        if not job_id:
            raise AdapterError(f"OpenAI Videos API returned no id ({self.cfg.v1})")
        return str(job_id)

    def poll(self, job_id: str) -> bytes | None:
        headers = {"Authorization": f"Bearer {self.cfg.api_key}"} if self.cfg.api_key else {}
        try:
            resp = requests.get(f"{self.cfg.v1}/videos/{job_id}", headers=headers, timeout=30)
        except requests.RequestException as exc:
            raise AdapterError(f"video poll failed ({self.cfg.v1}): {exc}") from exc
        if resp.status_code >= 400:
            raise AdapterError(
                f"video poll failed ({self.cfg.v1}): HTTP {resp.status_code} {resp.text[:200]}"
            )
        try:
            data = resp.json()
        except ValueError as exc:
            raise AdapterError(f"video poll returned non-JSON ({self.cfg.v1})") from exc
        status = str(data.get("status") or "").lower()
        if status in self._FAILED:
            raise AdapterError(f"video job {job_id} {status}: {data.get('error') or ''}".strip())
        if status not in self._DONE:
            return None
        try:
            clip = requests.get(
                f"{self.cfg.v1}/videos/{job_id}/content",
                headers=headers,
                timeout=self._TIMEOUT_S,
            )
        except requests.RequestException as exc:
            raise AdapterError(f"video download failed ({self.cfg.v1}): {exc}") from exc
        if clip.status_code >= 400 or not clip.content:
            raise AdapterError(f"video download failed ({self.cfg.v1}): HTTP {clip.status_code}")
        return _raw(clip)


class LocalTracksAdapter(_Base):
    """``local_tracks`` — pick ``dir/<mood>.mp3``, else the bundled default track."""

    def generate(self, prompt: str = "", *, mood: str = "warm") -> bytes:
        start = time.time()
        raw = self.cfg.options.get("dir", "data/fallback/moods")
        directory = Path(raw) if Path(raw).is_absolute() else REPO_ROOT / raw
        chosen = directory / f"{mood}.mp3"
        if not chosen.is_file():
            chosen = directory / "default.mp3"
        if not chosen.is_file():
            raise AdapterError(f"no track for mood {mood!r} in {directory}")
        data = chosen.read_bytes()
        self._timed(start, output_size_bytes=len(data), mood=mood, path=str(chosen))
        return data


_REGISTRY: dict[str, type[_Base]] = {
    "openai_chat": ChatAdapter,
    "openai_images": ImagesAdapter,
    "wan_omni": WanOmniAdapter,
    "openai_video": OpenAIVideoAdapter,
    "acestep_audio": AceStepAudioAdapter,
    "local_tracks": LocalTracksAdapter,
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
