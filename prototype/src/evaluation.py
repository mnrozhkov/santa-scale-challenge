"""Evaluation utilities for MLflow tracking and metrics calculation."""

import os
from datetime import datetime
from typing import Any

try:
    import mlflow

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False


def setup_mlflow(
    experiment_name: str,
    tracking_uri: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> None:
    """
    Set up MLflow tracking.

    Args:
        experiment_name: Name of the MLflow experiment
        tracking_uri: MLflow tracking URI (defaults to MLFLOW_TRACKING_URI env var)
        username: MLflow username (defaults to MLFLOW_TRACKING_USERNAME env var)
        password: MLflow password (defaults to MLFLOW_TRACKING_PASSWORD env var)

    Raises:
        ImportError: If mlflow is not installed
        ValueError: If tracking URI is not configured
    """
    if not MLFLOW_AVAILABLE:
        raise ImportError("MLflow is not installed. Install with: pip install mlflow")

    tracking_uri = tracking_uri or os.getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        raise ValueError(
            "MLflow tracking URI not configured. Set MLFLOW_TRACKING_URI env var or pass tracking_uri"
        )

    if username or password:
        username = username or os.getenv("MLFLOW_TRACKING_USERNAME")
        password = password or os.getenv("MLFLOW_TRACKING_PASSWORD")
        if username and password:
            parsed_uri = tracking_uri.replace("https://", f"https://{username}:{password}@")
            mlflow.set_tracking_uri(parsed_uri)
        else:
            mlflow.set_tracking_uri(tracking_uri)
    else:
        mlflow.set_tracking_uri(tracking_uri)

    mlflow.set_experiment(experiment_name)
    print("MLflow tracking URI:", mlflow.get_tracking_uri())
    print("MLflow experiment:", mlflow.get_experiment_by_name(experiment_name))


def log_llm_evaluation(
    model_name: str,
    prompt: str,
    response: str,
    metrics: dict[str, Any],
    quality_score: float | None = None,
    tags: dict[str, str] | None = None,
) -> str:
    """
    Log LLM evaluation run to MLflow.

    Args:
        model_name: Name of the model being evaluated
        prompt: Input prompt used
        response: Generated response
        metrics: Dictionary with metrics (latency_ms, tokens_in, tokens_out, etc.)
        quality_score: Optional quality score (0-1)
        tags: Optional tags for the run

    Returns:
        Run ID of the logged run
    """
    if not MLFLOW_AVAILABLE:
        return "mlflow_not_available"

    with mlflow.start_run(run_name=f"{model_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"):
        mlflow.log_param("model", model_name)
        mlflow.log_param("prompt_length", len(prompt))

        mlflow.log_metric("latency_ms", metrics.get("latency_ms", 0))
        if metrics.get("tokens_in"):
            mlflow.log_metric("tokens_in", metrics["tokens_in"])
        if metrics.get("tokens_out"):
            mlflow.log_metric("tokens_out", metrics["tokens_out"])

        if quality_score is not None:
            mlflow.log_metric("quality_score", quality_score)

        mlflow.log_text(prompt, "prompt.txt")
        mlflow.log_text(response, "response.txt")

        if tags:
            mlflow.set_tags(tags)

        return mlflow.active_run().info.run_id


def log_image_evaluation(
    model_name: str,
    service: str,
    prompt: str,
    image_url: str,
    metrics: dict[str, Any],
    quality_score: float | None = None,
    tags: dict[str, str] | None = None,
) -> str:
    """
    Log image generation evaluation run to MLflow.

    Args:
        model_name: Name of the model being evaluated
        service: Service name (recraft, tokenfactory, etc.)
        prompt: Image generation prompt
        image_url: URL or path to generated image
        metrics: Dictionary with metrics (latency_ms, output_size_bytes, etc.)
        quality_score: Optional quality score (0-1)
        tags: Optional tags for the run

    Returns:
        Run ID of the logged run
    """
    if not MLFLOW_AVAILABLE:
        return "mlflow_not_available"

    with mlflow.start_run(
        run_name=f"{service}-{model_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    ):
        mlflow.log_param("model", model_name)
        mlflow.log_param("service", service)
        mlflow.log_param("prompt_length", len(prompt))

        mlflow.log_metric("latency_ms", metrics.get("latency_ms", 0))
        if metrics.get("output_size_bytes"):
            mlflow.log_metric("output_size_bytes", metrics["output_size_bytes"])

        if quality_score is not None:
            mlflow.log_metric("quality_score", quality_score)

        mlflow.log_text(prompt, "prompt.txt")

        if image_url.startswith("http"):
            mlflow.log_param("image_url", image_url)
        else:
            mlflow.log_artifact(image_url)

        if tags:
            mlflow.set_tags(tags)

        return mlflow.active_run().info.run_id


def calculate_monthly_cost_estimate(
    tokens_in_per_request: float,
    tokens_out_per_request: float,
    cost_per_1m_tokens_in: float,
    cost_per_1m_tokens_out: float,
    requests_per_month: int = 2_000_000_000,
) -> float:
    """
    Calculate monthly cost estimate for LLM usage.

    Args:
        tokens_in_per_request: Average input tokens per request
        tokens_out_per_request: Average output tokens per request
        cost_per_1m_tokens_in: Cost per 1 million input tokens
        cost_per_1m_tokens_out: Cost per 1 million output tokens
        requests_per_month: Number of requests per month (default: 2B)

    Returns:
        Estimated monthly cost in USD
    """
    total_tokens_in = tokens_in_per_request * requests_per_month
    total_tokens_out = tokens_out_per_request * requests_per_month

    cost_in = (total_tokens_in / 1_000_000) * cost_per_1m_tokens_in
    cost_out = (total_tokens_out / 1_000_000) * cost_per_1m_tokens_out

    return cost_in + cost_out


def calculate_image_monthly_cost_estimate(
    cost_per_image: float,
    images_per_month: int = 2_000_000_000,
) -> float:
    """
    Calculate monthly cost estimate for image generation.

    Args:
        cost_per_image: Cost per image
        images_per_month: Number of images per month (default: 2B)

    Returns:
        Estimated monthly cost in USD
    """
    return cost_per_image * images_per_month


def evaluate_quality_with_judge(
    llm_client: Any,
    judge_prompt: str,
) -> tuple[float, str]:
    """
    Use LLM-as-a-judge to evaluate quality with structured JSON output.

    Args:
        llm_client: LLMClient instance
        judge_prompt: Prompt for the judge LLM

    Returns:
        Tuple of (quality_score: float, rationale: str)
        Quality score from 0.0 to 1.0 and explanation
    """
    try:
        # Try structured JSON output first
        response_json, _ = llm_client.generate_json(judge_prompt, temperature=0.0, max_tokens=200)

        score = float(response_json.get("quality_score", 0.5))
        rationale = response_json.get("rationale", "No rationale provided")

        return max(0.0, min(1.0, score)), rationale

    except (ValueError, KeyError, TypeError):
        # Fallback to text parsing for models that don't support JSON mode
        try:
            judge_response, _ = llm_client.generate(judge_prompt, temperature=0.0, max_tokens=200)
            # Try to extract just the number
            score = float(judge_response.strip().split()[0])
            rationale = judge_response.strip()
            return max(0.0, min(1.0, score)), rationale
        except (ValueError, TypeError):
            return 0.5, "Failed to parse judge response"
