"""Pydantic AI card agent on Token Factory. Fits on a slide."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider

from santa.card_tools import card_tools
from santa.config import ConfigError, Settings
from santa.models import adapter_for


def run_agent(
    request: str,
    *,
    settings: Any = None,
    model: Any = None,
    llm: Any = None,
    image: Any = None,
    out_root: Any = None,
) -> Path:
    s = settings or Settings.load()
    tools, state = card_tools(
        llm or adapter_for("llm", s), image or adapter_for("image", s), Path(out_root or "out")
    )
    if model is None:
        r = s.role("llm")
        if not r.model:
            raise ConfigError("llm role has no model in config/models.yaml.")
        model = OpenAIModel(
            r.model,
            provider=OpenAIProvider(base_url=r.v1, api_key=r.api_key),
        )
    Agent(model, tools=tools, instructions="Use the four card tools in order.").run_sync(request)
    return Path(state["png_path"])
