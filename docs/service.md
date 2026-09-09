# CPU service (`santa-service`)

FastAPI UI + API on a regular `cpu-e2` VM in **your** project. Same `santa` package and `.env` roles as the laptop CLI.

## Local

```bash
uv sync --group service
santa-service          # HOST=0.0.0.0 PORT=8000
```

- `GET /` — form → card (shows primary vs fallback per role)
- `POST /api/cards` — one `KidProfile` → card JSON + file URLs
- `POST /api/cards/batch` — `kids[]` → cards written to the bucket
- `POST /api/publish` — laptop `--publish` default (no S3 creds on the laptop)
- `GET /wall` · `GET /api/wall` — `cards/{id}/card.png` and `cards/{id}/video.mp4`, latest run summary

Set `SANTA_SERVICE_URL=https://<your-endpoint>` so `santa publish` (without `--local`) goes through this process. `santa batch` does not call this service.

## Image

`docker/service.Dockerfile` — CPU only, `santa[service]`. Deploy as a Serverless AI CPU endpoint; pass the same env as `.env.example` (Token Factory, image URL/token, bucket `AWS_*`, optional `OPENAI_API_KEY`).
