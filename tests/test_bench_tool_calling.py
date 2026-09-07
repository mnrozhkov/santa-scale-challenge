"""Scoring helpers for scripts/bench_tool_calling.py — fixtures only, no live models."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _bench():
    path = ROOT / "scripts" / "bench_tool_calling.py"
    spec = importlib.util.spec_from_file_location("bench_tool_calling", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_tool_order_and_success_literals() -> None:
    b = _bench()
    order = ["recommend_gift", "write_wish", "generate_image", "save_card"]
    assert b.tool_order_ok(order) is True
    assert b.tool_order_ok(["write_wish", "recommend_gift", "generate_image", "save_card"]) is False
    assert b.success(error=None, png_exists=True, tools=order) is True
    assert b.success(error="boom", png_exists=True, tools=order) is False
    assert b.success(error=None, png_exists=False, tools=order) is False


def test_p50_and_cost_literals() -> None:
    b = _bench()
    assert b.p50([10.0, 30.0, 20.0]) == 20.0
    assert b.p50([1.0, 2.0, 3.0, 4.0]) == 2.5
    assert b.p50([]) == 0.0
    assert b.cost_usd(1_000_000, 2_000_000) == 1.35


def test_main_without_key_writes_not_run(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("TOKEN_FACTORY_API_KEY", raising=False)
    b = _bench()
    dest = tmp_path / "tool_calling.md"
    assert b.main(dest=dest, env={}) == 0
    text = dest.read_text(encoding="utf-8")
    assert "not run" in text.lower()
    assert "openai/gpt-oss-120b" in text
