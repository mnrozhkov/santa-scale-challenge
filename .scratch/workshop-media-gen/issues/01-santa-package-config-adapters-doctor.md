# 01: `santa` package: config, schemas, LLM + image adapters, `doctor`

**What to build:** A participant clones the repo, runs `uv sync`, copies `.env.example` → `.env`, pastes their Token Factory key and endpoint URL/token, and `santa doctor` tells them in one screen what works and what to fix. Every model is named in `config/models.yaml` (roles `llm`, `image`, `video`, `audio`, each with a `fallback:` — OpenAI by default — plus `job:`), never in code. If an endpoint is not configured or fails, the fallback answers and the metrics say so. `santa_demo` is folded into `santa/`; `prototype/` is left untouched.

**Blocked by:** None (can start immediately)

**Status:** ready-for-human

- [x] `santa/config.py` loads `config/models.yaml` + `.env` into a typed `Settings`; `role(name)` and `fallback(name)`; `SANTA_FALLBACK=auto|off|only`
- [x] `santa/schemas.py`, `santa/prompts.py` lifted (copied) from `prototype/src`; no `sys.path` hack; `santa_demo/proto.py` gone
- [x] `santa/models.py`: `openai_chat` (Token Factory / OpenAI) and `openai_images` (Sana / `gpt-image-1`) adapters; `adapter_for(role)` returns a `Resilient` wrapper that switches to the fallback on `AdapterError` or when the primary is unconfigured; Recraft/TF-image branches dropped
- [x] `santa/cli.py` (typer) with `doctor`; `[project.scripts] santa = "santa.cli:app"`
- [x] `santa doctor` checks: `.env` · Token Factory `/v1/models` · each endpoint `/v1/models` (RUNNING ≠ ready) · each fallback (OpenAI `/v1/models`, local tracks dir) · service URL, IAM token, project, bucket presence · a failed primary with a working fallback is WARN, not FAIL · exit non-zero on any required failure
- [x] Tests: settings from yaml+env, fallback resolution + policy, adapter request shapes against fixtures, `Resilient` switching, doctor with fakes

## Comments

Implemented on `serverless`. `santa` imports schemas/prompts/adapters with no `sys.path` hack. `santa_demo/proto.py` is deleted; `santa_demo.session` still inserts `prototype/` on `sys.path` so the presenter app can call `process_kid` until issues 04/15 fold or remove it. Folding `santa_demo/` into `santa/service/` is issue 04, not this ticket.
