"""Teardown: fake EndpointPort / JobPort only — no live Nebius, no CLI spawn."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from typer.testing import CliRunner

from santa.cli import app
from santa.cost import hourly_rate
from santa.nebius_jobs import NebiusJobError
from santa.teardown import TeardownItem, require_credentials, run


def _item(
    kind: str,
    id: str,
    *,
    name: str = "",
    state: str,
    platform: str = "gpu-h100-sxm",
    preset: str = "1gpu-16vcpu-200gb",
    preemptible: bool = False,
) -> TeardownItem:
    return TeardownItem(
        kind=kind,
        id=id,
        name=name or id,
        state=state,
        platform=platform,
        preset=preset,
        preemptible=preemptible,
    )


@dataclass
class FakeEndpoints:
    items: list[TeardownItem]
    stopped_ids: list[str] = field(default_factory=list)

    def list(self) -> list[TeardownItem]:
        return list(self.items)

    def stop(self, item_id: str) -> None:
        self.stopped_ids.append(item_id)
        self.items = [i for i in self.items if i.id != item_id]


@dataclass
class FakeJobs:
    items: list[TeardownItem]
    cancelled_ids: list[str] = field(default_factory=list)

    def list(self) -> list[TeardownItem]:
        return list(self.items)

    def cancel(self, item_id: str) -> None:
        self.cancelled_ids.append(item_id)
        self.items = [i for i in self.items if i.id != item_id]


def test_dry_run_lists_running_endpoint_and_queued_job_without_stop_cancel() -> None:
    ep = _item("endpoint", "ep-1", name="sana", state="RUNNING")
    job = _item("job", "job-1", name="batch-0", state="QUEUED", preemptible=True)
    endpoints = FakeEndpoints([ep])
    jobs = FakeJobs([job])

    report = run(dry_run=True, endpoints=endpoints, jobs=jobs)

    assert report.dry_run is True
    assert [i.id for i in report.stopped] == ["ep-1"]
    assert [i.id for i in report.cancelled] == ["job-1"]
    assert endpoints.stopped_ids == []
    assert jobs.cancelled_ids == []
    expected = (
        hourly_rate(ep.platform, ep.preset, preemptible=ep.preemptible).usd_per_hour
        + hourly_rate(job.platform, job.preset, preemptible=job.preemptible).usd_per_hour
    )
    assert report.saved_usd_per_hour == expected
    assert {i.id for i in report.remaining} == {"ep-1", "job-1"}


def test_live_stops_endpoint_cancels_job_remaining_empty() -> None:
    ep = _item("endpoint", "ep-1", name="wan", state="STARTING")
    job = _item("job", "job-1", name="batch-0", state="RUNNING", preemptible=True)
    endpoints = FakeEndpoints([ep])
    jobs = FakeJobs([job])

    report = run(dry_run=False, endpoints=endpoints, jobs=jobs)

    assert report.dry_run is False
    assert endpoints.stopped_ids == ["ep-1"]
    assert jobs.cancelled_ids == ["job-1"]
    assert [i.id for i in report.stopped] == ["ep-1"]
    assert [i.id for i in report.cancelled] == ["job-1"]
    assert report.remaining == []
    expected = (
        hourly_rate(ep.platform, ep.preset, preemptible=ep.preemptible).usd_per_hour
        + hourly_rate(job.platform, job.preset, preemptible=job.preemptible).usd_per_hour
    )
    assert report.saved_usd_per_hour == expected


def test_already_stopped_and_terminal_left_remaining_saved_zero() -> None:
    ep = _item("endpoint", "ep-stopped", state="STOPPED")
    job = _item("job", "job-done", state="COMPLETED", preemptible=True)
    endpoints = FakeEndpoints([ep])
    jobs = FakeJobs([job])

    report = run(dry_run=False, endpoints=endpoints, jobs=jobs)

    assert report.stopped == []
    assert report.cancelled == []
    assert endpoints.stopped_ids == []
    assert jobs.cancelled_ids == []
    assert report.saved_usd_per_hour == 0
    assert {i.id for i in report.remaining} == {"ep-stopped", "job-done"}


def test_missing_iam_token_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEBIUS_IAM_TOKEN", raising=False)
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "proj-1")
    with pytest.raises(NebiusJobError, match="NEBIUS_IAM_TOKEN"):
        require_credentials()


def test_missing_project_id_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEBIUS_IAM_TOKEN", "tok")
    monkeypatch.delenv("NEBIUS_PROJECT_ID", raising=False)
    with pytest.raises(NebiusJobError, match="NEBIUS_PROJECT_ID"):
        require_credentials()


def test_cli_teardown_dry_run_prints_saved_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    ep = _item("endpoint", "ep-1", name="sana", state="RUNNING")
    job = _item("job", "job-1", name="batch-0", state="QUEUED", preemptible=True)
    endpoints = FakeEndpoints([ep])
    jobs = FakeJobs([job])
    monkeypatch.setattr("santa.teardown.ports_from_env", lambda: (endpoints, jobs))
    result = CliRunner().invoke(app, ["teardown", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "dry-run" in result.output
    assert "ep-1" in result.output
    assert "job-1" in result.output
    assert endpoints.stopped_ids == []
    assert jobs.cancelled_ids == []


def test_cli_teardown_missing_token_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NEBIUS_IAM_TOKEN", raising=False)
    monkeypatch.setenv("NEBIUS_PROJECT_ID", "proj-1")
    result = CliRunner().invoke(app, ["teardown"])
    assert result.exit_code == 1
    assert "NEBIUS_IAM_TOKEN" in result.output
