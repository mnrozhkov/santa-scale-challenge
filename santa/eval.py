"""Evaluation helpers for research notebooks. Optional mlflow/pandas (research extra).

Notebooks import ``santa.schemas``, ``santa.prompts``, ``santa.card``, ``santa.models``,
and this module. Set ``SANTA_EVAL_FAKE=1`` to run without endpoints.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from santa.card import generate_image, recommend_gift, write_wish
from santa.config import REPO_ROOT, RoleConfig, Settings
from santa.models import ChatAdapter, adapter_for
from santa.prompts import gift_recommendation_prompt, image_prompt, wish_prompt
from santa.schemas import CardImage, GiftRecommendation, KidProfile, Wish

# --- samples -----------------------------------------------------------------


_PROFILES: list[KidProfile] | None = None


def get_test_profiles() -> list[KidProfile]:
    global _PROFILES
    if _PROFILES is None:
        _PROFILES = [
            KidProfile(name="Emma", age=7, wishlist=["doll", "art supplies", "books"]),
            KidProfile(name="Lucas", age=10, wishlist=["LEGO set", "video games", "bicycle"]),
            KidProfile(name="Sophia", age=5, wishlist=["princess dress", "stuffed animals"]),
            KidProfile(name="Noah", age=12, wishlist=["basketball", "headphones", "science kit"]),
        ]
    return _PROFILES


def get_test_recommendations_for_wish() -> list[GiftRecommendation]:
    profiles = get_test_profiles()
    gifts = [
        ["DIY doll making kit", "Watercolor painting set", "Storybook collection"],
        ["Advanced LEGO Technic set", "Educational coding game", "Mountain bike"],
        ["Princess dress-up set", "Soft teddy bear", "Fairy tale book"],
        ["Professional basketball", "Wireless headphones", "Chemistry experiment kit"],
    ]
    notes = [
        "These gifts match Emma's creative interests.",
        "These gifts align with Lucas's interests in building and technology.",
        "These gifts are perfect for Sophia's age and interests.",
        "These gifts match Noah's active and scientific interests.",
    ]
    return [
        GiftRecommendation(kid_id=p.id, gifts=g, rationale=r, model_version="test")
        for p, g, r in zip(profiles, gifts, notes, strict=True)
    ]


def get_test_recommendations_for_image() -> list[GiftRecommendation]:
    profiles = get_test_profiles()
    gifts = [
        ["DIY doll making kit", "Watercolor painting set"],
        ["Advanced LEGO Technic set", "Mountain bike"],
        ["Princess dress-up set", "Soft teddy bear"],
        ["Professional basketball", "Chemistry experiment kit"],
    ]
    notes = [
        "These gifts match Emma's creative interests.",
        "These gifts align with Lucas's interests.",
        "These gifts are perfect for Sophia.",
        "These gifts match Noah's interests.",
    ]
    return [
        GiftRecommendation(kid_id=p.id, gifts=g, rationale=r, model_version="test")
        for p, g, r in zip(profiles, gifts, notes, strict=True)
    ]


# --- env ---------------------------------------------------------------------


def load_env_from_repo_root(env_file: str = ".env", override: bool = False) -> None:
    """Load ``REPO_ROOT/.env``. Missing file is a no-op (workshop notebooks use Settings)."""
    from dotenv import load_dotenv

    path = REPO_ROOT / env_file
    if path.is_file():
        load_dotenv(path, override=override)


# --- fakes -------------------------------------------------------------------


class FakeEvalLLM:
    """Deterministic llm stand-in for ``SANTA_EVAL_FAKE=1`` and tests."""

    model_version = "fake-llm"
    last_metrics: dict[str, Any] = {"latency_ms": 1, "tokens_in": 10, "tokens_out": 20}
    base_url = "https://fake.example/v1"
    model = "fake-llm"

    def generate_json(self, prompt: str, **kw: Any) -> dict[str, Any]:
        if "quality_score" in prompt:
            return {"quality_score": 0.8, "rationale": "fake"}
        if "You are Santa Claus writing" in prompt:
            return {
                "wish": "Dear child, the North Pole is proud of you. Merry Christmas!",
                "mood": "warm",
            }
        return {"gifts": ["wooden train", "storybook"], "rationale": "loves trains"}

    def generate(self, prompt: str, **kw: Any) -> str:
        return "0.8"


class FakeEvalImage:
    model_version = "fake-image"
    last_metrics: dict[str, Any] = {"latency_ms": 2}
    cfg = RoleConfig(name="image", adapter="openai_images", model="fake")

    def generate(self, prompt: str, *, seed: int | None = None) -> bytes:
        import base64

        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        )


def _use_fakes() -> bool:
    return os.environ.get("SANTA_EVAL_FAKE", "").strip() in {"1", "true", "yes"}


# --- models ------------------------------------------------------------------


@dataclass
class EvalModel:
    name: str
    client: Any
    cost_per_1m_tokens_in: float = 0.15
    cost_per_1m_tokens_out: float = 0.6
    cost_infra_per_hour: float | None = None
    is_self_hosted: bool = False


@dataclass
class EvalImageModel:
    name: str
    client: Any
    cost_per_image: float = 0.04

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "service": self.name,
            "client": self.client,
            "cost_per_image": self.cost_per_image,
        }


def get_available_models(
    model_names: list[str] | None = None,
    include_openai: bool = False,
    include_token_factory: bool = False,
    include_self_hosted: bool = False,
) -> list[EvalModel]:
    """Models for eval notebooks: configured llm role, plus OpenAI fallback if requested."""
    if _use_fakes():
        models = [
            EvalModel(name="fake-llm", client=FakeEvalLLM()),
            EvalModel(name="fake-openai", client=FakeEvalLLM()),
            EvalModel(name="fake-self-hosted", client=FakeEvalLLM(), is_self_hosted=True),
        ]
        return _filter_names(models, model_names)
    load_env_from_repo_root()
    settings = Settings.load()
    found: list[EvalModel] = []
    if include_token_factory or not (include_openai or include_self_hosted):
        try:
            cfg = settings.role("llm")
            found.append(EvalModel(name=cfg.model or "llm", client=adapter_for("llm", settings)))
        except Exception:
            pass
    if include_openai:
        fb = settings.fallback("llm")
        if fb is not None:
            found.append(EvalModel(name=fb.model or "gpt-4o-mini", client=ChatAdapter(fb)))
    return _filter_names(found, model_names)


def get_available_image_models(
    model_names: list[str] | None = None,
    include_recraft: bool = True,
    include_tokenfactory: bool = True,
    include_self_hosted: bool = True,
) -> list[EvalImageModel]:
    del include_recraft, include_tokenfactory, include_self_hosted  # Recraft dropped (D2)
    if _use_fakes():
        return _filter_names(
            [
                EvalImageModel(name="fake-image", client=FakeEvalImage()),
                EvalImageModel(name="fake-image-2", client=FakeEvalImage()),
                EvalImageModel(name="fake-image-3", client=FakeEvalImage()),
            ],
            model_names,
        )
    load_env_from_repo_root()
    settings = Settings.load()
    try:
        cfg = settings.role("image")
        models = [EvalImageModel(name=cfg.model or "image", client=adapter_for("image", settings))]
    except Exception:
        models = []
    return _filter_names(models, model_names)


def get_judge_client(model_name: str | None = None) -> Any | None:
    if _use_fakes():
        return FakeEvalLLM()
    load_env_from_repo_root()
    settings = Settings.load()
    try:
        if model_name:
            fb = settings.fallback("llm")
            if fb is not None:
                return ChatAdapter(fb.model_copy(update={"model": model_name}))
        return adapter_for("llm", settings)
    except Exception:
        return None


def _filter_names(models: list[Any], names: list[str] | None) -> list[Any]:
    if not names:
        return models
    wanted = {n.lower() for n in names}
    return [m for m in models if str(getattr(m, "name", "")).lower() in wanted]


# --- generate wrappers (tuple + metrics, as the old notebooks expect) --------


def _metrics(client: Any) -> dict[str, Any]:
    return dict(getattr(client, "last_metrics", None) or {})


def generate_gift_recommendation(
    llm_client: Any,
    kid_profile: KidProfile,
    temperature: float = 0.8,
    max_tokens: int = 300,
) -> tuple[GiftRecommendation, dict[str, Any]]:
    del temperature, max_tokens
    rec = recommend_gift(kid_profile, llm_client)
    return rec, _metrics(llm_client)


def generate_wish(
    llm_client: Any,
    kid_profile: KidProfile,
    gift_recommendation: GiftRecommendation,
    temperature: float = 0.9,
    max_tokens: int = 200,
) -> tuple[Wish, dict[str, Any]]:
    del temperature, max_tokens
    wish = write_wish(kid_profile, gift_recommendation, llm_client)
    return wish, _metrics(llm_client)


def generate_card_image(
    image_client: Any,
    kid_profile: KidProfile,
    gift_recommendation: GiftRecommendation,
) -> tuple[CardImage, dict[str, Any]]:
    png, meta = generate_image(kid_profile, gift_recommendation, image_client)
    with NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp.write(png)
        meta.path = tmp.name
    return meta, _metrics(image_client)


# --- judge prompts (lifted from prototype/src/prompts.py) --------------------


def generate_gift_quality_judge_prompt(kid_profile: KidProfile, response: str) -> str:
    wishlist = ", ".join(kid_profile.wishlist) if kid_profile.wishlist else "None"
    return f"""You are an evaluator. Score the quality of a gift recommendation between 0.0 and 1.0.
Kid: {kid_profile.name}, age {kid_profile.age}, wishlist {wishlist}
Recommendation:
---
{response}
---
Respond with JSON: {{"quality_score": 0.85, "rationale": "..."}}
"""


def generate_wish_quality_judge_prompt(kid_profile: KidProfile, response: str) -> str:
    return f"""You are an evaluator. Score the quality of a holiday wish between 0.0 and 1.0.
Kid: {kid_profile.name}, age {kid_profile.age}
Wish:
---
{response}
---
Respond with JSON: {{"quality_score": 0.0, "rationale": "..."}}
"""


def generate_image_quality_judge_prompt(
    prompt: str, image_url: str, kid_profile: KidProfile
) -> str:
    return f"""Evaluate this children's holiday illustration (0.0–1.0).
Prompt: {prompt}
Image: {image_url}
Kid: {kid_profile.name}, age {kid_profile.age}
Respond with JSON: {{"quality_score": 0.0, "rationale": "..."}}
"""


def evaluate_quality_with_judge(llm_client: Any, judge_prompt: str) -> tuple[float, str]:
    try:
        data = llm_client.generate_json(judge_prompt, temperature=0.0, max_tokens=200)
        if isinstance(data, tuple):
            data = data[0]
        score = float(data.get("quality_score", 0.5))
        rationale = str(data.get("rationale", "No rationale provided"))
        return max(0.0, min(1.0, score)), rationale
    except Exception:
        return 0.5, "Failed to parse judge response"


# --- mlflow (optional) -------------------------------------------------------


def setup_mlflow(
    experiment_name: str,
    tracking_uri: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> None:
    if _use_fakes():
        os.environ.pop("MLFLOW_TRACKING_URI", None)
        try:
            import mlflow
        except ImportError:
            print("SANTA_EVAL_FAKE=1; mlflow not installed")
            return
        dest = REPO_ROOT / "out" / "mlruns"
        dest.mkdir(parents=True, exist_ok=True)
        mlflow.set_tracking_uri(dest.resolve().as_uri())
        mlflow.set_experiment(experiment_name)
        print("SANTA_EVAL_FAKE=1; mlflow local file store", dest)
        return
    try:
        import mlflow
    except ImportError:
        print("mlflow not installed; skip tracking (uv sync --group research)")
        return
    tracking_uri = tracking_uri or os.getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        print("MLFLOW_TRACKING_URI unset; skip tracking")
        return
    if username or password:
        username = username or os.getenv("MLFLOW_TRACKING_USERNAME")
        password = password or os.getenv("MLFLOW_TRACKING_PASSWORD")
        if username and password:
            tracking_uri = tracking_uri.replace("https://", f"https://{username}:{password}@")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    print("MLflow tracking URI:", mlflow.get_tracking_uri())


def log_llm_evaluation(
    model_name: str,
    prompt: str,
    response: str,
    metrics: dict[str, Any],
    quality_score: float | None = None,
    tags: dict[str, str] | None = None,
) -> str:
    if _use_fakes():
        return "mlflow_skipped_fake"
    try:
        import mlflow
    except ImportError:
        return "mlflow_not_available"
    if not os.getenv("MLFLOW_TRACKING_URI"):
        return "mlflow_not_available"
    with mlflow.start_run(run_name=f"{model_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"):
        mlflow.log_param("model", model_name)
        mlflow.log_metric("latency_ms", metrics.get("latency_ms", 0))
        if quality_score is not None:
            mlflow.log_metric("quality_score", quality_score)
        mlflow.log_text(prompt, "prompt.txt")
        mlflow.log_text(response, "response.txt")
        if tags:
            mlflow.set_tags(tags)
        run = mlflow.active_run()
        return run.info.run_id if run else "mlflow_not_available"


def log_image_evaluation(
    model_name: str,
    service: str,
    prompt: str,
    image_url: str,
    metrics: dict[str, Any],
    quality_score: float | None = None,
    tags: dict[str, str] | None = None,
) -> str:
    if _use_fakes():
        return "mlflow_skipped_fake"
    try:
        import mlflow
    except ImportError:
        return "mlflow_not_available"
    if not os.getenv("MLFLOW_TRACKING_URI"):
        return "mlflow_not_available"
    with mlflow.start_run(
        run_name=f"{service}-{model_name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    ):
        mlflow.log_param("model", model_name)
        mlflow.log_param("service", service)
        mlflow.log_metric("latency_ms", metrics.get("latency_ms", 0))
        if quality_score is not None:
            mlflow.log_metric("quality_score", quality_score)
        mlflow.log_text(prompt, "prompt.txt")
        if image_url.startswith("http"):
            mlflow.log_param("image_url", image_url)
        elif Path(image_url).is_file():
            mlflow.log_artifact(image_url)
        if tags:
            mlflow.set_tags(tags)
        run = mlflow.active_run()
        return run.info.run_id if run else "mlflow_not_available"


def download_image_for_mlflow(image_data: str | bytes) -> str:
    if isinstance(image_data, bytes):
        with NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp.write(image_data)
            return tmp.name
    path = Path(image_data)
    if path.is_file():
        return str(path)
    return str(image_data)


# --- cost / bench ------------------------------------------------------------


def calculate_self_hosted_cost(
    latency_ms: float,
    tokens_in: int,
    tokens_out: int,
    cost_infra_per_hour: float,
) -> tuple[float, float]:
    latency_hours = latency_ms / 1000 / 3600
    cost_for_request = latency_hours * cost_infra_per_hour
    cost_per_1m_out = (cost_for_request / tokens_out) * 1_000_000 if tokens_out else 0.0
    cost_per_1m_in = (cost_for_request / tokens_in) * 1_000_000 if tokens_in else 0.0
    return cost_per_1m_in, cost_per_1m_out


def calculate_cost_1m_requests(
    cost_per_1m_in: float,
    cost_per_1m_out: float,
    tokens_in: int,
    tokens_out: int,
) -> float:
    return (
        tokens_in * (cost_per_1m_in / 1_000_000) * 1_000_000
        + tokens_out * (cost_per_1m_out / 1_000_000) * 1_000_000
    )


@dataclass
class BenchmarkResult:
    model_name: str
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    throughput_tokens_per_sec: float
    cost_per_1m_in: float | None
    cost_per_1m_out: float | None
    cost_per_1m_in_throughput_based: float | None
    cost_per_1m_out_throughput_based: float | None
    cost_1m_requests: float | None
    cost_1m_requests_throughput_based: float | None
    tokens_in_avg: float
    tokens_out_avg: float
    success_rate: float
    total_requests: int
    successful_requests: int


def results_to_dataframe(results: list[BenchmarkResult], concurrency: int | None = None) -> Any:
    import pandas as pd

    rows = []
    for result in results:
        row = result.__dict__.copy()
        if concurrency is not None:
            row["concurrency"] = concurrency
        rows.append(row)
    return pd.DataFrame(rows)


def run_benchmark_suite(
    model_configs: list[EvalModel],
    test_profiles: list[KidProfile],
    concurrency: int = 10,
    output_csv_path: Path | None = None,
) -> list[BenchmarkResult]:
    del concurrency
    results: list[BenchmarkResult] = []
    for cfg in model_configs:
        latencies: list[float] = []
        ok = 0
        for kid in test_profiles:
            try:
                _rec, metrics = generate_gift_recommendation(cfg.client, kid)
                latencies.append(float(metrics.get("latency_ms") or 0))
                ok += 1
            except Exception:
                pass
        n = len(test_profiles)
        p50 = sorted(latencies)[len(latencies) // 2] if latencies else 0.0
        results.append(
            BenchmarkResult(
                model_name=cfg.name,
                latency_p50_ms=p50,
                latency_p95_ms=latencies[-1] if latencies else 0.0,
                latency_p99_ms=latencies[-1] if latencies else 0.0,
                throughput_tokens_per_sec=0.0,
                cost_per_1m_in=cfg.cost_per_1m_tokens_in,
                cost_per_1m_out=cfg.cost_per_1m_tokens_out,
                cost_per_1m_in_throughput_based=None,
                cost_per_1m_out_throughput_based=None,
                cost_1m_requests=None,
                cost_1m_requests_throughput_based=None,
                tokens_in_avg=0.0,
                tokens_out_avg=0.0,
                success_rate=(ok / n) if n else 0.0,
                total_requests=n,
                successful_requests=ok,
            )
        )
    if output_csv_path:
        results_to_dataframe(results).to_csv(output_csv_path, index=False)
    return results


# Re-export card/prompt builders so notebooks can `from santa.eval import image_prompt`.
gift_recommendation_prompt = gift_recommendation_prompt
wish_prompt = wish_prompt
image_prompt = image_prompt
