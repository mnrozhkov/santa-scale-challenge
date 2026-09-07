"""Agent-native wrappers around ``card.py`` so ``santa/agent.py`` stays on a slide."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_ai import Tool

from santa import card as card_mod


def card_tools(
    llm: Any,
    image: Any,
    out_root: Path | str,
    *,
    on_tool: Any = print,
) -> tuple[list[Any], dict[str, Any]]:
    """Bind ``recommend_gift`` → ``write_wish`` → ``generate_image`` → ``save_card`` as sequential tools."""
    root = Path(out_root)
    state: dict[str, Any] = {"tools": []}

    def recommend_gift(name: str, age: int, wish: str = "") -> dict[str, Any]:
        on_tool("recommend_gift")
        kid = card_mod.validate_profile(name, age, wish)
        rec = card_mod.recommend_gift(kid, llm)
        state["kid"] = kid
        state["rec"] = rec
        state["tools"].append("recommend_gift")
        return rec.model_dump()

    def write_wish() -> dict[str, Any]:
        on_tool("write_wish")
        wish = card_mod.write_wish(state["kid"], state["rec"], llm)
        state["wish"] = wish
        state["tools"].append("write_wish")
        return wish.model_dump()

    def generate_image() -> str:
        on_tool("generate_image")
        png, meta = card_mod.generate_image(state["kid"], state["rec"], image)
        state["png"] = png
        state["meta"] = meta
        state["tools"].append("generate_image")
        return f"generated {len(png)} bytes"

    def save_card() -> dict[str, str]:
        on_tool("save_card")
        kid = state["kid"]
        gift = card_mod.save_card(
            kid, state["rec"], state["wish"], state["png"], state["meta"], root / kid.id
        )
        state["png_path"] = gift.png_path
        state["html_path"] = gift.html_path
        state["tools"].append("save_card")
        return {"png": gift.png_path or "", "html": gift.html_path or ""}

    tools = [
        Tool(recommend_gift, sequential=True),
        Tool(write_wish, sequential=True),
        Tool(generate_image, sequential=True),
        Tool(save_card, sequential=True),
    ]
    return tools, state
