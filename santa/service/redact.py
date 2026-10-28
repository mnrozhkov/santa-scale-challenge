"""Strip secrets and role URLs from payloads that leave the CPU service."""

from __future__ import annotations

import json
import re
from typing import Any

_DROP_KEYS = frozenset(
    {
        "endpoint",
        "base_url",
        "api_key",
        "api_token",
        "authorization",
        "password",
        "secret",
        "access_token",
        "iam_token",
    }
)

_SECRET_KEY_RE = re.compile(
    r"(NEBIUS_|AWS_|TOKEN_FACTORY_|OPENAI_|SANTA_OPERATOR_|"
    r"IMAGE_ENDPOINT_|VIDEO_ENDPOINT_|AUDIO_ENDPOINT_)",
    re.I,
)

_PUBLIC_PATH_PREFIXES = ("/media/", "/cards/", "/demo/", "/s/", "/api/")
_HTTP_RE = re.compile(r"https?://\S+", re.I)
_PUBLIC_URL_KEYS = frozenset({"png_url", "video_url", "html_url", "url", "og_image", "share_url"})


def _drop_key(key: str) -> bool:
    lowered = key.lower()
    if lowered in _DROP_KEYS:
        return True
    if lowered in {"token", "api_key"}:
        return True
    return bool(_SECRET_KEY_RE.search(key))


def _redact_string(key: str, value: str) -> str:
    if key.lower() in {"png_path", "html_path", "path"}:
        if value.startswith(_PUBLIC_PATH_PREFIXES):
            return value
        if "/Users/" in value or value.startswith("/"):
            return value.rsplit("/", 1)[-1]
    if key.lower() in _PUBLIC_URL_KEYS:
        return value
    if value.startswith("http://") or value.startswith("https://"):
        return ""
    if _HTTP_RE.search(value):
        return _HTTP_RE.sub("", value).strip()
    if "/Users/" in value:
        return ""
    return value


def redact_public(value: Any) -> Any:
    """Return a JSON-safe copy with endpoint URLs, tokens, and local paths removed."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if _drop_key(str(key)):
                continue
            out[str(key)] = (
                _redact_string(str(key), item) if isinstance(item, str) else redact_public(item)
            )
        return out
    if isinstance(value, list):
        return [redact_public(item) for item in value]
    return value


def redact_card_json_bytes(payload: bytes) -> bytes:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return payload
    if not isinstance(data, dict):
        return payload
    return json.dumps(redact_public(data)).encode()


def looks_like_secret(text: str) -> bool:
    if _SECRET_KEY_RE.search(text):
        return True
    lowered = text.lower()
    return "api_key" in lowered or "access-token" in lowered or "bearer " in lowered
