"""Video endpoint adapter — one PNG in, one MP4 out."""

from __future__ import annotations

import os
from dataclasses import dataclass

import requests

from santa_demo.config import _as_openai_v1


class VideoEndpointConfigError(ValueError):
    """Raised when the Wan video endpoint is not configured."""


class VideoEndpointError(RuntimeError):
    """Raised when the video endpoint call fails."""


@dataclass
class VideoClient:
    base_url: str
    token: str

    @classmethod
    def from_env(cls) -> VideoClient:
        url = (os.environ.get("VIDEO_ENDPOINT_URL") or "").strip()
        token = (os.environ.get("VIDEO_ENDPOINT_TOKEN") or "").strip()
        if not url or not token:
            raise VideoEndpointConfigError(
                "VIDEO_ENDPOINT_URL and VIDEO_ENDPOINT_TOKEN are required to animate."
            )
        return cls(base_url=_as_openai_v1(url), token=token)

    def animate(self, png_bytes: bytes, prompt: str = "gentle storybook motion") -> bytes:
        """Call the OpenAI-shaped video endpoint. Returns MP4 bytes."""
        import base64

        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {
            "model": os.environ.get("VIDEO_ENDPOINT_MODEL", "wan"),
            "prompt": prompt,
            "image": f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}",
        }
        try:
            response = requests.post(
                f"{self.base_url}/videos/generations",
                json=payload,
                headers=headers,
                timeout=180,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise VideoEndpointError(f"Video endpoint failed: {exc}") from exc

        content_type = response.headers.get("content-type", "")
        if "mp4" in content_type or "octet-stream" in content_type:
            return response.content
        try:
            body = response.json()
        except ValueError as exc:
            raise VideoEndpointError("Video endpoint did not return MP4 or JSON.") from exc
        url = body.get("url") or (body.get("data") or [{}])[0].get("url")
        if not url:
            raise VideoEndpointError("Video endpoint JSON had no url.")
        clip = requests.get(url, timeout=180)
        clip.raise_for_status()
        return clip.content
