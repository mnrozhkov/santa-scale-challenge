"""Policy caps and shared budget for Experiment B (evaluate-before-escalate)."""

from __future__ import annotations

import threading
from typing import Any

from pydantic import BaseModel

from santa.config import PolicyFile


class PolicyError(RuntimeError):
    """Hard attempt/cap refusal returned to the model via ModelRetry."""


class BudgetExceeded(RuntimeError):
    """Shared budget refusal returned to the model via ModelRetry."""


class GateError(RuntimeError):
    """Video gate refusal — image must be PASS before H100 is spent."""


class Policy(BaseModel):
    max_image_attempts: int = 5
    max_video_attempts: int = 2
    budget_usd: float = 1.50
    max_parallel_kids: int = 4
    max_steps_per_kid: int = 30
    gate_video_on_image_pass: bool = True
    estimate_image_seconds: float = 12
    estimate_video_seconds: float = 120
    image_retry_threshold: int = 70

    @classmethod
    def from_file(cls, file: PolicyFile, *, budget_usd: float | None = None) -> Policy:
        data = file.model_dump()
        if budget_usd is not None:
            data["budget_usd"] = budget_usd
        return cls.model_validate(data)

    def check_image_attempts(self, used: int) -> None:
        if used >= self.max_image_attempts:
            raise PolicyError(f"image attempts {used}/{self.max_image_attempts} used")

    def check_video_attempts(self, used: int) -> None:
        if used >= self.max_video_attempts:
            raise PolicyError(f"video attempts {used}/{self.max_video_attempts} used")


class Budget:
    """Shared across kids. ``reserve`` / ``commit`` under a lock; no I/O inside the lock."""

    def __init__(self, limit_usd: float) -> None:
        self.limit_usd = float(limit_usd)
        self._spent = 0.0
        self._reserved = 0.0
        self._lock = threading.Lock()

    @property
    def spent(self) -> float:
        with self._lock:
            return self._spent

    @property
    def remaining(self) -> float:
        with self._lock:
            return max(0.0, self.limit_usd - self._spent - self._reserved)

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 1e-9

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            remaining = max(0.0, self.limit_usd - self._spent - self._reserved)
            return {
                "spent": round(self._spent, 6),
                "reserved": round(self._reserved, 6),
                "remaining": round(remaining, 6),
                "limit": self.limit_usd,
            }

    def reserve(self, estimate_usd: float) -> None:
        need = max(0.0, float(estimate_usd))
        with self._lock:
            remaining = self.limit_usd - self._spent - self._reserved
            if need > remaining + 1e-12:
                raise BudgetExceeded(f"need ~${need:.4f}, remaining ${remaining:.4f}")
            self._reserved += need

    def commit(self, actual_usd: float, *, reserved_usd: float) -> None:
        actual = max(0.0, float(actual_usd))
        reserved = max(0.0, float(reserved_usd))
        with self._lock:
            self._reserved = max(0.0, self._reserved - reserved)
            self._spent += actual

    def release(self, reserved_usd: float) -> None:
        """Drop a reservation without spending (call failed before attribution)."""
        reserved = max(0.0, float(reserved_usd))
        with self._lock:
            self._reserved = max(0.0, self._reserved - reserved)


def estimate_cost_usd(
    platform: str,
    preset: str,
    seconds: float,
    *,
    preemptible: bool = True,
) -> float:
    from santa.cost import cost_usd

    return cost_usd(platform, preset, seconds, preemptible=preemptible)


def compute_for_role(settings: Any, role: str) -> tuple[str, str]:
    """Return ``(platform, preset)`` from role compute, with safe defaults."""
    try:
        cfg = settings.role(role)
    except Exception:
        cfg = None
    compute = getattr(cfg, "compute", None) if cfg is not None else None
    if compute is not None:
        return compute.platform, compute.preset
    if role == "image":
        return "gpu-l40s-a", "1gpu-8vcpu-32gb"
    return "gpu-h100-sxm", "1gpu-16vcpu-200gb"
