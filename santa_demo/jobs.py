"""GPU Job runner for batch video — one PNG per Wan Job."""

from __future__ import annotations

import os
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class JobRunnerConfigError(ValueError):
    """Raised when Job / storage env is missing."""


@dataclass
class JobResult:
    id: str
    state: str
    png_path: str
    mp4_url: str | None = None
    error: str | None = None


class JobRunner(Protocol):
    def submit(self, png_paths: list[Path]) -> list[JobResult]:
        ...

    def poll(self, jobs: list[JobResult]) -> list[JobResult]:
        ...


@dataclass
class NebiusJobRunner:
    """Submit GPU Jobs via the Nebius CLI. Preemptible is GPU-only."""

    job_image: str
    platform: str = "gpu-h100-sxm"
    preset: str = "1gpu-16vcpu-200gb"
    preemptible: bool = True
    bucket: str = ""

    @classmethod
    def from_env(cls) -> NebiusJobRunner:
        image = (os.environ.get("VIDEO_JOB_IMAGE") or "").strip()
        if not image:
            raise JobRunnerConfigError("VIDEO_JOB_IMAGE is required (Wan container for GPU Jobs).")
        return cls(
            job_image=image,
            platform=os.environ.get("VIDEO_JOB_PLATFORM", "gpu-h100-sxm"),
            preset=os.environ.get("VIDEO_JOB_PRESET", "1gpu-16vcpu-200gb"),
            preemptible=os.environ.get("VIDEO_JOB_PREEMPTIBLE", "true").lower() != "false",
            bucket=os.environ.get("NEBIUS_S3_BUCKET", ""),
        )

    def submit(self, png_paths: list[Path]) -> list[JobResult]:
        results: list[JobResult] = []
        for png in png_paths:
            name = f"santa-video-{uuid.uuid4().hex[:8]}"
            cmd = [
                "nebius",
                "ai",
                "job",
                "create",
                "--name",
                name,
                "--image",
                self.job_image,
                "--platform",
                self.platform,
                "--preset",
                self.preset,
            ]
            if self.preemptible:
                cmd.append("--preemptible")
            if self.bucket:
                cmd.extend(["--volume", f"{self.bucket}:/data"])
            try:
                proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
                job_id = (proc.stdout or name).strip().split()[-1]
                results.append(JobResult(id=job_id, state="PENDING", png_path=str(png)))
            except (FileNotFoundError, subprocess.CalledProcessError) as exc:
                results.append(
                    JobResult(
                        id=name,
                        state="FAILED",
                        png_path=str(png),
                        error=str(exc),
                    )
                )
        return results

    def poll(self, jobs: list[JobResult]) -> list[JobResult]:
        updated: list[JobResult] = []
        for job in jobs:
            if job.state in {"COMPLETED", "FAILED"}:
                updated.append(job)
                continue
            try:
                proc = subprocess.run(
                    ["nebius", "ai", "job", "get", "--id", job.id],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                text = proc.stdout.lower()
                if "error" in text or "failed" in text:
                    job.state = "FAILED"
                    job.error = proc.stdout.strip()
                elif "complete" in text or "succeeded" in text:
                    job.state = "COMPLETED"
                    if self.bucket:
                        job.mp4_url = f"{self.bucket}/demo/videos/{Path(job.png_path).stem}.mp4"
                else:
                    job.state = "RUNNING"
            except (FileNotFoundError, subprocess.CalledProcessError) as exc:
                job.state = "FAILED"
                job.error = str(exc)
            updated.append(job)
        return updated
