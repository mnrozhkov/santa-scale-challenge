"""Environment-only config for the presenter demo."""

from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_TOKEN_FACTORY_URL = "https://api.tokenfactory.nebius.com/v1"
DEFAULT_TOKEN_FACTORY_MODEL = "openai/gpt-oss-20b"
DEFAULT_IMAGE_MODEL = "sana"


class ImageEndpointConfigError(ValueError):
    """Raised when the Serverless image endpoint is not configured."""


class TokenFactoryConfigError(ValueError):
    """Raised when Token Factory is not configured."""


@dataclass(frozen=True)
class DemoConfig:
    image_endpoint_url: str
    image_endpoint_token: str
    token_factory_api_key: str
    token_factory_base_url: str = DEFAULT_TOKEN_FACTORY_URL
    token_factory_model: str = DEFAULT_TOKEN_FACTORY_MODEL
    image_model: str = DEFAULT_IMAGE_MODEL

    @classmethod
    def from_env(cls) -> DemoConfig:
        image_url = (os.environ.get("IMAGE_ENDPOINT_URL") or "").strip()
        image_token = (os.environ.get("IMAGE_ENDPOINT_TOKEN") or "").strip()
        if not image_url or not image_token:
            raise ImageEndpointConfigError(
                "IMAGE_ENDPOINT_URL and IMAGE_ENDPOINT_TOKEN are required. "
                "The presenter demo does not fall back to Recraft."
            )

        tf_key = (os.environ.get("TOKEN_FACTORY_API_KEY") or "").strip()
        if not tf_key:
            raise TokenFactoryConfigError("TOKEN_FACTORY_API_KEY is required.")

        tf_url = (os.environ.get("TOKEN_FACTORY_BASE_URL") or DEFAULT_TOKEN_FACTORY_URL).strip()
        tf_model = (os.environ.get("TOKEN_FACTORY_MODEL") or DEFAULT_TOKEN_FACTORY_MODEL).strip()
        image_model = (os.environ.get("IMAGE_ENDPOINT_MODEL") or DEFAULT_IMAGE_MODEL).strip()

        return cls(
            image_endpoint_url=_as_openai_v1(image_url),
            image_endpoint_token=image_token,
            token_factory_api_key=tf_key,
            token_factory_base_url=_as_openai_v1(tf_url),
            token_factory_model=tf_model,
            image_model=image_model,
        )


def _as_openai_v1(url: str) -> str:
    cleaned = url.rstrip("/")
    if cleaned.endswith("/v1"):
        return cleaned
    return f"{cleaned}/v1"
