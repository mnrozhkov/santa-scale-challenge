"""Centralized image model configuration for evaluation pipelines."""

import os
from typing import Any

from src.clients.image_client import ImageClient


class ImageModelConfig:
    """Configuration for an image generation model."""

    def __init__(
        self,
        name: str,
        client: ImageClient,
        cost_per_image: float,
    ) -> None:
        self.name = name
        self.client = client
        self.cost_per_image = cost_per_image

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for backward compatibility."""
        return {
            "name": self.name,
            "service": self._get_service_name(),
            "client": self.client,
            "cost_per_image": self.cost_per_image,
        }

    def _get_service_name(self) -> str:
        """Extract service name from base_url."""
        base_url = self.client.base_url.lower()
        if "recraft" in base_url:
            return "recraft"
        elif "tokenfactory" in base_url:
            return "tokenfactory"
        elif "flux" in base_url or "7861" in base_url:
            return "flux"
        elif "sdxl" in base_url or "7860" in base_url:
            return "sdxl"
        else:
            return "unknown"


def get_available_image_models(
    model_names: list[str] | None = None,
    include_recraft: bool = True,
    include_tokenfactory: bool = True,
    include_self_hosted: bool = True,
) -> list[ImageModelConfig]:
    """
    Get list of available image model configurations based on environment variables.

    Args:
        model_names: Optional list of specific model names to include (filters results)
        include_recraft: Whether to include Recraft models
        include_tokenfactory: Whether to include TokenFactory models
        include_self_hosted: Whether to include self-hosted models (Flux, SDXL)

    Returns:
        List of ImageModelConfig objects
    """
    models: list[ImageModelConfig] = []

    # Recraft models
    if include_recraft and os.getenv("RECRAFT_API_KEY"):
        recraft_models = [
            ImageModelConfig(
                name="recraftv3",
                client=ImageClient(
                    base_url="https://external.api.recraft.ai/v1",
                    api_key=os.getenv("RECRAFT_API_KEY"),
                    model="recraftv3",
                ),
                cost_per_image=0.01,
            ),
        ]
        models.extend(recraft_models)

    # TokenFactory models
    if (
        include_tokenfactory
        and os.getenv("TOKEN_FACTORY_API_KEY")
        and os.getenv("TOKEN_FACTORY_BASE_URL")
    ):
        tf_base_url = os.getenv("TOKEN_FACTORY_BASE_URL").rstrip("/")
        tf_api_key = os.getenv("TOKEN_FACTORY_API_KEY")

        tf_models = [
            ImageModelConfig(
                name="tokenfactory-flux-schnell",
                client=ImageClient(
                    base_url=tf_base_url,
                    api_key=tf_api_key,
                    model="black-forest-labs/flux-schnell",
                ),
                cost_per_image=0.005,
            ),
            ImageModelConfig(
                name="tokenfactory-flux-dev",
                client=ImageClient(
                    base_url=tf_base_url,
                    api_key=tf_api_key,
                    model="black-forest-labs/flux-dev",
                ),
                cost_per_image=0.01,
            ),
        ]
        models.extend(tf_models)

    # Self-hosted models
    if include_self_hosted:
        # Flux self-hosted
        flux_url = os.getenv("FLUX_SELF_HOSTED_URL")
        if flux_url:
            models.append(
                ImageModelConfig(
                    name="flux-dev",
                    client=ImageClient(
                        base_url=flux_url,
                        api_key=None,
                        model="flux-dev",
                    ),
                    cost_per_image=0.0,
                )
            )

        # SDXL Lightning self-hosted
        sdxl_url = os.getenv("SDXL_LIGHTNING_URL")
        if sdxl_url:
            models.append(
                ImageModelConfig(
                    name="sdxl-lightning",
                    client=ImageClient(
                        base_url=sdxl_url,
                        api_key=None,
                        model="sdxl-lightning",
                    ),
                    cost_per_image=0.0,
                )
            )

    # Filter by model names if specified
    if model_names:
        models = [m for m in models if m.name in model_names]

    return models


def get_image_models_for_evaluation(
    model_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Get image models in dictionary format for evaluation notebooks (backward compatibility).

    Args:
        model_names: Optional list of specific model names to include

    Returns:
        List of model dictionaries compatible with existing evaluation code
    """
    models = get_available_image_models(model_names=model_names)
    return [m.to_dict() for m in models]
