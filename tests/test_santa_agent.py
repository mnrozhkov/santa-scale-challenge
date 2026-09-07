"""Agent tools + MCP card shim: injected fakes, no Token Factory or image HTTP."""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import FunctionModel

from santa.agent import run_agent
from santa.config import Settings

NOENV = Path("/nonexistent")
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
TOOL_ORDER = ("recommend_gift", "write_wish", "generate_image", "save_card")


class FakeLLM:
    used_fallback = False
    model_version = "openai/gpt-oss-120b@https://tf.example/v1"
    last_metrics = {"latency_ms": 12, "fallback": False}
    cfg = SimpleNamespace(
        model="openai/gpt-oss-120b",
        base_url="https://tf.example",
        is_fallback=False,
        label="llm",
    )

    def generate_json(self, prompt: str, **kw):
        if "rationale" in prompt:
            return {"gifts": ["telescope", "star chart"], "rationale": "loves the sky"}
        return {
            "wish": "Dear Alex, may your telescope find a bright new star. Merry Christmas!",
            "mood": "warm",
        }


class FakeImage:
    used_fallback = False
    model_version = "sana@https://img.example"
    last_metrics = {"latency_ms": 40, "fallback": False}
    cfg = SimpleNamespace(model="sana", base_url="https://img.example/", is_fallback=False)

    def generate(self, prompt: str, *, seed=None) -> bytes:
        return PNG_1PX


def _scripted_card_model(messages, info) -> ModelResponse:
    done: list[str] = []
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, ToolReturnPart):
                    done.append(part.tool_name)
    if "recommend_gift" not in done:
        return ModelResponse(
            parts=[ToolCallPart("recommend_gift", {"name": "Alex", "age": 7, "wish": "telescope"})]
        )
    if "write_wish" not in done:
        return ModelResponse(parts=[ToolCallPart("write_wish", {})])
    if "generate_image" not in done:
        return ModelResponse(parts=[ToolCallPart("generate_image", {})])
    if "save_card" not in done:
        return ModelResponse(parts=[ToolCallPart("save_card", {})])
    return ModelResponse(parts=[TextPart("card ready")])


def test_run_agent_invokes_card_tools_in_order(tmp_path, capsys) -> None:
    png = run_agent(
        "make a card for a 7-year-old who wants a telescope",
        settings=Settings.load(env_file=NOENV),
        model=FunctionModel(_scripted_card_model),
        llm=FakeLLM(),
        image=FakeImage(),
        out_root=tmp_path,
    )
    printed = [line.strip() for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert printed == list(TOOL_ORDER)
    assert png.is_file()
    assert png.suffix == ".png"
    assert png.with_name("card.html").is_file()


def test_mcp_generate_card_returns_png_and_html_paths(tmp_path) -> None:
    from santa.mcp import generate_card

    result = generate_card(
        "Alex",
        7,
        "telescope",
        settings=Settings.load(env_file=NOENV),
        llm=FakeLLM(),
        image=FakeImage(),
        out_root=tmp_path,
    )
    png = Path(result["png"])
    html = Path(result["html"])
    assert png.is_file()
    assert html.is_file()
    assert png.suffix == ".png"
    assert html.suffix == ".html"


def test_agent_cli_prints_png_path(tmp_path, monkeypatch) -> None:
    from typer.testing import CliRunner

    from santa.cli import app

    png = tmp_path / "card.png"
    png.write_bytes(PNG_1PX)

    def fake_run(request: str, **kw):
        assert "telescope" in request
        return png

    monkeypatch.setattr("santa.agent.run_agent", fake_run)
    result = CliRunner().invoke(
        app, ["agent", "make a card for a 7-year-old who wants a telescope"]
    )
    assert result.exit_code == 0, result.output
    assert "No such command" not in result.output
    assert "Wrote" in result.output
    assert "card.png" in result.output
