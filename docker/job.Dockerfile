# santa-job: CUDA + diffusers Wan I2V. Also the BYOC example in AFTER_THE_WORKSHOP.md.
#
# Build (amd64, from the repo root):
#   docker build --platform linux/amd64 -f docker/job.Dockerfile -t santa-job:local .
#
# Push (participant's Container Registry):
#   docker tag santa-job:local cr.eu-north1.nebius.cloud/<registry>/santa-job:<tag>
#   docker push cr.eu-north1.nebius.cloud/<registry>/santa-job:<tag>
# Then write that tag into config/models.yaml job.image.
#
# Runtime env (set by santa.nebius_jobs): RUN_ID, CHUNK, HF_HOME=/data/models
# Bucket is FUSE-mounted at /data. Weights live at /data/models (scripts/sync_models.py).
#
# Installs santa[job]. CUDA torch comes from the pytorch cu124 index so the
# PyPI CPU wheel is not what ends up in the image.

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY santa ./santa
COPY config ./config

ENV UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    HF_HOME=/data/models \
    PATH="/app/.venv/bin:$PATH"

RUN uv python install 3.11 \
    && uv venv --python 3.11 \
    && uv sync --frozen --no-dev --extra job --group job --no-install-package torch \
    && uv pip install torch --index-url https://download.pytorch.org/whl/cu124

ENTRYPOINT ["python", "-m", "santa.job"]
