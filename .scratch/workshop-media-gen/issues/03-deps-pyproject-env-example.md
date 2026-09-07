# 03: Dependency split, `pyproject`, `.env.example`, `.gitignore`

**What to build:** `uv sync` on a participant laptop installs only what the CLI needs, in well under a minute on conference wifi. Heavy research and service/job deps live in optional groups. The repo cannot leak `.env`.

**Blocked by:** 01

**Status:** ready-for-human

- [x] Core deps: `openai pydantic pydantic-settings pyyaml typer rich requests python-dotenv pillow jinja2 imageio-ffmpeg boto3 nebius pydantic-ai`
- [x] Groups: `service` (fastapi, uvicorn, jinja2, python-multipart) · `job` (torch, diffusers, transformers, accelerate, imageio-ffmpeg) · `research` (mlflow, pandas, google-*, aiohttp) · `dev`
- [x] `requires-python = ">=3.11"`; real URLs; description/keywords match the workshop; `santa_demo` wheel target replaced by `santa`
- [x] `.env.example`: Steps 0–5/7 block · fallbacks block (`OPENAI_API_KEY`, `SANTA_FALLBACK`) · batch/service/publish block · alternate `llm` models commented
- [x] `.gitignore`: `.env`, `*.pkg`, `data/out/`, `santa/out/`; `_DEV/AWSCLIV2.pkg` removed from the tree
- [x] `uv sync` on a clean checkout: core install ≤ 60 s from warm cache; documented timing in README

## Comments

- Kept `truststore` in core (not in the D15 list) because `santa.cli` injects the OS cert store for laptop TLS.
- Hatch wheel `packages = ["santa", "santa_demo"]` and `[project.scripts] santa-demo` stay so `tests/test_demo_*.py` still install. `santa` is the primary package (issue 01); dropping `santa_demo` would break the presenter app until issue 04.
- `dev` uses `{include-group = "service"}` so `uv sync --group dev` has fastapi for demo tests. `job` / `research` stay optional. `[tool.uv] default-groups = []` so a plain `uv sync` is laptop-core only.
- `_DEV/AWSCLIV2.pkg` was already untracked (`_DEV/*`); `git ls-files` has no `*.pkg`. Added `*.pkg` anyway. Did not delete local `_DEV/`.
- Warm-cache `uv sync` (clean `.venv`) was ~1 s on this machine; README documents that.
