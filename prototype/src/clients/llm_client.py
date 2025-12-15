"""LLM client for OpenAI-compatible and self-hosted vLLM services."""

import os
import time
from datetime import datetime
from typing import Any

import requests


class LLMClient:
    """Client for OpenAI-compatible LLM services including self-hosted vLLM."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model: str = "gpt-3.5-turbo",
    ) -> None:
        """
        Initialize LLM client.

        Args:
            base_url: Base URL for the LLM service
            api_key: API key (required for OpenAI, optional for local vLLM)
            model: Model name to use
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.model_version = f"{model}-{datetime.now().strftime('%Y%m%d')}"

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 500,
    ) -> tuple[str, dict[str, Any]]:
        """
        Generate text using the LLM service.

        Args:
            prompt: Input prompt
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate

        Returns:
            Tuple of (generated_text, metrics_dict) where metrics includes:
            - latency_ms: Time taken in milliseconds
            - tokens_in: Input tokens (if available)
            - tokens_out: Output tokens (if available)
            - model: Model name used

        Raises:
            ValueError: If the API call fails
        """
        headers = {"Content-Type": "application/json"}

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        is_openai_compatible = "openai.com" in self.base_url or self.base_url.endswith("/v1")

        if is_openai_compatible:
            # Check if model requires max_completion_tokens (newer models)
            requires_max_completion = any(
                pattern in self.model.lower() for pattern in ["gpt-5", "o3", "o1"]
            )

            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
            }
            if requires_max_completion:
                payload["max_completion_tokens"] = max_tokens
            else:
                payload["max_tokens"] = max_tokens

            endpoint = f"{self.base_url}/chat/completions"
        else:
            payload = {
                "prompt": prompt,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            endpoint = f"{self.base_url}/generate"

        start_time = time.time()

        try:
            response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            data = response.json()

            latency_ms = (time.time() - start_time) * 1000

            metrics: dict[str, Any] = {
                "latency_ms": latency_ms,
                "model": self.model,
                "tokens_in": None,
                "tokens_out": None,
            }

            # Handle OpenAI-compatible chat completions format
            if "openai.com" in self.base_url or "choices" in data:
                choice = data.get("choices", [{}])[0]
                content = None

                # Handle chat-style responses with message.content
                if isinstance(choice, dict) and "message" in choice:
                    message = choice["message"]
                    raw = message.get("content")
                    if isinstance(raw, str):
                        content = raw
                    elif isinstance(raw, list):
                        # TokenFactory may return list of content parts
                        parts = []
                        for item in raw:
                            if isinstance(item, dict):
                                if item.get("type") == "text" and "text" in item:
                                    parts.append(str(item["text"]))
                                elif "text" in item:
                                    parts.append(str(item["text"]))
                            elif isinstance(item, str):
                                parts.append(item)
                        content = "".join(parts).strip() if parts else None

                    # TokenFactory fallback: some models use reasoning_content when content is None
                    if content is None and "reasoning_content" in message:
                        reasoning = message.get("reasoning_content")
                        if isinstance(reasoning, str):
                            content = reasoning

                # Fallback to direct text field in choice
                if content is None and isinstance(choice, dict) and "text" in choice:
                    content = choice.get("text")

                if not content or not isinstance(content, str):
                    raise ValueError(f"Unexpected response format: {data}")

                text = content.strip()
                if "usage" in data:
                    metrics["tokens_in"] = data["usage"].get("prompt_tokens")
                    metrics["tokens_out"] = data["usage"].get("completion_tokens")
            elif "text" in data:
                text = data["text"].strip()
                if "usage" in data:
                    metrics["tokens_in"] = data["usage"].get("prompt_tokens")
                    metrics["tokens_out"] = data["usage"].get("completion_tokens")
            else:
                raise ValueError(f"Unexpected response format: {data}")

            return text, metrics

        except requests.exceptions.HTTPError as e:
            # Surface API error details to help debugging (model availability, auth, quota)
            err_detail = ""
            try:
                err_json = response.json()
                err_detail = f" | api_error={err_json}"
            except Exception:
                err_detail = f" | body={response.text}"
            raise ValueError(
                f"LLM API call failed: {e} | status={response.status_code}{err_detail}"
            ) from e
        except requests.exceptions.RequestException as e:
            raise ValueError(f"LLM API call failed: {str(e)}") from e


def create_llm_client_from_env(
    base_url_env: str,
    api_key_env: str | None = None,
    model: str = "gpt-3.5-turbo",
) -> LLMClient:
    """
    Create LLM client from environment variables.

    Args:
        base_url_env: Environment variable name for base URL
        api_key_env: Environment variable name for API key (optional)
        model: Model name to use

    Returns:
        Initialized LLMClient

    Raises:
        ValueError: If required environment variables are not set
    """
    base_url = os.getenv(base_url_env)
    if not base_url:
        raise ValueError(f"Environment variable {base_url_env} is not set")

    api_key = None
    if api_key_env:
        api_key = os.getenv(api_key_env)

    return LLMClient(base_url=base_url, api_key=api_key, model=model)
