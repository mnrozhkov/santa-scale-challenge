# santa-service: FastAPI UI + /api + /wall on a regular CPU VM.
#
# Deploy (participant's own project):
#   nebius ai endpoint create --platform cpu-e2 …
# Same .env roles as the laptop CLI. Required at runtime:
#   TOKEN_FACTORY_API_KEY
#   IMAGE_ENDPOINT_URL / IMAGE_ENDPOINT_TOKEN
#   OPENAI_API_KEY (fallback) · SANTA_FALLBACK=auto|off|only
# Optional for Gallery/batch on the endpoint:
#   NEBIUS_BUCKET_NAME · AWS_ACCESS_KEY_ID · AWS_SECRET_ACCESS_KEY · AWS_ENDPOINT_URL
# Optional: VIDEO_ENDPOINT_URL/TOKEN, AUDIO_ENDPOINT_URL/TOKEN, NEBIUS_IAM_TOKEN (Jobs).
#
# Installs santa[service] (optional extra). Do not pull torch / job / research.

FROM node:22-slim AS ui
WORKDIR /ui
COPY santa/service/ui ./
RUN npm install && npm run build

FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY santa ./santa
COPY config ./config
COPY data/kids.csv ./data/kids.csv
COPY --from=ui /static ./santa/service/static

RUN uv sync --frozen --no-dev --extra service --group service

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["santa-service"]
