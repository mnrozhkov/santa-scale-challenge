# santa-service: FastAPI UI + /api + /wall on a regular CPU VM.
#
# Deploy (participant's own project):
#   nebius ai endpoint create --platform cpu-e2 …
# Same .env roles as the laptop CLI. Required at runtime:
#   TOKEN_FACTORY_API_KEY
#   IMAGE_ENDPOINT_URL / IMAGE_ENDPOINT_TOKEN
#   OPENAI_API_KEY (fallback) · SANTA_FALLBACK=auto|off|only
#   NEBIUS_BUCKET_NAME · AWS_ACCESS_KEY_ID · AWS_SECRET_ACCESS_KEY · AWS_ENDPOINT_URL
# Optional: VIDEO_ENDPOINT_URL/TOKEN, AUDIO_ENDPOINT_URL/TOKEN (not used by this image).
#
# Installs santa[service] (optional extra). Do not pull torch / job / research.

FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY santa ./santa
COPY config ./config

RUN uv sync --frozen --no-dev --extra service --group service

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["santa-service"]
