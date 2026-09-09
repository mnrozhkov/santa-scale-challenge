#!/usr/bin/env python3
"""Bench the 4-tool card agent on Token Factory chat models.

Runs the card task ×10 on GLM / Nemotron / DeepSeek / gpt-oss. Reports success
rate, tool-order correctness, p50 latency, and cost. Writes
``data/bench/tool_calling.md``.

Inner gift/wish/image adapters are fakes so this measures *tool calling*, not
Sana. Token prices below are documented placeholders (USD / 1M tokens), not
scraped at runtime.

If ``TOKEN_FACTORY_API_KEY`` is unset, writes a "not run" report and exits 0
so CI stays green. Put the printed winner into ``config/models.yaml``
``roles.llm.model`` — this script never invents a live winner.
"""

from __future__ import annotations

import base64
import os
import statistics
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from santa.config import REPO_ROOT

MODELS = (
    "zai-org/GLM-5.3-Flash",
    "nvidia/Nemotron-3_5-Lightning",
    "deepseek-ai/DeepSeek-V4-Flash-0731",
    "openai/gpt-oss-120b",
)
EXPECTED_TOOLS = ("recommend_gift", "write_wish", "generate_image", "save_card")
PROMPT = "make a card for a 7-year-old who wants a telescope"
N_RUNS = 10
# Placeholder Token Factory rates (USD per 1M tokens). Replace from the console.
INPUT_USD_PER_MILLION = 0.15
OUTPUT_USD_PER_MILLION = 0.60
DEFAULT_DEST = REPO_ROOT / "data" / "bench" / "tool_calling.md"
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


class _FakeLLM:
    model_version = "bench-fake-llm"
    last_metrics = {"latency_ms": 1, "fallback": False}
    cfg = SimpleNamespace(model="fake", base_url="https://tf.example", is_fallback=False)

    def generate_json(self, prompt: str, **kw: Any) -> dict[str, Any]:
        if "rationale" in prompt:
            return {"gifts": ["telescope", "star chart"], "rationale": "loves the sky"}
        return {
            "wish": "Dear Alex, may your telescope find a bright new star. Merry Christmas!",
            "mood": "warm",
        }


class _FakeImage:
    model_version = "bench-fake-image"
    last_metrics = {"latency_ms": 1, "fallback": False}
    cfg = SimpleNamespace(model="fake", base_url="https://img.example/", is_fallback=False)

    def generate(self, prompt: str, *, seed: int | None = None) -> bytes:
        return PNG_1PX


def tool_order_ok(tools: Sequence[str], expected: Sequence[str] = EXPECTED_TOOLS) -> bool:
    filtered = [name for name in tools if name in expected]
    return filtered == list(expected)


def success(*, error: str | None, png_exists: bool, tools: Sequence[str]) -> bool:
    return error is None and png_exists and tool_order_ok(tools)


def p50(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return float(statistics.median(values))


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return round(
        input_tokens / 1e6 * INPUT_USD_PER_MILLION + output_tokens / 1e6 * OUTPUT_USD_PER_MILLION,
        6,
    )


def not_run_report() -> str:
    return (
        "# Tool-calling bench\n\n"
        "Not run: `TOKEN_FACTORY_API_KEY` is not set.\n\n"
        "Keep `openai/gpt-oss-120b` as `roles.llm.model` in `config/models.yaml` "
        "until this script is run against Token Factory. It will print the winner "
        "to put in yaml (do not invent one).\n"
    )


def summarize(model: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows) or 1
    return {
        "model": model,
        "success_rate": sum(1 for r in rows if r["success"]) / n,
        "order_rate": sum(1 for r in rows if r["order_ok"]) / n,
        "p50_ms": p50([float(r["ms"]) for r in rows]),
        "cost": round(sum(float(r["cost"]) for r in rows), 6),
    }


def pick_winner(scores: Sequence[Mapping[str, Any]]) -> str | None:
    ok = [s for s in scores if float(s["success_rate"]) > 0]
    if not ok:
        return None
    ranked = sorted(ok, key=lambda s: (-float(s["success_rate"]), float(s["p50_ms"])))
    return str(ranked[0]["model"])


def render_markdown(scores: Sequence[Mapping[str, Any]], winner: str | None) -> str:
    lines = [
        "# Tool-calling bench",
        "",
        f"Task: `{PROMPT}` ×{N_RUNS} per model. Inner llm/image adapters are fakes.",
        f"Cost uses placeholder Token Factory rates "
        f"${INPUT_USD_PER_MILLION}/M input and ${OUTPUT_USD_PER_MILLION}/M output.",
        "",
        "| model | success | tool-order | p50 ms | cost USD |",
        "| --- | --- | --- | --- | --- |",
    ]
    for s in scores:
        lines.append(
            f"| `{s['model']}` | {s['success_rate']:.0%} | {s['order_rate']:.0%} | "
            f"{s['p50_ms']:.0f} | {s['cost']:.4f} |"
        )
    lines.append("")
    if winner:
        lines.append(
            f"**Winner:** `{winner}` — set `roles.llm.model` in `config/models.yaml` "
            "to this id. Comment the two runners-up."
        )
    else:
        lines.append(
            "No successful runs. Keep `openai/gpt-oss-120b` as the placeholder in "
            "`config/models.yaml`."
        )
    lines.append("")
    return "\n".join(lines)


def _run_one(model_name: str, out_root: Path) -> dict[str, Any]:
    from pydantic_ai import Agent
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    from santa.card_tools import card_tools
    from santa.config import Settings

    settings = Settings.load()
    role = settings.role("llm")
    model = OpenAIChatModel(
        model_name, provider=OpenAIProvider(base_url=role.v1, api_key=role.api_key)
    )
    called: list[str] = []
    tools, state = card_tools(_FakeLLM(), _FakeImage(), out_root, on_tool=called.append)
    t0 = time.perf_counter()
    error: str | None = None
    usage_in = 0
    usage_out = 0
    try:
        result = Agent(
            model,
            tools=tools,
            instructions="Call recommend_gift, write_wish, generate_image, save_card in that order.",
        ).run_sync(PROMPT)
        usage = result.usage()
        usage_in = int(usage.input_tokens or 0)
        usage_out = int(usage.output_tokens or 0)
    except Exception as exc:
        error = str(exc)
    ms = (time.perf_counter() - t0) * 1000
    png = Path(str(state.get("png_path") or ""))
    png_exists = png.is_file()
    return {
        "tools": called,
        "png_exists": png_exists,
        "error": error,
        "ms": ms,
        "success": success(error=error, png_exists=png_exists, tools=called),
        "order_ok": tool_order_ok(called),
        "cost": cost_usd(usage_in, usage_out),
    }


def main(
    dest: Path | str | None = None, *, env: Mapping[str, str] | None = None, runs: int = N_RUNS
) -> int:
    dest_path = Path(dest or DEFAULT_DEST)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if env is None:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env", override=False)
        env = os.environ
    if not (env.get("TOKEN_FACTORY_API_KEY") or "").strip():
        text = not_run_report()
        dest_path.write_text(text, encoding="utf-8")
        print(text)
        print("Keep openai/gpt-oss-120b in config/models.yaml (bench was not run).")
        return 0

    import tempfile

    scores: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="santa-bench-") as tmp:
        root = Path(tmp)
        for model_name in MODELS:
            rows = [
                _run_one(model_name, root / model_name.replace("/", "_") / str(i))
                for i in range(runs)
            ]
            scores.append(summarize(model_name, rows))
            print(
                f"{model_name}: success={scores[-1]['success_rate']:.0%} p50={scores[-1]['p50_ms']:.0f}ms"
            )
    winner = pick_winner(scores)
    text = render_markdown(scores, winner)
    dest_path.write_text(text, encoding="utf-8")
    print(text)
    if winner:
        print(f"Put this in config/models.yaml roles.llm.model: {winner}")
    else:
        print("Keep openai/gpt-oss-120b in config/models.yaml (no successful runs).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
