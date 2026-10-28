# CPU service (`santa-service`)

FastAPI UI + API on a regular `cpu-e2` VM in **your** project. Same `santa` package and `.env` roles as the laptop CLI.

This is the presenter **kiosk**: one public HTTPS URL, QR on a screen, phones and laptops hit the same UI. GPU endpoints (Sana / Wan) stay token-protected in container env. QR guests never see those tokens.

## Local

```bash
uv sync --group service
# First time (or after UI edits): build the prototype into santa/service/static
npm install --prefix santa/service/ui && npm run build --prefix santa/service/ui
santa-service          # HOST=0.0.0.0 PORT=8000
```

Vite-only during UI work: `npm run dev --prefix santa/service/ui` (proxies `/api` to port 8000). `ship` is only for the public QR URL.

## Deploy loop

Nebius CLI has no `endpoint update`. Keep a stable HTTPS URL by creating once, then **build → push the same tag → restart**.

```bash
./scripts/deploy-service.sh ship    # build && push && restart
./scripts/deploy-service.sh url     # managed https:// for the QR
```

Image (same registry as the Sana / ACE-Step templates):

```text
cr.eu-north1.nebius.cloud/e00gw2b7v3pxetvpy7/santa-service:dev
```

`up` creates the endpoint if missing:

- `--platform cpu-e2 --preset 4vcpu-16gb`
- `--container-port 8000`
- **`--auth none`** (QR works with no access token)
- `--env` from `.env` (roles, bucket, Jobs). `NEBIUS_IAM_TOKEN` is minted with `nebius iam get-access-token` at create time.
- No `--ssh-key` (that would let anyone with the key dump container env)

If restart keeps a stale image, `ship` falls back to stop/delete/create with the same `--name` (`./scripts/deploy-service.sh recreate`). The URL may change in that case — refresh the QR.

`santa teardown` still stops this endpoint with the rest of your Serverless AI resources.

## Guest vs operator

The gateway is open (`--auth none`). App policy:

| Action | Guest (QR) | Operator (`SANTA_OPERATOR_TOKEN`) |
|---|---|---|
| Create GiftCard | Real | Real or Sim |
| Gallery | Real | Real |
| Animate / Let it snow | 403 — UI stays on Sim | Real if Sim/Real = Real |
| Agent (evaluate-before-escalate) | 403 — UI stays on Sim | Real if Sim/Real = Real |

Unlock: open `https://<endpoint>/?op=<token>` once. The UI stores it in `sessionStorage`, strips `?op=` from the address bar, and sends `X-Santa-Operator`. The QR encodes **origin only**.

`GET /api/access` returns `{ "role": "guest" | "operator" }` and never the token.

## Jobs IAM (12h)

The CPU endpoint fans out GPU Jobs with the same `NEBIUS_IAM_TOKEN` the laptop CLI uses. It is a **user** Bearer token valid **12 hours**. Remint = recreate the endpoint (no `endpoint update`). Fine for a one-day demo; Jobs fail until you `ship` / `recreate` with a fresh token.

QR guests cannot read it from the browser if the public JSON/error/`/media` rules hold. Anyone who steals the token can call `api.nebius.cloud` as you for ~12h. Do not pass `--ssh-key`.

## Public JSON

The kiosk is `--auth none`, so DevTools is public. Responses strip role endpoint URLs, tokens, and env names. HTTP errors are generic (`Card generation failed`). `/media` serves PNG/MP4/HTML only (`card.json` is 404). `/docs` is disabled.

## Routes

- `GET /` — kiosk UI (Create · Animate · Agent · Gallery). Header **QR** opens a modal; `/qr` is a projector page (origin only).
- `GET /s/{id}` — share page with absolute `og:image` / Twitter tags (no gateway token).
- `GET /form` — original one-KidProfile HTML form
- `POST /api/cards` — one `KidProfile` → card JSON + file URLs (also writes the GiftCard to storage, or local `out/` when bucket creds are missing)
- `POST /api/cards/{id}/animate` — mood-bank `santa animate` → `cards/{id}/video.mp4` (operator)
- `POST /api/cards/batch` — `kids[]` → cards written to storage
- `GET /api/kids` — first N rows of `data/kids.csv`
- `POST /api/agent/stream` — Experiment B `run_kids` SSE (operator); body `{ kids: [KidProfile] }` (kiosk Agent tab: one kid) or `{ limit }` + optional `budget_usd` / `publish`. Complete event includes `png_url` / `video_url` per kid.
- `POST /api/runs` · `GET /api/runs/{run_id}` — `santa animate_batch --no-wait`, then poll job states (operator)
- `POST /api/publish` — laptop `--publish` default (no S3 creds on the laptop)
- `GET /wall` · `GET /api/wall` — `cards/{id}/card.png` and `cards/{id}/video.mp4`, plus `items[]` for Gallery

Without bucket creds the service uses local `out/` so the laptop UI works. Set `SANTA_LOCAL_STORAGE=1` to skip S3 even if AWS keys are in `.env`. On the CPU endpoint, set `AWS_*` + `NEBIUS_BUCKET_NAME` so Gallery and Jobs share the bucket.

Set `SANTA_SERVICE_URL=https://<your-endpoint>` so `santa publish` (without `--local`) goes through this process. `santa animate_batch` from the CLI does not call this service; the UI **Let it snow** button in Real mode does, via `POST /api/runs`.

## Image

`docker/service.Dockerfile` — CPU only, `santa[service]`, plus a Node stage that builds the UI. Layer cache: `uv sync` runs before copying Python/UI sources so code edits do not reinstall deps. Pass the same env as `.env.example` (Token Factory, image URL/token, optional bucket `AWS_*`, optional `OPENAI_API_KEY`, `SANTA_OPERATOR_TOKEN`). Jobs from Real-mode **Let it snow** also need `NEBIUS_IAM_TOKEN`, `NEBIUS_PROJECT_ID`, `NEBIUS_BUCKET_ID`, `NEBIUS_SUBNET_ID`, and `job.image` in `config/models.yaml`.
