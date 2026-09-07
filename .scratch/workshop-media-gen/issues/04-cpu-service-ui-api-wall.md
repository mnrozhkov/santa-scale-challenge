# 04: `santa-service` — CPU endpoint with UI, `/api/cards`, `/api/cards/batch`, `/api/publish`, `/wall`

**What to build:** The presenter app becomes `santa/service/` and runs as a Serverless CPU endpoint (regular VM) in the participant's project, configured by the same `.env` roles. The UI form makes a card; `santa batch` calls `POST /api/cards/batch` (when `SANTA_SERVICE_URL` is set) to fan out card generation and write `cards/` to the bucket. `/wall` shows cards, videos and the latest run summary from the bucket.

**Blocked by:** 02

**Status:** ready-for-human

- [x] `santa_demo/` → `santa/service/` (FastAPI, templates); old S2/S3 buttons removed (video is `animate`, batch is Jobs)
- [x] `POST /api/cards` (profile) → card json + URLs; UI shows which model answered (primary/fallback)
- [x] `POST /api/cards/batch` (kids[]) → thread pool over the `image` role, writes `cards/{id}.png|html|json` to the bucket via `storage.py`, returns ids + failures
- [x] `POST /api/publish` (multipart png/mp4) → bucket; `GET /wall` + `GET /api/wall` list `cards/`, `videos/`, latest `runs/*/summary.json`
- [x] `docker/service.Dockerfile` (python:3.11-slim + `santa[service]`); deploy notes: `nebius ai endpoint create --platform cpu-e2 …`; env: role URLs/tokens, bucket creds
- [x] Tests: routes call the session/fakes; batch endpoint chunks and records failures without aborting

## Comments

- On `serverless` via `issue/04-cpu-service` (`7eb5c8d`), merged in `4230041`.
- `POST /api/cards` URLs are `/cards/{id}.png|.html` (per kid, not the last-run slot). `/wall` renders bucket png/mp4 via `/media/…`. Latest summary uses `list_with_mtime` (upload order / S3 LastModified), not lexicographic `max()`.
- Batch “chunks” = thread pool over `kids[]` with per-kid failures (GPU job chunks are issue 09). Dockerfile: `uv sync --frozen --no-dev --extra service --group service`. UI still POSTs `/generate`. `conftest.py` still inserts `prototype/` (issue 15). Recraft URL hard-fail kept (D2).
