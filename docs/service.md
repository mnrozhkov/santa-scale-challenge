# CPU service (`santa-service`)

FastAPI UI + API on a regular `cpu-e2` VM in **your** project. Same `santa` package and `.env` roles as the laptop CLI.

## Local

```bash
uv sync --group service
# First time (or after UI edits): build the prototype into santa/service/static
npm install --prefix santa/service/ui && npm run build --prefix santa/service/ui
santa-service          # HOST=0.0.0.0 PORT=8000
```

Vite-only during UI work: `npm run dev --prefix santa/service/ui` (proxies `/api` to port 8000).

- `GET /` — prototype UI (Create gift card · Animate · Gallery). Right-hand **Sim / Real** toggle defaults to **Real** (calls this process). Sim is the original graph + log simulation plus 12 bundled demo GiftCards from `data/fallback/gallery/` (`/demo/{id}/…`). Real Gallery / Animate list published Magic and Animate artifacts from `GET /api/wall` only (demo seed items are hidden). On Gallery, the right pane is a GiftCard preview (not the DAG); Sim/Real stays in that header.
- `GET /form` — original one-KidProfile HTML form
- `POST /api/cards` — one `KidProfile` → card JSON + file URLs (also writes the GiftCard to storage, or local `out/` when bucket creds are missing)
- `POST /api/cards/{id}/animate` — mood-bank `santa animate` → `cards/{id}/video.mp4`
- `POST /api/cards/batch` — `kids[]` → cards written to storage
- `GET /api/kids` — first N rows of `data/kids.csv`
- `POST /api/runs` · `GET /api/runs/{run_id}` — `santa animate_batch --no-wait`, then poll job states
- `POST /api/publish` — laptop `--publish` default (no S3 creds on the laptop)
- `GET /wall` · `GET /api/wall` — `cards/{id}/card.png` and `cards/{id}/video.mp4`, plus `items[]` for Gallery

Without bucket creds the service uses local `out/` so the laptop UI works. Set `SANTA_LOCAL_STORAGE=1` to skip S3 even if AWS keys are in `.env`. On the CPU endpoint, set `AWS_*` + `NEBIUS_BUCKET_NAME` so Gallery and Jobs share the bucket.

Set `SANTA_SERVICE_URL=https://<your-endpoint>` so `santa publish` (without `--local`) goes through this process. `santa animate_batch` from the CLI does not call this service; the UI **Let it snow** button in Real mode does, via `POST /api/runs`.

## Image

`docker/service.Dockerfile` — CPU only, `santa[service]`, plus a Node stage that builds the UI. Deploy as a Serverless AI CPU endpoint; pass the same env as `.env.example` (Token Factory, image URL/token, optional bucket `AWS_*`, optional `OPENAI_API_KEY`). Jobs from Real-mode **Let it snow** also need `NEBIUS_IAM_TOKEN`, `NEBIUS_PROJECT_ID`, `NEBIUS_BUCKET_ID`, `NEBIUS_SUBNET_ID`, and `job.image` in `config/models.yaml`.
