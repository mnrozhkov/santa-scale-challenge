# 06: Step 5 — `santa agent` (Pydantic AI, ≤40 lines) + `santa-mcp` shim + tool-calling bench

**What to build:** A participant runs `santa agent "make a card for a 7-year-old who wants a telescope"`; a Pydantic AI agent on Token Factory calls `recommend_gift`, `write_wish`, `generate_image` (their endpoint), `save_card`, and the card appears. `agent.py` fits on a slide. If the model's tool calling is flaky, the same tools are exposed by a one-file MCP server so Claude Code / Cursor can call their endpoint instead.

**Blocked by:** 02

**Status:** ready-for-human

- [x] `scripts/bench_tool_calling.py`: runs the 4-tool card task ×10 on `zai-org/GLM-5.3-Flash`, `nvidia/Nemotron-3_5-Lightning`, `deepseek-ai/DeepSeek-V4-Flash-0731`, `openai/gpt-oss-120b`; reports success rate, tool-order correctness, p50 latency, cost; writes `data/bench/tool_calling.md`
- [ ] Winner set as `roles.llm.model` in `config/models.yaml`; two runners-up commented in `.env.example`
- [x] `santa/agent.py` ≤40 lines: `Agent(OpenAIModel(provider=TF), tools=[…from card.py])`, streaming tool trace printed
- [x] `santa/mcp.py`: FastMCP server exposing `generate_card(name, age, wish)`; README snippets for Claude Code (`claude mcp add`) and Cursor (`.cursor/mcp.json`)
- [x] Tests: scripted fake model → expected tool sequence; MCP tool returns card paths

## Comments

- On `serverless` via `issue/06-agent-mcp` (`7fbf94f`), merged in `4230041`. Wrappers live in `santa/card_tools.py` so `santa/agent.py` stays ≤40 lines.
- Bench was **not run live** (no Token Factory in CI). `roles.llm.model` stays `openai/gpt-oss-120b`; GLM / Nemotron / DeepSeek remain commented in `config/models.yaml`. `.env.example` was not edited (already lists those names from issue 03).
- Agent uses pydantic-ai `OpenAIModel` (subclass of `OpenAIChatModel`) with Token Factory via `OpenAIProvider`. Tool names print via `on_tool=print` as each tool runs (`run_sync`; FunctionModel tests do not stream).
- MCP copy-paste lives in `santa/mcp.py` and a short README section. mcp 2.x: `MCPServer` aliased as `FastMCP`. Checkbox tool is `generate_card`, not the four inner tools.
