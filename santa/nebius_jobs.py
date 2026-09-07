"""Nebius Serverless Jobs: build a spec from ``config/models.yaml`` ``job:`` and wait.

The SDK ``JobServiceClient`` is wrapped behind a tiny protocol so tests inject a fake.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Protocol

from santa.config import JobSpec, Settings


class NebiusJobError(RuntimeError):
    """A job create/wait/cancel failed; message is participant-readable."""


@dataclass
class JobPayload:
    """Everything ``create`` needs, derived from yaml ``job:`` + env + this run."""

    image: str
    platform: str
    preset: str
    preemptible: bool
    disk_gb: int
    timeout_min: int
    mount_path: str
    bucket_id: str
    env: dict[str, str]
    command: str = "python"
    args: str = "-m santa.job"
    project_id: str = ""
    subnet_id: str = ""
    name: str = ""


@dataclass
class StateTransition:
    state: str
    at: float


@dataclass
class JobWait:
    job_id: str
    timeline: list[StateTransition] = field(default_factory=list)
    state: str = ""
    run_s: float = 0.0


class JobService(Protocol):
    def create(self, payload: JobPayload) -> str:
        ...

    def get(self, job_id: str) -> str:
        ...

    def cancel(self, job_id: str) -> None:
        ...


_DONE = frozenset(
    {"COMPLETED", "SUCCEEDED", "SUCCESS", "DONE", "FAILED", "ERROR", "CANCELLED", "CANCELED"}
)
_FAILED = frozenset({"FAILED", "ERROR", "CANCELLED", "CANCELED"})


def job_payload(
    settings: Settings,
    *,
    run_id: str,
    chunk: str,
    name: str = "",
) -> JobPayload:
    """Build a JobPayload from the yaml ``job:`` block and ``NEBIUS_*`` env."""
    spec: JobSpec = settings.job
    bucket = (os.environ.get("NEBIUS_BUCKET_ID") or "").strip()
    if not spec.image:
        raise NebiusJobError(
            "job.image is empty in config/models.yaml. Push santa-job (issue 08) and set the tag."
        )
    if not bucket:
        raise NebiusJobError("NEBIUS_BUCKET_ID is missing. Mount your bucket at /data.")
    hf_home = spec.hf_home or "/data/models"
    chunk_path = (
        chunk if chunk.startswith("/") else f"{spec.mount_path.rstrip('/')}/{chunk.lstrip('/')}"
    )
    return JobPayload(
        image=spec.image,
        platform=spec.platform,
        preset=spec.preset,
        preemptible=spec.preemptible,
        disk_gb=spec.disk_gb,
        timeout_min=spec.timeout_min,
        mount_path=spec.mount_path,
        bucket_id=bucket,
        env={
            "RUN_ID": run_id,
            "CHUNK": chunk_path,
            "HF_HOME": hf_home,
        },
        command="python",
        args="-m santa.job",
        project_id=(os.environ.get("NEBIUS_PROJECT_ID") or "").strip(),
        subnet_id=(os.environ.get("NEBIUS_SUBNET_ID") or "").strip(),
        name=name or f"santa-{run_id}",
    )


def create_and_wait(
    service: JobService,
    payload: JobPayload,
    *,
    poll_s: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.time,
) -> JobWait:
    """Create a job and poll until a terminal state. Records the state timeline."""
    job_id = service.create(payload)
    try:
        return _wait_for_job_completion(service, job_id, poll_s=poll_s, sleep=sleep, now=now)
    except BaseException:
        _cancel_nebius_job(service, job_id)
        raise


def _wait_for_job_completion(
    service: JobService,
    job_id: str,
    *,
    poll_s: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.time,
) -> JobWait:
    timeline: list[StateTransition] = []
    t0 = now()
    last = ""
    while True:
        state = (service.get(job_id) or "").upper()
        if state != last:
            timeline.append(StateTransition(state=state, at=now()))
            last = state
        if state in _DONE:
            run_s = now() - t0
            result = JobWait(job_id=job_id, timeline=timeline, state=state, run_s=run_s)
            if state in _FAILED:
                raise NebiusJobError(f"job {job_id} ended {state}")
            return result
        sleep(poll_s)


def _cancel_nebius_job(service: JobService, job_id: str) -> None:
    try:
        service.cancel(job_id)
    except Exception:
        pass


def to_sdk_spec(payload: JobPayload) -> Any:
    """Map ``JobPayload`` onto the Nebius SDK ``JobSpec`` (lazy import)."""
    from nebius.api.nebius.ai.v1 import JobSpec as SdkJobSpec

    env = [SdkJobSpec.EnvironmentVariable(name=k, value=v) for k, v in payload.env.items()]
    volume = SdkJobSpec.VolumeMount(
        source=payload.bucket_id,
        container_path=payload.mount_path,
    )
    disk = SdkJobSpec.DiskSpec(size_bytes=payload.disk_gb * 1024**3) if payload.disk_gb else None
    kw: dict[str, Any] = {
        "image": payload.image,
        "platform": payload.platform,
        "preset": payload.preset,
        "preemptible": payload.preemptible,
        "environment_variables": env,
        "volumes": [volume],
        "container_command": payload.command,
        "args": payload.args,
        "timeout": timedelta(minutes=payload.timeout_min),
    }
    if payload.subnet_id:
        kw["subnet_id"] = payload.subnet_id
    if disk is not None:
        kw["disk"] = disk
    return SdkJobSpec(**kw)
