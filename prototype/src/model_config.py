"""Centralized model configuration for all evaluation pipelines."""

import os
from typing import Any

from src.clients.llm_client import LLMClient


class ModelConfig:
    """Configuration for an LLM model."""

    def __init__(
        self,
        name: str,
        client: LLMClient,
        cost_per_1m_tokens_in: float,
        cost_per_1m_tokens_out: float,
        cost_infra_per_hour: float | None = None,
    ) -> None:
        self.name = name
        self.client = client
        self.cost_per_1m_tokens_in = cost_per_1m_tokens_in
        self.cost_per_1m_tokens_out = cost_per_1m_tokens_out
        self.cost_infra_per_hour = cost_infra_per_hour
        self.is_self_hosted = cost_infra_per_hour is not None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for backward compatibility."""
        return {
            "name": self.name,
            "client": self.client,
            "cost_per_1m_tokens_in": self.cost_per_1m_tokens_in,
            "cost_per_1m_tokens_out": self.cost_per_1m_tokens_out,
            "cost_infra_per_hour": self.cost_infra_per_hour,
            "is_self_hosted": self.is_self_hosted,
        }


def get_available_models(
    model_names: list[str] | None = None,
    include_openai: bool = False,
    include_token_factory: bool = False,
    include_self_hosted: bool = False,
) -> list[ModelConfig]:
    """
    Get list of available model configurations based on environment variables.

    Args:
        model_names: Optional list of specific model names to include (filters results)
        include_openai: Whether to include OpenAI models
        include_token_factory: Whether to include Token Factory models
        include_vllm: Whether to include vLLM models

    Returns:
        List of ModelConfig objects
    """
    models: list[ModelConfig] = []

    # OpenAI models
    if include_openai and os.getenv("OPENAI_API_KEY"):
        openai_base_url = "https://api.openai.com/v1"
        openai_api_key = os.getenv("OPENAI_API_KEY")

        openai_models = [
            ModelConfig(
                name="gpt-4o-mini",
                client=LLMClient(
                    base_url=openai_base_url,
                    api_key=openai_api_key,
                    model="gpt-4o-mini",
                ),
                cost_per_1m_tokens_in=0.15,
                cost_per_1m_tokens_out=0.6,
            ),
            ModelConfig(
                name="openai-gpt-3.5-turbo",
                client=LLMClient(
                    base_url=openai_base_url,
                    api_key=openai_api_key,
                    model="gpt-3.5-turbo",
                ),
                cost_per_1m_tokens_in=1.5,
                cost_per_1m_tokens_out=2.0,
            ),
        ]
        models.extend(openai_models)

    # Token Factory models
    if include_token_factory and os.getenv("TOKEN_FACTORY_API_KEY"):
        tf_base_url = "https://api.tokenfactory.nebius.com/v1/"
        tf_api_key = os.getenv("TOKEN_FACTORY_API_KEY")

        tf_models = [
            ModelConfig(
                name="tf/gpt-oss-20b",
                client=LLMClient(
                    base_url=tf_base_url, api_key=tf_api_key, model="openai/gpt-oss-20b"
                ),
                cost_per_1m_tokens_in=0.15,
                cost_per_1m_tokens_out=0.6,
            ),
            ModelConfig(
                name="tf/DeepSeek-R1-0528",
                client=LLMClient(
                    base_url=tf_base_url, api_key=tf_api_key, model="deepseek-ai/DeepSeek-R1-0528"
                ),
                cost_per_1m_tokens_in=0.8,
                cost_per_1m_tokens_out=2.4,
            ),
        ]
        models.extend(tf_models)

    # Self-hosted models (any inference engine with OpenAI-compatible API)
    if include_self_hosted:
        # Get infrastructure cost from environment variable (default: 2.50 USD/hour)

        self_hosted_models = [
            # ModelConfig(
            #     name="santa-deepseek-r1",
            #     client=LLMClient(
            #         base_url=os.getenv("SANTA_DEEPSEEK_R1_URL"),
            #         api_key=os.getenv("SANTA_DEEPSEEK_R1_API_KEY"),
            #         model="deepseek-ai/DeepSeek-R1-Distill-Llama-8B",
            #     ),
            #     cost_per_1m_tokens_in=0.0,  # Will be calculated dynamically
            #     cost_per_1m_tokens_out=0.0,  # Will be calculated dynamically
            #     cost_infra_per_hour=2.98,
            # ),
            ModelConfig(
                name="santa-deepseek-r1-llama-8b",
                client=LLMClient(
                    base_url=os.getenv("SANTA_DEEPSEEK_R1_L8B_URL"),
                    api_key=os.getenv("SANTA_DEEPSEEK_R1_L8B_API_KEY"),
                    model="deepseek-ai/DeepSeek-R1-Distill-Llama-8B",
                ),
                cost_per_1m_tokens_in=0.0,  # Will be calculated dynamically
                cost_per_1m_tokens_out=0.0,  # Will be calculated dynamically
                cost_infra_per_hour=2.96,
            ),
            ModelConfig(
                name="santa-deepseek-r1-qwen-1d5b",
                client=LLMClient(
                    base_url=os.getenv("SANTA_DEEPSEEK_R1_Q1d5B_URL"),
                    api_key=os.getenv("SANTA_DEEPSEEK_R1_Q1d5B_API_KEY"),
                    model="deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B",
                ),
                cost_per_1m_tokens_in=0.0,  # Will be calculated dynamically
                cost_per_1m_tokens_out=0.0,  # Will be calculated dynamically
                cost_infra_per_hour=2.96,
            ),
        ]
        models.extend(self_hosted_models)

    # Filter by model names if specified
    if model_names:
        models = [m for m in models if m.name in model_names]

    return models


def get_judge_client(model_name: str | None = None) -> LLMClient | None:
    """
    Get judge client for quality evaluation.

    Args:
        model_name: Optional specific model name. If None, uses default priority:
            1. gpt-5.2 (if OPENAI_API_KEY available)
            2. gpt-3.5-turbo (if OPENAI_API_KEY available)
            3. Token Factory model (if TOKEN_FACTORY_API_KEY available)

    Returns:
        LLMClient instance or None if no judge model available
    """

    # Default priority order
    if os.getenv("OPENAI_API_KEY"):
        # Try gpt-5.2 first, fallback to gpt-3.5-turbo
        try:
            client = LLMClient(
                base_url="https://api.openai.com/v1",
                api_key=os.getenv("OPENAI_API_KEY"),
                model="gpt-5.2",
            )
            # Test if model is available
            client.generate("test", temperature=0.0, max_tokens=1)
            return client
        except Exception:
            # Fallback to gpt-3.5-turbo
            return LLMClient(
                base_url="https://api.openai.com/v1",
                api_key=os.getenv("OPENAI_API_KEY"),
                model="gpt-3.5-turbo",
            )

    if os.getenv("TOKEN_FACTORY_API_KEY") and os.getenv("TOKEN_FACTORY_BASE_URL"):
        return LLMClient(
            base_url=os.getenv("TOKEN_FACTORY_BASE_URL"),
            api_key=os.getenv("TOKEN_FACTORY_API_KEY"),
            model="meta-llama/Meta-Llama-3-8B-Instruct",
        )

    return None
