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
    ) -> None:
        self.name = name
        self.client = client
        self.cost_per_1m_tokens_in = cost_per_1m_tokens_in
        self.cost_per_1m_tokens_out = cost_per_1m_tokens_out

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format for backward compatibility."""
        return {
            "name": self.name,
            "client": self.client,
            "cost_per_1m_tokens_in": self.cost_per_1m_tokens_in,
            "cost_per_1m_tokens_out": self.cost_per_1m_tokens_out,
        }


def get_available_models(
    model_names: list[str] | None = None,
    include_openai: bool = True,
    include_token_factory: bool = True,
    include_vllm: bool = True,
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
        openai_models = [
            ModelConfig(
                name="gpt-4o-mini",
                client=LLMClient(
                    base_url="https://api.openai.com/v1",
                    api_key=os.getenv("OPENAI_API_KEY"),
                    model="gpt-4o-mini",
                ),
                cost_per_1m_tokens_in=0.15,
                cost_per_1m_tokens_out=0.6,
            ),
            ModelConfig(
                name="openai-gpt-3.5-turbo",
                client=LLMClient(
                    base_url="https://api.openai.com/v1",
                    api_key=os.getenv("OPENAI_API_KEY"),
                    model="gpt-3.5-turbo",
                ),
                cost_per_1m_tokens_in=1.5,
                cost_per_1m_tokens_out=2.0,
            ),
            ModelConfig(
                name="openai-gpt-4-turbo",
                client=LLMClient(
                    base_url="https://api.openai.com/v1",
                    api_key=os.getenv("OPENAI_API_KEY"),
                    model="gpt-4-turbo-preview",
                ),
                cost_per_1m_tokens_in=10.0,
                cost_per_1m_tokens_out=30.0,
            ),
        ]
        models.extend(openai_models)

    # Token Factory models
    if (
        include_token_factory
        and os.getenv("TOKEN_FACTORY_API_KEY")
        and os.getenv("TOKEN_FACTORY_BASE_URL")
    ):
        tf_base_url = os.getenv("TOKEN_FACTORY_BASE_URL")
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
            ModelConfig(
                name="tokenfactory-llama-3-8b",
                client=LLMClient(
                    base_url=tf_base_url,
                    api_key=tf_api_key,
                    model="meta-llama/Meta-Llama-3-8B-Instruct",
                ),
                cost_per_1m_tokens_in=0.1,
                cost_per_1m_tokens_out=0.1,
            ),
        ]
        models.extend(tf_models)

    # vLLM models
    if include_vllm:
        vllm_base_url = os.getenv("VLLM_BASE_URL")
        if vllm_base_url:
            vllm_models = [
                ModelConfig(
                    name="vllm-llama-2-7b",
                    client=LLMClient(
                        base_url=vllm_base_url,
                        api_key=None,
                        model=os.getenv("VLLM_MODEL_7B", "meta-llama/Llama-2-7b-chat-hf"),
                    ),
                    cost_per_1m_tokens_in=0.0,
                    cost_per_1m_tokens_out=0.0,
                ),
                ModelConfig(
                    name="vllm-llama-2-13b",
                    client=LLMClient(
                        base_url=vllm_base_url,
                        api_key=None,
                        model=os.getenv("VLLM_MODEL_13B", "meta-llama/Llama-2-13b-chat-hf"),
                    ),
                    cost_per_1m_tokens_in=0.0,
                    cost_per_1m_tokens_out=0.0,
                ),
            ]
            models.extend(vllm_models)

    # Filter by model names if specified
    if model_names:
        models = [m for m in models if m.name in model_names]

    return models


def get_models_for_evaluation(
    model_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Get models in dictionary format for evaluation notebooks (backward compatibility).

    Args:
        model_names: Optional list of specific model names to include

    Returns:
        List of model dictionaries compatible with existing evaluation code
    """
    models = get_available_models(model_names=model_names)
    return [m.to_dict() for m in models]


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
    if model_name:
        # Find specific model
        models = get_available_models()
        for model in models:
            if model.name == model_name:
                return model.client
        # If not found in available models, try to create it directly
        if model_name == "gpt-5.2" and os.getenv("OPENAI_API_KEY"):
            return LLMClient(
                base_url="https://api.openai.com/v1",
                api_key=os.getenv("OPENAI_API_KEY"),
                model="gpt-5.2",
            )
        return None

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
