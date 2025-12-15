"""Image generation client for various image generation services."""

import os
import time
from datetime import datetime
from typing import Any

import requests


class ImageClient:
    """Client for image generation APIs (Recraft, TokenFactory, etc.)."""

    def __init__(
        self,
        service: str = "recraft",
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "recraftv3",
    ) -> None:
        """
        Initialize image generation client.

        Args:
            service: Service name ('recraft', 'tokenfactory', 'flux', 'sdxl')
            api_key: API key (required for most services)
            base_url: Base URL (optional, uses defaults if not provided)
            model: Model name to use
        """
        self.service = service
        self.model = model
        self.model_version = f"{service}-{model}-{datetime.now().strftime('%Y%m%d')}"

        if service == "recraft":
            self.base_url = base_url or "https://external.api.recraft.ai/v1"
            self.api_key = api_key or os.getenv("RECRAFT_API_KEY")
        elif service == "tokenfactory":
            self.base_url = base_url or os.getenv(
                "TOKEN_FACTORY_BASE_URL", "https://api.tokenfactory.ai/v1"
            )
            self.api_key = api_key or os.getenv("TOKEN_FACTORY_API_KEY")
        elif service == "flux":
            self.base_url = base_url or os.getenv("FLUX_SELF_HOSTED_URL", "http://localhost:7861")
            self.api_key = api_key
        elif service == "sdxl":
            self.base_url = base_url or os.getenv("SDXL_LIGHTNING_URL", "http://localhost:7860")
            self.api_key = api_key
        else:
            raise ValueError(f"Unsupported service: {service}")

        if not self.api_key and service in ["recraft", "tokenfactory"]:
            raise ValueError(f"API key required for {service} service")

    def generate(
        self,
        prompt: str,
        style: str | None = None,
        size: str = "1024x1024",
        extra_body: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """
        Generate image using the image generation service.

        Args:
            prompt: Image generation prompt
            style: Style for image (service-specific)
            size: Image size (e.g., "1024x1024")
            extra_body: Additional parameters for the API call

        Returns:
            Tuple of (image_url, metrics_dict) where metrics includes:
            - latency_ms: Time taken in milliseconds
            - output_size_bytes: Size of generated image (if available)
            - model: Model name used
            - service: Service name

        Raises:
            ValueError: If the API call fails
        """
        start_time = time.time()
        metrics: dict[str, Any] = {
            "latency_ms": 0,
            "output_size_bytes": None,
            "model": self.model,
            "service": self.service,
        }

        try:
            if self.service == "recraft":
                image_url = self._generate_recraft(prompt, style, size, extra_body)
            elif self.service == "tokenfactory":
                image_url = self._generate_tokenfactory(prompt, style, size, extra_body)
            elif self.service == "flux":
                image_url = self._generate_flux(prompt, size, extra_body)
            elif self.service == "sdxl":
                image_url = self._generate_sdxl(prompt, size, extra_body)
            else:
                raise ValueError(f"Unsupported service: {self.service}")

            metrics["latency_ms"] = (time.time() - start_time) * 1000

            return image_url, metrics

        except requests.exceptions.RequestException as e:
            raise ValueError(f"Image generation API call failed: {str(e)}") from e

    def _generate_recraft(
        self,
        prompt: str,
        style: str | None,
        size: str,
        extra_body: dict[str, Any] | None,
    ) -> str:
        """Generate image using Recraft API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "prompt": prompt,
            "aspect_ratio": size,
            "style": style or "digital_illustration",
        }

        if extra_body:
            payload.update(extra_body)

        response = requests.post(
            f"{self.base_url}/images/generations",
            headers=headers,
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()

        if "data" in data and len(data["data"]) > 0:
            return data["data"][0].get("url", "")
        raise ValueError(f"Unexpected Recraft response format: {data}")

    def _generate_tokenfactory(
        self,
        prompt: str,
        style: str | None,
        size: str,
        extra_body: dict[str, Any] | None,
    ) -> str:
        """Generate image using TokenFactory API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
        }

        if extra_body:
            payload.update(extra_body)

        response = requests.post(
            f"{self.base_url}/images/generations",
            headers=headers,
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()

        if "data" in data and len(data["data"]) > 0:
            return data["data"][0].get("url", "")
        raise ValueError(f"Unexpected TokenFactory response format: {data}")

    def _generate_flux(
        self,
        prompt: str,
        size: str,
        extra_body: dict[str, Any] | None,
    ) -> str:
        """Generate image using self-hosted Flux API."""
        payload: dict[str, Any] = {
            "prompt": prompt,
            "width": int(size.split("x")[0]),
            "height": int(size.split("x")[1]) if "x" in size else int(size.split("x")[0]),
        }

        if extra_body:
            payload.update(extra_body)

        response = requests.post(
            f"{self.base_url}/api/v1/txt2img",
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()

        if "images" in data and len(data["images"]) > 0:
            return data["images"][0]
        raise ValueError(f"Unexpected Flux response format: {data}")

    def _generate_sdxl(
        self,
        prompt: str,
        size: str,
        extra_body: dict[str, Any] | None,
    ) -> str:
        """Generate image using self-hosted SDXL Lightning API."""
        payload: dict[str, Any] = {
            "prompt": prompt,
            "width": int(size.split("x")[0]),
            "height": int(size.split("x")[1]) if "x" in size else int(size.split("x")[0]),
        }

        if extra_body:
            payload.update(extra_body)

        response = requests.post(
            f"{self.base_url}/api/v1/txt2img",
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()

        if "images" in data and len(data["images"]) > 0:
            return data["images"][0]
        raise ValueError(f"Unexpected SDXL response format: {data}")
