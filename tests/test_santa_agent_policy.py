"""Unit tests for Policy / Budget (Experiment B)."""

from __future__ import annotations

import threading

import pytest

from santa.agent.policy import Budget, BudgetExceeded, Policy, PolicyError


def test_policy_attempt_caps() -> None:
    policy = Policy(max_image_attempts=2, max_video_attempts=2)
    policy.check_image_attempts(0)
    policy.check_image_attempts(1)
    with pytest.raises(PolicyError, match="image attempts 2/2"):
        policy.check_image_attempts(2)
    with pytest.raises(PolicyError, match="video attempts 2/2"):
        policy.check_video_attempts(2)


def test_budget_reserve_commit_releases_difference() -> None:
    budget = Budget(1.0)
    budget.reserve(0.4)
    assert budget.snapshot()["remaining"] == pytest.approx(0.6)
    budget.commit(0.25, reserved_usd=0.4)
    snap = budget.snapshot()
    assert snap["spent"] == pytest.approx(0.25)
    assert snap["remaining"] == pytest.approx(0.75)


def test_budget_exhausted_raises() -> None:
    budget = Budget(0.1)
    budget.reserve(0.1)
    budget.commit(0.1, reserved_usd=0.1)
    with pytest.raises(BudgetExceeded, match="remaining"):
        budget.reserve(0.01)
    assert budget.exhausted


def test_budget_concurrent_only_one_fits() -> None:
    budget = Budget(0.5)
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        barrier.wait()
        try:
            budget.reserve(0.4)
            budget.commit(0.4, reserved_usd=0.4)
        except BudgetExceeded as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 1
    assert budget.spent == pytest.approx(0.4)
    assert budget.spent <= budget.limit_usd
