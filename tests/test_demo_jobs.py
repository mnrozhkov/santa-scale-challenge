"""S3 — four GPU Jobs on the demo session seam."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.data_scheme import KidProfile

from santa_demo.fallbacks import require_four_fallbacks
from santa_demo.jobs import JobResult
from santa_demo.session import DemoSession
from tests.test_demo_session import _env, _fake_runner_factory


class FakeJobRunner:
    def __init__(self) -> None:
        self.submitted: list[list[Path]] = []

    def submit(self, png_paths: list[Path]) -> list[JobResult]:
        self.submitted.append(list(png_paths))
        results = []
        for i, png in enumerate(png_paths):
            state = "FAILED" if i == 1 else "COMPLETED"
            results.append(
                JobResult(
                    id=f"job-{i}",
                    state=state,
                    png_path=str(png),
                    mp4_url=None if state == "FAILED" else f"s3://bucket/{png.stem}.mp4",
                    error="preempted" if state == "FAILED" else None,
                )
            )
        return results

    def poll(self, jobs: list[JobResult]) -> list[JobResult]:
        return jobs


def _session(
    monkeypatch, tmp_path: Path, runner: FakeJobRunner, with_live: bool = False
) -> DemoSession:
    _env(monkeypatch)
    image = SimpleNamespace(base_url="https://sana.example/v1")
    llm = SimpleNamespace(base_url="https://api.tokenfactory.nebius.com/v1")
    session = DemoSession.from_env(
        llm_client=llm,
        image_client=image,
        card_runner=_fake_runner_factory([]),
        job_runner=runner,
        output_dir=tmp_path,
    )
    if with_live:
        live = tmp_path / "live.png"
        live.write_bytes(b"live-png")
        card = session.generate_card(KidProfile(name="Emma", age=7, wishlist=["stars"]))
        card.png_path = str(live)
        session.last_card = card
    return session


def test_batch_submits_four_fallbacks(monkeypatch, tmp_path):
    runner = FakeJobRunner()
    session = _session(monkeypatch, tmp_path, runner)
    jobs = session.batch_videos(include_last=False)
    assert len(jobs) == 4
    assert runner.submitted[0] == require_four_fallbacks()


def test_batch_include_last_swaps_live_png(monkeypatch, tmp_path):
    runner = FakeJobRunner()
    session = _session(monkeypatch, tmp_path, runner, with_live=True)
    jobs = session.batch_videos(include_last=True)
    assert Path(jobs[0].png_path).name == "live.png"
    assert len(jobs) == 4
    fallbacks = require_four_fallbacks()
    assert [Path(j.png_path) for j in jobs[1:]] == fallbacks[:3]


def test_batch_include_last_ignored_without_live_card(monkeypatch, tmp_path):
    runner = FakeJobRunner()
    session = _session(monkeypatch, tmp_path, runner, with_live=False)
    jobs = session.batch_videos(include_last=True)
    assert [Path(j.png_path) for j in jobs] == require_four_fallbacks()


def test_batch_partial_failure_keeps_other_results(monkeypatch, tmp_path):
    runner = FakeJobRunner()
    session = _session(monkeypatch, tmp_path, runner)
    jobs = session.batch_videos()
    assert jobs[1].state == "FAILED"
    assert jobs[1].error == "preempted"
    completed = [j for j in jobs if j.state == "COMPLETED"]
    assert len(completed) == 3
    assert all(j.mp4_url for j in completed)
