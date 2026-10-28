"""Mutable per-kid state and structured reports for Experiment B."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from santa.agent.policy import Policy
from santa.schemas import GiftRecommendation, KidProfile, Wish


class Evaluation(BaseModel):
    decision: Literal["PASS", "RETRY", "WEAK"]
    score: int = Field(ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    passed: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    fix: Literal["seed", "prompt", "none"] = "none"
    cause: Literal["image", "motion", "none"] = "none"
    prompt_suffix: str = ""
    motion_metric: float | None = None
    judge_model: str = ""


class Attempt(BaseModel):
    kind: Literal["image", "video"]
    n: int
    seed: int | None = None
    prompt_suffix: str = ""
    motion_hint: str = ""
    source_image_n: int | None = None
    path: str = ""
    latency_s: float = 0.0
    cost_usd: float = 0.0
    platform: str = ""
    preset: str = ""
    fallback: bool = False
    evaluation: Evaluation | None = None
    gate_bypassed: bool = False  # True when keep_best animates without image PASS


class KidReport(BaseModel):
    kid_id: str
    status: Literal["accepted", "kept_best", "failed"]
    image_attempts: int = 0
    video_attempts: int = 0
    image_n: int | None = None
    video_n: int | None = None
    gpu_seconds_l40s: float = 0.0
    gpu_seconds_h100: float = 0.0
    cost_usd: float = 0.0
    h100_seconds_on_rejected_images: float = 0.0
    decision_log: list[str] = Field(default_factory=list)


class RunReport(BaseModel):
    run_id: str
    mode: Literal["agent", "pipeline", "pipeline-retry-all"]
    policy: Policy
    kids: list[KidReport] = Field(default_factory=list)
    totals: dict[str, Any] = Field(default_factory=dict)
    cost_model: str = "attributed: gpu_hourly_rate × call_latency; endpoints bill while running"


@dataclass
class KidState:
    kid: KidProfile
    rec: GiftRecommendation | None = None
    wish: Wish | None = None
    images: list[Attempt] = field(default_factory=list)
    videos: list[Attempt] = field(default_factory=list)
    accepted_image_n: int | None = None
    accepted_video_n: int | None = None
    status: Literal["accepted", "kept_best", "failed"] | None = None
    decision_log: list[str] = field(default_factory=list)
    kept_best: bool = False

    def image(self, n: int) -> Attempt | None:
        for attempt in self.images:
            if attempt.n == n:
                return attempt
        return None

    def video(self, n: int) -> Attempt | None:
        for attempt in self.videos:
            if attempt.n == n:
                return attempt
        return None

    def best_image(self) -> Attempt | None:
        scored = [a for a in self.images if a.evaluation is not None]
        if not scored:
            return self.images[-1] if self.images else None
        return max(scored, key=lambda a: a.evaluation.score if a.evaluation else -1)

    def best_video(self) -> Attempt | None:
        scored = [a for a in self.videos if a.evaluation is not None]
        if not scored:
            return self.videos[-1] if self.videos else None
        return max(scored, key=lambda a: a.evaluation.score if a.evaluation else -1)

    def gpu_seconds(self) -> tuple[float, float]:
        l40s = sum(a.latency_s for a in self.images if not a.fallback)
        h100 = sum(a.latency_s for a in self.videos if not a.fallback)
        return l40s, h100

    def cost_total(self) -> float:
        return sum(a.cost_usd for a in self.images) + sum(a.cost_usd for a in self.videos)

    def h100_on_rejected_images(self) -> float:
        """H100 spent animating images that failed eval — excludes keep_best bypass."""
        rejected = {
            a.n
            for a in self.images
            if a.evaluation is not None and a.evaluation.decision == "RETRY"
        }
        return sum(
            v.latency_s
            for v in self.videos
            if not v.fallback and not v.gate_bypassed and v.source_image_n in rejected
        )

    def to_report(self) -> KidReport:
        status = self.status or "failed"
        return KidReport(
            kid_id=self.kid.id,
            status=status,
            image_attempts=len(self.images),
            video_attempts=len(self.videos),
            image_n=self.accepted_image_n,
            video_n=self.accepted_video_n,
            gpu_seconds_l40s=self.gpu_seconds()[0],
            gpu_seconds_h100=self.gpu_seconds()[1],
            cost_usd=round(self.cost_total(), 6),
            h100_seconds_on_rejected_images=self.h100_on_rejected_images(),
            decision_log=list(self.decision_log),
        )
