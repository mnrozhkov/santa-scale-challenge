"""Image generation client for OpenAI-compatible and self-hosted image services."""

import base64
import time
from datetime import datetime
from typing import Any

try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

import requests


class ImageClient:
    """Client for OpenAI-compatible image generation services and self-hosted APIs.

    Provides a unified API: client.generate(prompt) that works for all services.
    All images are generated at 1024x1024 in PNG format with service-appropriate defaults.
    """

    # Hardcoded defaults for all services
    DEFAULT_SIZE = "1024x1024"
    DEFAULT_WIDTH = 1024
    DEFAULT_HEIGHT = 1024
    DEFAULT_FORMAT = "png"
    DEFAULT_SEED = -1  # Random seed
    DEFAULT_STYLE = "digital_illustration"  # For Recraft

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model: str = "recraftv3",
    ) -> None:
        """
        Initialize image generation client.

        Args:
            base_url: Base URL for the image generation service
            api_key: API key (required for most services, optional for self-hosted)
            model: Model name to use
        """
        # Normalize base_url: remove trailing slashes and ensure no double slashes
        normalized_url = base_url.rstrip("/")
        # Remove any double slashes (except after http:// or https://)
        if "://" in normalized_url:
            parts = normalized_url.split("://", 1)
            normalized_url = parts[0] + "://" + parts[1].replace("//", "/")
        self.base_url = normalized_url
        self.api_key = api_key
        self.model = model
        self.model_version = f"{model}-{datetime.now().strftime('%Y%m%d')}"

        # Determine service type for applying appropriate defaults
        self.service_type = self._detect_service_type()

        # Determine if this is an OpenAI-compatible API
        self.is_openai_compatible = (
            "openai.com" in self.base_url
            or "recraft.ai" in self.base_url
            or "tokenfactory" in self.base_url
            or self.base_url.endswith("/v1")
        )

        # Initialize OpenAI client for compatible APIs
        if self.is_openai_compatible:
            if not OPENAI_AVAILABLE:
                raise ValueError(
                    "OpenAI library is required for OpenAI-compatible image APIs. "
                    "Install with: pip install openai"
                )
            # OpenAI SDK: ensure base_url doesn't end with slash to avoid double slashes
            client_base_url = self.base_url.rstrip("/")

            self.client = OpenAI(
                base_url=client_base_url,
                api_key=self.api_key,
            )

    def _detect_service_type(self) -> str:
        """Detect service type from base_url to apply appropriate defaults."""
        base_url_lower = self.base_url.lower()
        if "recraft" in base_url_lower:
            return "recraft"
        elif "tokenfactory" in base_url_lower:
            return "tokenfactory"
        elif "flux" in base_url_lower or ":7861" in base_url_lower:
            return "flux"
        elif "sdxl" in base_url_lower or ":7860" in base_url_lower:
            return "sdxl"
        else:
            return "unknown"

    def generate(self, prompt: str) -> tuple[str, dict[str, Any]]:
        """
        Generate image using the image generation service.

        Unified API: all services use the same simple interface.
        - All images are 1024x1024
        - All images are PNG format
        - Service-specific defaults are applied automatically
        - Always returns a URL (HTTP URL or data URL for base64 images)

        Args:
            prompt: Image generation prompt

        Returns:
            Tuple of (image_url, metrics_dict) where:
            - image_url: Always a URL string (HTTP URL or data:image/png;base64,...)
            - metrics includes:
                - latency_ms: Time taken in milliseconds
                - output_size_bytes: Size of generated image (if available)
                - model: Model name used

        Raises:
            ValueError: If the API call fails
        """
        start_time = time.time()
        metrics: dict[str, Any] = {
            "latency_ms": 0,
            "output_size_bytes": None,
            "model": self.model,
        }

        try:
            if self.is_openai_compatible:
                image_data = self._generate_openai_compatible(prompt)
            else:
                # Self-hosted services (Flux, SDXL) that don't use OpenAI-compatible API
                image_data = self._generate_self_hosted(prompt)

            # Convert to URL format if needed (base64 -> data URL)
            image_url = self._ensure_url_format(image_data)

            metrics["latency_ms"] = (time.time() - start_time) * 1000

            return image_url, metrics

        except Exception as e:
            error_msg = f"Image generation API call failed: {str(e)}"
            # Check for double slash issues in URL
            if "//" in str(e) and "/v1//" in str(e):
                error_msg += (
                    f"\n   → URL construction issue detected. Base URL: {self.base_url}"
                    f"\n   → Ensure base_url ends with '/v1' (no trailing slash after v1)"
                )
            elif "authentication" in str(e).lower() or "api key" in str(e).lower():
                error_msg += "\n   → Check that your API key is correct and not expired"
            elif "quota" in str(e).lower() or "balance" in str(e).lower():
                error_msg += "\n   → Check your API units balance"
            elif "404" in str(e):
                error_msg += (
                    f"\n   → Endpoint not found. Base URL: {self.base_url}"
                    f"\n   → Verify the base_url is correct for the service"
                )
            raise ValueError(error_msg) from e

    def _generate_openai_compatible(self, prompt: str) -> str:
        """Generate image using OpenAI-compatible API (Recraft, TokenFactory, etc.)."""
        # Build base parameters
        params: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
        }

        # Apply service-specific defaults
        if self.service_type == "recraft":
            # Recraft uses size parameter and style in extra_body
            params["size"] = self.DEFAULT_SIZE
            params["extra_body"] = {
                "style": self.DEFAULT_STYLE,
            }
        elif self.service_type == "tokenfactory":
            # TokenFactory uses response_format="url" to get HTTP URLs
            # See: https://docs.tokenfactory.nebius.com/api-reference/examples/image-generation#response
            params["response_format"] = "url"
            params["extra_body"] = {
                "response_extension": self.DEFAULT_FORMAT,
                "width": self.DEFAULT_WIDTH,
                "height": self.DEFAULT_HEIGHT,
                "seed": self.DEFAULT_SEED,
            }
        else:
            # Other OpenAI-compatible services
            params["size"] = self.DEFAULT_SIZE

        # Generate image
        response = self.client.images.generate(**params)

        # Extract image URL or base64 data
        if hasattr(response, "data") and len(response.data) > 0:
            image_obj = response.data[0]
            # Check if it's a URL or base64
            if hasattr(image_obj, "url") and image_obj.url:
                return image_obj.url
            elif hasattr(image_obj, "b64_json") and image_obj.b64_json:
                # Return base64 - will be converted to data URL in _ensure_url_format
                return image_obj.b64_json
            elif hasattr(image_obj, "revised_prompt"):
                # Some services return revised_prompt, try to get URL from response
                return str(image_obj)
        else:
            raise ValueError(f"Unexpected response format: {response}")

        raise ValueError(f"Could not extract image from response: {response}")

    def _generate_self_hosted(self, prompt: str) -> str:
        """Generate image using self-hosted API (Flux, SDXL)."""
        payload: dict[str, Any] = {
            "prompt": prompt,
            "width": self.DEFAULT_WIDTH,
            "height": self.DEFAULT_HEIGHT,
        }

        # Determine endpoint based on base_url pattern
        if "/api/v1" in self.base_url:
            endpoint = f"{self.base_url}/txt2img"
        else:
            endpoint = f"{self.base_url}/api/v1/txt2img"

        response = requests.post(endpoint, json=payload, timeout=120)
        response.raise_for_status()
        data = response.json()

        if "images" in data and len(data["images"]) > 0:
            # Self-hosted services typically return base64-encoded images
            # Return base64 - will be converted to data URL in _ensure_url_format
            return data["images"][0]
        raise ValueError(f"Unexpected self-hosted API response format: {data}")

    def _base64_to_data_url(self, base64_data: str) -> str:
        """
        Convert base64 encoded image to data URL format.

        Args:
            base64_data: Base64 encoded image string (with or without data URL prefix)

        Returns:
            Data URL string (data:image/png;base64,...)
        """
        # Remove data URL prefix if present
        if base64_data.startswith("data:image"):
            return base64_data

        # Ensure it's valid base64
        try:
            # Validate by decoding
            base64.b64decode(base64_data)
            return f"data:image/{self.DEFAULT_FORMAT};base64,{base64_data}"
        except Exception:
            # If decoding fails, assume it's already in the right format or return as-is
            return base64_data

    def _ensure_url_format(self, image_data: str) -> str:
        """
        Ensure image data is in URL format (HTTP URL or data URL).

        Args:
            image_data: Image data (URL, base64, or data URL)

        Returns:
            URL string (HTTP URL or data URL)
        """
        # If it's already a URL (HTTP or data), return as-is
        if image_data.startswith("http://") or image_data.startswith("https://"):
            return image_data
        if image_data.startswith("data:image"):
            return image_data

        # Otherwise, assume it's base64 and convert to data URL
        return self._base64_to_data_url(image_data)
