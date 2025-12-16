"""LLM benchmarking module for testing different providers and self-hosted models.

This module provides comprehensive benchmarking capabilities including:
- Sequential request testing for latency metrics
- Concurrent/batched request testing for throughput metrics
- Cost calculation using both latency-based (upper bound) and throughput-based (realistic) approaches
"""

import concurrent.futures
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from src.data_scheme import KidProfile
from src.generators import generate_gift_recommendation
from src.model_config import ModelConfig, calculate_self_hosted_cost, get_available_models
from src.test_samples import get_test_profiles

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class BenchmarkResult:
    """Results from benchmarking a single model."""

    model_name: str
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    throughput_tokens_per_sec: float
    cost_per_1m_in: (
        float | None
    )  # For API models: from ModelConfig. For self-hosted: latency-based calculated
    cost_per_1m_out: (
        float | None
    )  # For API models: from ModelConfig. For self-hosted: latency-based calculated
    cost_per_1m_in_throughput_based: (
        float | None
    )  # Throughput-based cost per 1M input tokens (self-hosted only)
    cost_per_1m_out_throughput_based: (
        float | None
    )  # Throughput-based cost per 1M output tokens (self-hosted only)
    cost_1m_requests: float | None  # Cost for 1M similar requests based on average token counts
    cost_1m_requests_throughput_based: (
        float | None
    )  # Cost for 1M similar requests based on throughput-based cost
    tokens_in_avg: float
    tokens_out_avg: float
    success_rate: float
    total_requests: int
    successful_requests: int


@dataclass
class RequestMetrics:
    """Metrics for a single request."""

    latency_ms: float
    tokens_in: int
    tokens_out: int
    success: bool
    error: str | None = None


def calculate_latency_percentiles(latencies: list[float]) -> tuple[float, float, float]:
    """
    Calculate p50, p95, and p99 latency percentiles.

    Args:
        latencies: List of latency values in milliseconds

    Returns:
        Tuple of (p50, p95, p99) in milliseconds
    """
    if not latencies:
        return 0.0, 0.0, 0.0

    sorted_latencies = sorted(latencies)
    n = len(sorted_latencies)

    p50_idx = int(n * 0.50)
    p95_idx = int(n * 0.95)
    p99_idx = int(n * 0.99)

    p50 = sorted_latencies[p50_idx] if p50_idx < n else sorted_latencies[-1]
    p95 = sorted_latencies[p95_idx] if p95_idx < n else sorted_latencies[-1]
    p99 = sorted_latencies[p99_idx] if p99_idx < n else sorted_latencies[-1]

    return p50, p95, p99


def calculate_throughput(total_tokens: int, total_time_seconds: float) -> float:
    """
    Calculate throughput in tokens per second.

    Args:
        total_tokens: Total tokens processed (input + output)
        total_time_seconds: Total time taken in seconds

    Returns:
        Throughput in tokens per second
    """
    if total_time_seconds <= 0:
        return 0.0
    return total_tokens / total_time_seconds


def calculate_self_costed_costs(
    latency_ms: float,
    tokens_in: int,
    tokens_out: int,
    cost_infra_per_hour: float,
) -> tuple[float, float]:
    """
    Calculate cost per 1M tokens using latency-based approach (upper bound).

    This assumes 1 request at a time, no batching, and represents worst-case cost.

    Args:
        latency_ms: Request latency in milliseconds
        tokens_in: Number of input tokens
        tokens_out: Number of output tokens
        cost_infra_per_hour: Infrastructure cost per hour in USD

    Returns:
        Tuple of (cost_per_1m_tokens_in, cost_per_1m_tokens_out) in USD
    """
    return calculate_self_hosted_cost(
        latency_ms=latency_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_infra_per_hour=cost_infra_per_hour,
    )


def calculate_throughput_based_costs(
    throughput_tokens_per_sec: float,
    cost_infra_per_hour: float,
) -> float:
    """
    Calculate cost per 1M tokens using throughput-based approach (realistic production cost).

    This assumes optimal GPU utilization with batching and represents realistic cost at scale.

    Args:
        throughput_tokens_per_sec: Measured throughput in tokens per second
        cost_infra_per_hour: Infrastructure cost per hour in USD

    Returns:
        Cost per 1M tokens in USD (combined input + output)
    """
    if throughput_tokens_per_sec <= 0:
        return 0.0

    # Calculate time needed to process 1M tokens
    GPU_UTIL_AVG = 0.7  # TODO: get from GPU stats
    effective_tokens_per_sec = throughput_tokens_per_sec * GPU_UTIL_AVG
    time_for_1m_tokens_seconds = 1_000_000 / effective_tokens_per_sec

    # Convert to hours
    time_for_1m_tokens_hours = time_for_1m_tokens_seconds / 3600

    # Calculate cost
    cost_per_1m_tokens = time_for_1m_tokens_hours * cost_infra_per_hour

    return cost_per_1m_tokens


def calculate_cost_1m_requests(
    cost_per_1m_in: float,
    cost_per_1m_out: float,
    tokens_in: int,
    tokens_out: int,
) -> float:
    """
    Calculate cost for 1M similar requests based on token counts and cost per 1M tokens.

    Formula: (tokens_in * cost_per_token_in + tokens_out * cost_per_token_out) * 1_000_000
    where cost_per_token = cost_per_1m_tokens / 1_000_000

    Args:
        cost_per_1m_in: Cost per 1M input tokens in USD
        cost_per_1m_out: Cost per 1M output tokens in USD
        tokens_in: Number of input tokens in the request
        tokens_out: Number of output tokens in the request

    Returns:
        Cost for 1M similar requests in USD
    """
    cost_per_token_in = cost_per_1m_in / 1_000_000
    cost_per_token_out = cost_per_1m_out / 1_000_000
    cost_1m_requests = (tokens_in * cost_per_token_in + tokens_out * cost_per_token_out) * 1_000_000
    return cost_1m_requests


def run_sequential_benchmark(
    model_config: ModelConfig,
    test_profiles: list[KidProfile],
) -> list[RequestMetrics]:
    """
    Run sequential benchmark to collect latency samples and token counts.

    Args:
        model_config: Model configuration to benchmark
        test_profiles: List of test kid profiles to use

    Returns:
        List of RequestMetrics for each request
    """
    metrics_list: list[RequestMetrics] = []

    for profile in test_profiles:
        try:
            _, metrics = generate_gift_recommendation(
                llm_client=model_config.client,
                kid_profile=profile,
            )

            tokens_in = metrics.get("tokens_in") or 0
            tokens_out = metrics.get("tokens_out") or 0
            latency_ms = metrics.get("latency_ms", 0.0)

            metrics_list.append(
                RequestMetrics(
                    latency_ms=latency_ms,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    success=True,
                )
            )
        except Exception as e:
            metrics_list.append(
                RequestMetrics(
                    latency_ms=0.0,
                    tokens_in=0,
                    tokens_out=0,
                    success=False,
                    error=str(e),
                )
            )

    return metrics_list


def run_concurrent_benchmark(
    model_config: ModelConfig,
    test_profiles: list[KidProfile],
    concurrency: int = 10,
) -> tuple[list[RequestMetrics], float]:
    """
    Run concurrent benchmark to measure throughput.

    Args:
        model_config: Model configuration to benchmark
        test_profiles: List of test kid profiles to use
        concurrency: Number of concurrent requests (default: 10)

    Returns:
        Tuple of (list of RequestMetrics, total_time_seconds)
    """
    metrics_list: list[RequestMetrics] = []

    def run_request(profile: KidProfile) -> RequestMetrics:
        """Run a single request and return metrics."""
        try:
            _, metrics = generate_gift_recommendation(
                llm_client=model_config.client,
                kid_profile=profile,
            )

            tokens_in = metrics.get("tokens_in") or 0
            tokens_out = metrics.get("tokens_out") or 0
            latency_ms = metrics.get("latency_ms", 0.0)

            return RequestMetrics(
                latency_ms=latency_ms,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                success=True,
            )
        except Exception as e:
            return RequestMetrics(
                latency_ms=0.0,
                tokens_in=0,
                tokens_out=0,
                success=False,
                error=str(e),
            )

    # Repeat profiles to get enough requests for concurrent testing
    # Use at least concurrency number of profiles
    repeated_profiles = (test_profiles * ((concurrency // len(test_profiles)) + 1))[:concurrency]

    # Warmup requests (not timed) to stabilize caches/compilation
    warmup_requests = min(len(repeated_profiles), 3)
    for profile in repeated_profiles[:warmup_requests]:
        _ = run_request(profile)

    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(run_request, profile) for profile in repeated_profiles]
        metrics_list = [future.result() for future in concurrent.futures.as_completed(futures)]

    total_time = time.time() - start_time

    return metrics_list, total_time


def benchmark_model(
    model_config: ModelConfig,
    test_profiles: list[KidProfile],
    concurrency: int = 10,
) -> BenchmarkResult:
    """
    Benchmark a single model with both sequential and concurrent tests.

    Args:
        model_config: Model configuration to benchmark
        test_profiles: List of test kid profiles to use
        concurrency: Number of concurrent requests for throughput test (default: 10)

    Returns:
        BenchmarkResult with all metrics
    """
    # Run sequential benchmark for latency metrics
    sequential_metrics = run_sequential_benchmark(model_config, test_profiles)

    # Run concurrent benchmark for throughput metrics
    concurrent_metrics, total_time = run_concurrent_benchmark(
        model_config, test_profiles, concurrency
    )

    # Calculate latency percentiles from sequential metrics
    successful_latencies = [m.latency_ms for m in sequential_metrics if m.success]
    latency_p50, latency_p95, latency_p99 = calculate_latency_percentiles(successful_latencies)

    # Calculate throughput from concurrent metrics
    total_tokens = sum(m.tokens_in + m.tokens_out for m in concurrent_metrics if m.success)
    throughput = calculate_throughput(total_tokens, total_time)

    # Calculate average tokens
    successful_metrics = [m for m in sequential_metrics if m.success]
    if successful_metrics:
        tokens_in_avg = statistics.mean([m.tokens_in for m in successful_metrics])
        tokens_out_avg = statistics.mean([m.tokens_out for m in successful_metrics])
    else:
        tokens_in_avg = 0.0
        tokens_out_avg = 0.0

    # Calculate success rate
    total_requests = len(sequential_metrics)
    successful_requests = sum(1 for m in sequential_metrics if m.success)
    success_rate = successful_requests / total_requests if total_requests > 0 else 0.0

    # Calculate costs for benchmark payload
    cost_per_1m_in: float | None = None
    cost_per_1m_out: float | None = None
    cost_per_1m_in_throughput_based: float | None = None
    cost_per_1m_out_throughput_based: float | None = None
    cost_1m_requests: float | None = None
    cost_1m_requests_throughput_based: float | None = None

    if model_config.is_self_hosted and model_config.cost_infra_per_hour:
        # Self-hosted models: calculate based on infrastructure cost
        # Latency-based cost: Use average latency and tokens (write to cost_per_1m_in/out)
        if successful_metrics:
            avg_latency = statistics.mean([m.latency_ms for m in successful_metrics])
            avg_tokens_in = int(tokens_in_avg)
            avg_tokens_out = int(tokens_out_avg)

            cost_per_1m_in_latency, cost_per_1m_out_latency = calculate_self_costed_costs(
                latency_ms=avg_latency,
                tokens_in=avg_tokens_in,
                tokens_out=avg_tokens_out,
                cost_infra_per_hour=model_config.cost_infra_per_hour,
            )
            # Write latency-based costs to cost_per_1m_in/out (rounded)
            cost_per_1m_in = round(cost_per_1m_in_latency, 2)
            cost_per_1m_out = round(cost_per_1m_out_latency, 2)

        # Throughput-based cost: Use measured throughput
        if throughput > 0:
            throughput_cost = calculate_throughput_based_costs(
                throughput_tokens_per_sec=throughput,
                cost_infra_per_hour=model_config.cost_infra_per_hour,
            )
            # For throughput-based, we use the same cost for both input and output
            cost_per_1m_in_throughput_based = round(throughput_cost, 2)
            cost_per_1m_out_throughput_based = round(throughput_cost, 2)
    else:
        # API-based models: use per-token pricing from ModelConfig
        cost_per_1m_in = round(model_config.cost_per_1m_tokens_in, 2)
        cost_per_1m_out = round(model_config.cost_per_1m_tokens_out, 2)
        # For API models, throughput-based is the same as latency-based
        cost_per_1m_in_throughput_based = None
        cost_per_1m_out_throughput_based = None

    # Calculate cost_1m_requests using average token counts
    if (
        cost_per_1m_in is not None
        and cost_per_1m_out is not None
        and tokens_in_avg > 0
        and tokens_out_avg > 0
    ):
        cost_1m_requests = calculate_cost_1m_requests(
            cost_per_1m_in=cost_per_1m_in,
            cost_per_1m_out=cost_per_1m_out,
            tokens_in=int(tokens_in_avg),
            tokens_out=int(tokens_out_avg),
        )
        cost_1m_requests = round(cost_1m_requests, 0)

    # Calculate cost_1m_requests_throughput_based using throughput-based costs
    cost_1m_requests_throughput_based: float | None = None
    if (
        cost_per_1m_in_throughput_based is not None
        and cost_per_1m_out_throughput_based is not None
        and tokens_in_avg > 0
        and tokens_out_avg > 0
    ):
        cost_1m_requests_throughput_based = calculate_cost_1m_requests(
            cost_per_1m_in=cost_per_1m_in_throughput_based,
            cost_per_1m_out=cost_per_1m_out_throughput_based,
            tokens_in=int(tokens_in_avg),
            tokens_out=int(tokens_out_avg),
        )
        cost_1m_requests_throughput_based = round(cost_1m_requests_throughput_based, 2)

    return BenchmarkResult(
        model_name=model_config.name,
        latency_p50_ms=round(latency_p50, 0),
        latency_p95_ms=round(latency_p95, 0),
        latency_p99_ms=round(latency_p99, 0),
        throughput_tokens_per_sec=round(throughput, 0),
        cost_per_1m_in=cost_per_1m_in,
        cost_per_1m_out=cost_per_1m_out,
        cost_per_1m_in_throughput_based=cost_per_1m_in_throughput_based,
        cost_per_1m_out_throughput_based=cost_per_1m_out_throughput_based,
        cost_1m_requests=cost_1m_requests,
        cost_1m_requests_throughput_based=cost_1m_requests_throughput_based,
        tokens_in_avg=tokens_in_avg,
        tokens_out_avg=tokens_out_avg,
        success_rate=success_rate,
        total_requests=total_requests,
        successful_requests=successful_requests,
    )


def results_to_dataframe(
    results: list[BenchmarkResult], concurrency: int | None = None
) -> "pd.DataFrame":
    """
    Convert list of BenchmarkResult objects to pandas DataFrame.

    Args:
        results: List of BenchmarkResult objects
        concurrency: Optional concurrency level to add as a column

    Returns:
        pandas DataFrame with all benchmark metrics
    """
    try:
        import pandas as pd
    except ImportError as err:
        raise ImportError(
            "pandas is required for DataFrame conversion. Install with: pip install pandas"
        ) from err

    data = []
    for result in results:
        row = {
            "model_name": result.model_name,
            "latency_p50_ms": result.latency_p50_ms,
            "latency_p95_ms": result.latency_p95_ms,
            "latency_p99_ms": result.latency_p99_ms,
            "throughput_tokens_per_sec": result.throughput_tokens_per_sec,
            "tokens_in_avg": result.tokens_in_avg,
            "tokens_out_avg": result.tokens_out_avg,
            "success_rate": result.success_rate,
            "total_requests": result.total_requests,
            "successful_requests": result.successful_requests,
            "cost_per_1m_in": result.cost_per_1m_in,
            "cost_per_1m_out": result.cost_per_1m_out,
            "cost_per_1m_in_throughput_based": result.cost_per_1m_in_throughput_based,
            "cost_per_1m_out_throughput_based": result.cost_per_1m_out_throughput_based,
            "cost_1m_requests": result.cost_1m_requests,
            "cost_1m_requests_throughput_based": result.cost_1m_requests_throughput_based,
        }
        if concurrency is not None:
            row["concurrency"] = concurrency
        data.append(row)

    return pd.DataFrame(data)


def run_benchmark_suite(
    model_configs: list[ModelConfig],
    test_profiles: list[KidProfile],
    concurrency: int = 10,
    output_csv_path: Path | None = None,
) -> list[BenchmarkResult]:
    """
    Run benchmark suite on multiple models.

    Args:
        model_configs: List of model configurations to benchmark
        test_profiles: List of test kid profiles to use
        concurrency: Number of concurrent requests for throughput test (default: 10)
        output_csv_path: Optional path to save CSV results

    Returns:
        List of BenchmarkResult objects
    """
    results: list[BenchmarkResult] = []

    print(f"Starting benchmark suite with {len(model_configs)} models...")
    print(f"Using {len(test_profiles)} test profiles")
    print(f"Concurrency level: {concurrency}\n")

    for i, model_config in enumerate(model_configs, 1):
        print(f"[{i}/{len(model_configs)}] Benchmarking {model_config.name}...")
        try:
            result = benchmark_model(model_config, test_profiles, concurrency)
            results.append(result)
            print(f"  ✓ Completed: {result.successful_requests}/{result.total_requests} successful")
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            # Create a failed result
            results.append(
                BenchmarkResult(
                    model_name=model_config.name,
                    latency_p50_ms=0.0,
                    latency_p95_ms=0.0,
                    latency_p99_ms=0.0,
                    throughput_tokens_per_sec=0.0,
                    cost_per_1m_in=None,
                    cost_per_1m_out=None,
                    cost_per_1m_in_throughput_based=None,
                    cost_per_1m_out_throughput_based=None,
                    cost_1m_requests=None,
                    cost_1m_requests_throughput_based=None,
                    tokens_in_avg=0.0,
                    tokens_out_avg=0.0,
                    success_rate=0.0,
                    total_requests=0,
                    successful_requests=0,
                )
            )

    # Print console report
    # print_console_report(results)
    df = results_to_dataframe(results)
    print(df)

    # Export to CSV if path provided
    if output_csv_path:
        df.to_csv(output_csv_path, index=False)
        print(f"Results exported to: {output_csv_path}")

    return results


def main() -> int:
    """
    Main entry point for running benchmark suite from command line.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Benchmark LLM models for technical metrics and cost estimation"
    )
    parser.add_argument(
        "--models",
        type=str,
        nargs="+",
        help="Specific model names to benchmark (default: all available)",
    )
    parser.add_argument(
        "--include-openai",
        action="store_true",
        help="Include OpenAI models",
    )
    parser.add_argument(
        "--include-token-factory",
        action="store_true",
        help="Include Token Factory models",
    )
    parser.add_argument(
        "--include-self-hosted",
        action="store_true",
        help="Include self-hosted models",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent requests for throughput test (default: 10)",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        help="Path to output CSV file (default: benchmark_results.csv)",
    )

    args = parser.parse_args()

    # Get test profiles
    test_profiles = get_test_profiles()
    print(f"Using {len(test_profiles)} test profiles for benchmarking")

    # Get available models
    model_configs = get_available_models(
        model_names=args.models if args.models else None,
        include_openai=args.include_openai,
        include_token_factory=args.include_token_factory,
        include_self_hosted=args.include_self_hosted,
    )

    if not model_configs:
        print(
            "No models available. Set environment variables or use --include-* flags to enable models."
        )
        return 1

    # Determine output path
    output_csv_path = None
    if args.output_csv:
        output_csv_path = Path(args.output_csv)
    else:
        output_csv_path = Path("data/benchmark_results.csv")

    # Run benchmark suite
    try:
        results = run_benchmark_suite(
            model_configs=model_configs,
            test_profiles=test_profiles,
            concurrency=args.concurrency,
            output_csv_path=output_csv_path,
        )

        print("\n✓ Benchmark completed successfully!")
        print(f"  - Tested {len(results)} models")
        print(f"  - Results saved to: {output_csv_path}")
        return 0

    except Exception as e:
        print(f"\n✗ Benchmark failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
