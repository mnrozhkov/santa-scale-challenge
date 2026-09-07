"""One-file MCP server: ``generate_card(name, age, wish)`` → PNG + HTML paths.

Copy-paste for Claude Code::

    claude mcp add santa -- python -m santa.mcp

Copy-paste for Cursor (``.cursor/mcp.json``)::

    {
      "mcpServers": {
        "santa": {
          "command": "python",
          "args": ["-m", "santa.mcp"]
        }
      }
    }

mcp 2.x renamed FastMCP to MCPServer; the alias below keeps the workshop name.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer as FastMCP

from santa.card import make_card, validate_profile
from santa.config import Settings

mcp = FastMCP("santa")


def generate_card(
    name: str,
    age: int,
    wish: str = "",
    *,
    settings: Settings | None = None,
    llm: Any = None,
    image: Any = None,
    out_root: Path | str | None = None,
) -> dict[str, str]:
    """Make a gift card and return paths to the PNG and HTML."""
    kid = validate_profile(name, age, wish)
    run = make_card(kid, settings or Settings.load(), llm=llm, image=image, out_root=out_root)
    return {"png": str(run.card.png_path), "html": str(run.card.html_path)}


@mcp.tool(name="generate_card")
def _mcp_generate_card(name: str, age: int, wish: str = "") -> dict[str, str]:
    """Make a personalized gift card (PNG + HTML) for this child."""
    return generate_card(name, age, wish)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
