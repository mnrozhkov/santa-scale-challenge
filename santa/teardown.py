"""Stop the participant's Serverless AI endpoints and cancel lingering jobs.

``run`` takes injected list/stop/cancel ports so tests never talk to Nebius.
Live adapters use the Nebius Python SDK (same auth as ``SdkJobService``).
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from santa.cost import hourly_rate
from santa.nebius_jobs import NebiusJobError

_STOPPABLE_ENDPOINT = frozenset({"RUNNING", "STARTING", "PROVISIONING", "IMAGE_PULLING"})
_TERMINAL_JOB = frozenset(
    {
        "COMPLETED",
        "SUCCEEDED",
        "SUCCESS",
        "DONE",
        "FAILED",
        "ERROR",
        "CANCELLED",
        "CANCELED",
    }
)


@dataclass
class TeardownItem:
    kind: Literal["endpoint", "job"]
    id: str
    name: str
    state: str
    platform: str
    preset: str
    preemptible: bool


@dataclass
class TeardownReport:
    stopped: list[TeardownItem]
    cancelled: list[TeardownItem]
    remaining: list[TeardownItem]
    saved_usd_per_hour: float
    dry_run: bool


class EndpointPort(Protocol):
    def list(self) -> list[TeardownItem]:
        ...

    def stop(self, item_id: str) -> None:
        ...


class JobPort(Protocol):
    def list(self) -> list[TeardownItem]:
        ...

    def cancel(self, item_id: str) -> None:
        ...


def require_credentials() -> tuple[str, str]:
    """Return ``(token, project_id)`` or raise a participant-readable error."""
    token = (os.environ.get("NEBIUS_IAM_TOKEN") or "").strip()
    if not token:
        raise NebiusJobError(
            "NEBIUS_IAM_TOKEN is missing. Run: nebius iam get-access-token, then set it in .env."
        )
    project_id = (os.environ.get("NEBIUS_PROJECT_ID") or "").strip()
    if not project_id:
        raise NebiusJobError("NEBIUS_PROJECT_ID is missing.")
    return token, project_id


def _norm_state(state: str) -> str:
    return (state or "").upper()


def _endpoint_stoppable(state: str) -> bool:
    return _norm_state(state) in _STOPPABLE_ENDPOINT


def _job_terminal(state: str) -> bool:
    return _norm_state(state) in _TERMINAL_JOB


def _saved_usd_per_hour(items: list[TeardownItem]) -> float:
    return sum(
        hourly_rate(i.platform, i.preset, preemptible=i.preemptible).usd_per_hour for i in items
    )


def run(*, dry_run: bool, endpoints: EndpointPort, jobs: JobPort) -> TeardownReport:
    """List project endpoints/jobs, stop/cancel active ones, report leftovers and $/h saved."""
    listed_eps = endpoints.list()
    listed_jobs = jobs.list()
    to_stop = [e for e in listed_eps if _endpoint_stoppable(e.state)]
    to_cancel = [j for j in listed_jobs if not _job_terminal(j.state)]
    if not dry_run:
        for item in to_stop:
            endpoints.stop(item.id)
        for item in to_cancel:
            jobs.cancel(item.id)
    remaining = endpoints.list() + jobs.list()
    return TeardownReport(
        stopped=to_stop,
        cancelled=to_cancel,
        remaining=remaining,
        saved_usd_per_hour=_saved_usd_per_hour(to_stop + to_cancel),
        dry_run=dry_run,
    )


def _state_name(state: object) -> str:
    name = getattr(state, "name", None)
    return str(name or state or "").upper()


def _wait_op(op: Any) -> None:
    if hasattr(op, "sync_wait"):
        op.sync_wait()


def _endpoint_item(raw: Any) -> TeardownItem:
    meta = getattr(raw, "metadata", None)
    spec = getattr(raw, "spec", None)
    status = getattr(raw, "status", None)
    return TeardownItem(
        kind="endpoint",
        id=str(getattr(meta, "id", "") or ""),
        name=str(getattr(meta, "name", "") or ""),
        state=_state_name(getattr(status, "state", None)),
        platform=str(getattr(spec, "platform", "") or ""),
        preset=str(getattr(spec, "preset", "") or ""),
        preemptible=bool(getattr(spec, "preemptible", False)),
    )


def _job_item(raw: Any) -> TeardownItem:
    meta = getattr(raw, "metadata", None)
    spec = getattr(raw, "spec", None)
    status = getattr(raw, "status", None)
    return TeardownItem(
        kind="job",
        id=str(getattr(meta, "id", "") or ""),
        name=str(getattr(meta, "name", "") or ""),
        state=_state_name(getattr(status, "state", None)),
        platform=str(getattr(spec, "platform", "") or ""),
        preset=str(getattr(spec, "preset", "") or ""),
        preemptible=bool(getattr(spec, "preemptible", False)),
    )


def _list_pages(client: Any, request_cls: Any, project_id: str, to_item: Any) -> list[TeardownItem]:
    items: list[TeardownItem] = []
    token = ""
    while True:
        kw: dict[str, Any] = {"parent_id": project_id}
        if token:
            kw["page_token"] = token
        resp = client.list(request_cls(**kw)).wait()
        for raw in getattr(resp, "items", None) or []:
            items.append(to_item(raw))
        token = str(getattr(resp, "next_page_token", "") or "")
        if not token:
            break
    return items


def _sdk(token: str) -> Any:
    from nebius.aio.token.static import Bearer
    from nebius.sdk import SDK

    return SDK(credentials=Bearer(token), user_agent_prefix="santa/2")


class SdkEndpointPort:
    """Live ``EndpointServiceClient`` authenticated with ``NEBIUS_IAM_TOKEN``."""

    def __init__(self, client: Any, *, project_id: str) -> None:
        self.client = client
        self.project_id = project_id

    @classmethod
    def from_env(cls) -> SdkEndpointPort:
        token, project_id = require_credentials()
        from nebius.api.nebius.ai.v1 import EndpointServiceClient

        return cls(EndpointServiceClient(_sdk(token)), project_id=project_id)

    def list(self) -> list[TeardownItem]:
        from nebius.api.nebius.ai.v1 import ListEndpointsRequest

        return _list_pages(self.client, ListEndpointsRequest, self.project_id, _endpoint_item)

    def stop(self, item_id: str) -> None:
        from nebius.api.nebius.ai.v1 import StopEndpointRequest

        op = self.client.stop(StopEndpointRequest(id=item_id)).wait()
        _wait_op(op)


class SdkJobPort:
    """Live ``JobServiceClient`` list/cancel authenticated with ``NEBIUS_IAM_TOKEN``."""

    def __init__(self, client: Any, *, project_id: str) -> None:
        self.client = client
        self.project_id = project_id

    @classmethod
    def from_env(cls) -> SdkJobPort:
        token, project_id = require_credentials()
        from nebius.api.nebius.ai.v1 import JobServiceClient

        return cls(JobServiceClient(_sdk(token)), project_id=project_id)

    def list(self) -> list[TeardownItem]:
        from nebius.api.nebius.ai.v1 import ListJobsRequest

        return _list_pages(self.client, ListJobsRequest, self.project_id, _job_item)

    def cancel(self, item_id: str) -> None:
        from nebius.api.nebius.ai.v1 import CancelJobRequest

        op = self.client.cancel(CancelJobRequest(id=item_id)).wait()
        _wait_op(op)


def ports_from_env() -> tuple[SdkEndpointPort, SdkJobPort]:
    token, project_id = require_credentials()
    from nebius.api.nebius.ai.v1 import EndpointServiceClient, JobServiceClient

    sdk = _sdk(token)
    return (
        SdkEndpointPort(EndpointServiceClient(sdk), project_id=project_id),
        SdkJobPort(JobServiceClient(sdk), project_id=project_id),
    )


def _fmt_item(item: TeardownItem) -> str:
    preempt = " preemptible" if item.preemptible else ""
    return (
        f"  {item.kind} {item.id}  {item.name}  {item.state}  "
        f"{item.platform} {item.preset}{preempt}"
    )


def print_report(report: TeardownReport) -> None:
    mode = "dry-run — would stop/cancel, nothing changed" if report.dry_run else "live"
    print(f"santa teardown ({mode})")
    print(
        f"stop {len(report.stopped)} endpoint(s), cancel {len(report.cancelled)} job(s). "
        f"~${report.saved_usd_per_hour:.2f}/h saved."
    )
    if report.stopped:
        print("Stopped:" if not report.dry_run else "Would stop:")
        for item in report.stopped:
            print(_fmt_item(item))
    if report.cancelled:
        print("Cancelled:" if not report.dry_run else "Would cancel:")
        for item in report.cancelled:
            print(_fmt_item(item))
    print("Still in the project:" if report.remaining else "Nothing left in the project.")
    for item in report.remaining:
        print(_fmt_item(item))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="santa teardown",
        description="Stop your Serverless AI endpoints and cancel lingering jobs.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would stop/cancel without changing anything.",
    )
    args = parser.parse_args(argv)
    try:
        endpoints, jobs = ports_from_env()
        report = run(dry_run=args.dry_run, endpoints=endpoints, jobs=jobs)
    except NebiusJobError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
