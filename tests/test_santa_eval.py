"""Research eval helpers: samples, fakes, generate wrappers. No cloud."""

from __future__ import annotations

import os

from santa.eval import (
    FakeEvalLLM,
    calculate_cost_1m_requests,
    evaluate_quality_with_judge,
    generate_gift_quality_judge_prompt,
    generate_gift_recommendation,
    generate_wish,
    get_available_models,
    get_test_profiles,
    get_test_recommendations_for_wish,
    run_benchmark_suite,
)
from santa.schemas import KidProfile


def test_test_profiles_are_valid() -> None:
    kids = get_test_profiles()
    assert len(kids) == 4
    assert kids[0].name == "Emma"
    recs = get_test_recommendations_for_wish()
    assert recs[0].kid_id == kids[0].id


def test_generate_gift_and_wish_from_fake() -> None:
    kid = KidProfile(name="Mia", age=7, wishlist=["trains"])
    llm = FakeEvalLLM()
    rec, metrics = generate_gift_recommendation(llm, kid)
    assert rec.gifts and "latency_ms" in metrics
    wish, wmetrics = generate_wish(llm, kid, rec)
    assert wish.text and "Merry Christmas" in wish.text
    assert "latency_ms" in wmetrics


def test_get_available_models_honours_eval_fake(monkeypatch) -> None:
    monkeypatch.setenv("SANTA_EVAL_FAKE", "1")
    models = get_available_models(include_openai=True, include_token_factory=True)
    assert models and models[0].name == "fake-llm"
    assert len(models) >= 3


def test_judge_and_cost_helpers() -> None:
    kid = get_test_profiles()[0]
    prompt = generate_gift_quality_judge_prompt(kid, '{"gifts":["x"]}')
    score, why = evaluate_quality_with_judge(FakeEvalLLM(), prompt)
    assert 0.0 <= score <= 1.0 and why
    assert calculate_cost_1m_requests(0.15, 0.6, 100, 50) > 0


def test_run_benchmark_suite_with_fake() -> None:
    os.environ["SANTA_EVAL_FAKE"] = "1"
    models = get_available_models()
    results = run_benchmark_suite(models, get_test_profiles())
    assert results and results[0].successful_requests == 4
