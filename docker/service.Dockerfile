# santa-service: FastAPI UI + /api + /wall on a regular CPU VM.
#
# Deploy (same registry as Sana / ACE-Step templates):
#   ./scripts/deploy-service.sh ship
# Image: cr.eu-north1.nebius.cloud/e00gw2b7v3pxetvpy7/santa-service:dev
# Endpoint: --platform cpu-e2 --preset 4vcpu-16gb --container-port 8000 --auth none
# Do not pass --ssh-key. Same .env roles as the laptop CLI, plus NEBIUS_IAM_TOKEN
# (minted at create; 12h) and optional SANTA_OPERATOR_TOKEN.
#
# Installs santa[service] (optional extra). Do not pull torch / job / research.

FROM node:22-slim AS ui
WORKDIR /ui
COPY santa/service/ui/package.json santa/service/ui/package-lock.json ./
RUN npm ci
COPY santa/service/ui ./
RUN npm run build

FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra service --group service --no-install-project

COPY santa ./santa
COPY config ./config
COPY data/kids.csv ./data/kids.csv
COPY --from=ui /static ./santa/service/static
RUN uv sync --frozen --no-dev --extra service --group service

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["santa-service"]
