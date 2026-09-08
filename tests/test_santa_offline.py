"""``santa … --offline`` copies bundled fallback card/mp4/summary; no adapters, no cloud."""

from __future__ import annotations

from typer.testing import CliRunner

from santa.cli import app
from santa.config import REPO_ROOT

FALLBACK = REPO_ROOT / "data" / "fallback"


def test_fallback_tree_has_cards_mp4_moods_and_summary() -> None:
    cards = FALLBACK / "cards"
    pngs = sorted(cards.glob("card-0[1-4].png"))
    htmls = sorted(cards.glob("card-0[1-4].html"))
    assert [p.name for p in pngs] == [f"card-{i:02d}.png" for i in range(1, 5)]
    assert [p.name for p in htmls] == [f"card-{i:02d}.html" for i in range(1, 5)]
    for png in pngs:
        assert png.stat().st_size > 1000
    mp4 = FALLBACK / "card.mp4"
    assert mp4.is_file() and mp4.stat().st_size > 1000
    moods = sorted((FALLBACK / "moods").glob("*.mp3"))
    assert len(moods) >= 8
    summary = FALLBACK / "run_summary.json"
    assert summary.is_file()
    import json

    data = json.loads(summary.read_text(encoding="utf-8"))
    assert data["run_id"]
    assert len(data["kids"]) == 200
    assert len(data["jobs"]) == 40
    assert "totals" in data and "savings_usd" in data
    job = data["jobs"][0]
    for key in (
        "job_id",
        "chunk",
        "platform",
        "preset",
        "preemptible",
        "state_transitions",
        "run_s",
        "cost_usd",
        "on_demand_cost_usd",
        "done",
        "skipped",
        "failed",
    ):
        assert key in job


def _spy_adapters(monkeypatch):
    calls: list[tuple] = []

    def boom(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("offline must not construct adapters")

    monkeypatch.setattr("santa.models.adapter_for", boom)
    monkeypatch.setattr("santa.card.adapter_for", boom)
    monkeypatch.setattr("santa.animate.adapter_for", boom)
    return calls


def test_card_offline_copies_fallback_without_adapters(tmp_path, monkeypatch) -> None:
    calls = _spy_adapters(monkeypatch)
    result = CliRunner().invoke(app, ["card", "--offline", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert calls == []
    pngs = list(tmp_path.rglob("card.png"))
    htmls = list(tmp_path.rglob("card.html"))
    assert len(pngs) == 1 and pngs[0].is_file()
    assert len(htmls) == 1 and htmls[0].is_file()
    assert "offline" in result.output.lower() or "fallback" in result.output.lower()
    assert pngs[0].stat().st_size == (FALLBACK / "cards" / "card-01.png").stat().st_size


def test_card_offline_picks_named_fallback(tmp_path, monkeypatch) -> None:
    _spy_adapters(monkeypatch)
    result = CliRunner().invoke(
        app, ["card", "--offline", "--name", "Nora", "--age", "10", "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    html = next(tmp_path.rglob("card.html")).read_text(encoding="utf-8")
    assert "Nora" in html
    assert 'src="card.png"' in html


def test_animate_offline_copies_mp4_without_adapters(tmp_path, monkeypatch) -> None:
    calls = _spy_adapters(monkeypatch)
    dest = tmp_path / "card.mp4"
    result = CliRunner().invoke(app, ["animate", "--offline", "--out", str(dest)])
    assert result.exit_code == 0, result.output
    assert calls == []
    assert dest.is_file() and dest.stat().st_size == (FALLBACK / "card.mp4").stat().st_size
    assert str(dest) in result.output or "offline" in result.output.lower()


def test_batch_offline_writes_summary_without_sdk(tmp_path, monkeypatch) -> None:
    calls = _spy_adapters(monkeypatch)

    def boom_store(*args, **kwargs):
        raise AssertionError("offline batch must not touch the bucket")

    def boom_jobs(*args, **kwargs):
        raise AssertionError("offline batch must not submit GPU jobs")

    monkeypatch.setattr("santa.storage.Storage.from_env", boom_store)
    monkeypatch.setattr("santa.nebius_jobs.SdkJobService.from_env", boom_jobs)
    result = CliRunner().invoke(
        app, ["batch", "--offline", "--kids", "20", "--jobs", "4", "--out", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output
    assert calls == []
    summaries = list(tmp_path.rglob("summary.json"))
    assert len(summaries) == 1
    import json

    data = json.loads(summaries[0].read_text(encoding="utf-8"))
    assert data["jobs"] and data["totals"]
    assert "summary" in result.output.lower() or "offline" in result.output.lower()
