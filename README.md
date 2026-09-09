# 🎄 Santa Scale Challenge

**AI Orchestration & Agentic Deployment on Nebius Infrastructure**

A reference implementation for orchestrating LLMs and image, video, and audio models to create personalized gift cards at scale using Nebius Serverless AI, Token Factory, GPU Jobs, and MLflow.

## 🗂️ Repository Structure

```
santa-scale-challenge/
├── santa/                 # One package: CLI, CPU service, GPU job
│   ├── cli.py             # santa doctor | card | agent | batch | animate | teardown
│   ├── card.py            # Gift rec + wish + illustration → PNG/HTML
│   ├── animate.py         # Wan I2V + music → card.mp4
│   ├── batch.py           # Cards then K GPU Jobs
│   ├── service/           # FastAPI UI + /wall
│   └── job.py             # GPU Job entrypoint
├── config/
│   ├── models.yaml        # Roles (llm, image, video, audio) + job spec
│   └── prompts.yaml       # Motion / mood prompts
├── notebooks/             # Playgrounds + research evals
├── data/
│   ├── kids.csv           # 200 profiles for santa batch
│   └── fallback/          # Offline cards, mp4, moods, run summary
├── docker/
│   ├── service.Dockerfile # CPU UI / API
│   └── job.Dockerfile     # BYOC GPU Job image
├── skills/                # Echo prompts + Serverless AI skill
├── scripts/               # Mood bank, model sync, teardown, benches
├── tests/
└── docs/                  # Service + job contracts; domain glossary
```

Ops: [docs/service.md](docs/service.md) (CPU UI / `/wall`) · [docs/job.md](docs/job.md) (GPU Jobs). Domain language: [CONTEXT.md](CONTEXT.md).

## 🚀 Installation

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

### Setup

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone repository
git clone https://github.com/mnrozhkov/santa-scale-challenge
cd santa-scale-challenge

# Create virtual environment
uv python install 3.12
uv venv --python 3.12
source .venv/bin/activate

# Install dependencies (laptop CLI only)
uv sync

# Optional groups
uv sync --group service    # FastAPI CPU UI (santa-service)
uv sync --group dev        # Jupyter, pytest, linters
uv sync --group research   # MLflow eval notebooks
```

`uv sync` with no groups is the laptop core: `santa doctor`, `santa card`, `santa agent`.

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the repository root (copy `.env.example` and fill in your keys). Roles are named in `config/models.yaml`; secrets and URLs live in `.env`.

```bash
# Token Factory (llm role) — at least one LLM key required
TOKEN_FACTORY_API_KEY=your_token_factory_key

# Fallback for llm / image / video when a primary endpoint is missing or fails
OPENAI_API_KEY=your_openai_key
SANTA_FALLBACK=auto          # auto | off | only

# Image endpoint (Sana) — required for a live card
IMAGE_ENDPOINT_URL=https://your-sana-endpoint
IMAGE_ENDPOINT_TOKEN=your_endpoint_token

# Video endpoint (Wan I2V) — santa animate
VIDEO_ENDPOINT_URL=https://your-wan-endpoint
VIDEO_ENDPOINT_TOKEN=your_endpoint_token

# Audio endpoint (ACE-Step) — or use --mood-bank
AUDIO_ENDPOINT_URL=https://your-acestep-endpoint
AUDIO_ENDPOINT_TOKEN=your_endpoint_token

# CPU service (optional; santa batch / santa publish without --local)
SANTA_SERVICE_URL=https://your-cpu-service

# Object Storage (publish + santa batch)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_ENDPOINT_URL=https://storage.eu-north1.nebius.cloud
NEBIUS_BUCKET_NAME=your-bucket-name

# GPU Jobs (santa batch)
NEBIUS_IAM_TOKEN=your_iam_token
NEBIUS_PROJECT_ID=your_project_id
NEBIUS_BUCKET_ID=your_bucket_id
NEBIUS_SUBNET_ID=your_subnet_id
```

The CLI loads `.env` from the repository root automatically.

Swap a model in `config/models.yaml` only — code never names a model. Then re-run `santa doctor`.

## 🧪 Running Locally (test/debug)

Check that `.env`, Token Factory, and endpoints resolve:

```bash
santa doctor
```

One gift card (interactive form, or flags):

```bash
santa card --form
# or: santa card --name Emma --age 7 --wish "a telescope"
```

Expected: `out/<id>/card.png` and `out/<id>/card.html`. Stuck? Set `OPENAI_API_KEY` — fallbacks kick in. No endpoints yet?

```bash
santa card --offline
santa animate --offline
santa batch --offline
```

Agent (Pydantic AI tools: `recommend_gift`, `write_wish`, `generate_image`, `save_card`):

```bash
santa agent "make a card for a 7-year-old who wants a telescope"
```

CPU UI on the laptop:

```bash
uv sync --group service
santa-service          # HOST=0.0.0.0 PORT=8000  →  GET /  and  GET /wall
```

Playground notebooks: [notebooks/README.md](notebooks/README.md).

```bash
uv sync --group dev && uv run jupyter lab
```

## ☁️ Running with Serverless AI

Everything below runs in **your** Nebius project. Workshop walkthrough: [_DEV/WORKSHOP.md](_DEV/WORKSHOP.md) (steps 0–8). After the session: [_DEV/AFTER_THE_WORKSHOP.md](_DEV/AFTER_THE_WORKSHOP.md).

**1. Deploy endpoints** from the console templates (Create Endpoint), then paste URL + token into `.env`:

- Image — [Sana (L40S)](https://console.nebius.com/serverless/endpoint/create?image=cr.eu-north1.nebius.cloud%2Fe00gw2b7v3pxetvpy7%2Fsana-serve%3Ad315ae1&targetPort=8000&platform=gpu-l40s-a&preset=1gpu-8vcpu-32gb&diskSize=500GiB&preemptible=true) → `IMAGE_ENDPOINT_*`
- Video — [Wan 2.2 I2V A14B (H100)](https://console.nebius.com/serverless/endpoint/create?image=vllm%2Fvllm-omni%3Av0.24.0&command=vllm%20serve%20Wan-AI%2FWan2.2-I2V-A14B-Diffusers%20--omni%20--host%200.0.0.0%20--port%208000&targetPort=8000&platform=gpu-h100-sxm&preset=1gpu-16vcpu-200gb&diskSize=500GiB&preemptible=true) → `VIDEO_ENDPOINT_*`
- Audio — [ACE-Step 1.5 (H100)](https://console.nebius.com/serverless/endpoint/create?image=cr.eu-north1.nebius.cloud%2Fe00gw2b7v3pxetvpy7%2Facestep-serve%3Ad315ae1&targetPort=8000&platform=gpu-h100-sxm&preset=1gpu-16vcpu-200gb&diskSize=500GiB&preemptible=true) → `AUDIO_ENDPOINT_*`

Catalog: [serverless-ai-cookbook/templates](https://github.com/nebius/serverless-ai-cookbook/tree/main/templates). Re-run `santa doctor` until the **image** (and later **video**) rows are OK.

**2. Animate a card** (Wan + mood-bank tracks, or a live ACE-Step endpoint):

```bash
santa animate out/<id>/card.png --mood-bank
```

**3. Batch** — cards first, then K preemptible GPU Jobs. Needs bucket + IAM and `job.image` in `config/models.yaml`:

```bash
santa batch --kids 20 --jobs 4
```

`--local` makes cards on the laptop even if `SANTA_SERVICE_URL` is set. `--no-wait` + `santa batch --status <run_id>` to poll later.

**4. Publish** to the wall (`GET /wall` on the CPU service):

```bash
santa card --name Emma --age 7 --wish "a telescope" --publish
santa animate out/<id>/card.png --mood-bank --publish
```

**5. Tear down** before you leave (billing is yours):

```bash
santa teardown --dry-run
santa teardown
```

Echo prompts for listing/stopping endpoints: [skills/README.md](skills/README.md). Load `skills/serverless-ai` in the coding agent.

## 🧯 Troubleshooting

| Symptom | What to try |
| --- | --- |
| `santa doctor` red on **llm** or **image** | Paste `TOKEN_FACTORY_API_KEY` and `IMAGE_ENDPOINT_URL` / `IMAGE_ENDPOINT_TOKEN`. Or set `OPENAI_API_KEY` so the fallback covers the role (row becomes WARN). |
| Endpoint is RUNNING in the console, doctor still fails | RUNNING ≠ ready. Wait and re-run `santa doctor` until it pings `/v1/models`. |
| TLS / `SSLError` on a corporate laptop | The CLI injects the OS cert store (`truststore`). Persist with `export SSL_CERT_FILE=/path/to/corp-ca.pem`. S3: `AWS_CA_BUNDLE=/etc/ssl/cert.pem`. |
| No GPU endpoints yet | `SANTA_FALLBACK=only` skips primaries. Or `santa card --offline` / `santa animate --offline` / `santa batch --offline` (copies `data/fallback/`, calls no models). |
| `santa batch` / publish 403 | Use Object Storage access keys (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`), not `NEBIUS_IAM_TOKEN`. Bucket **name** is `NEBIUS_BUCKET_NAME`; bucket **id** (`NEBIUS_BUCKET_ID`) is only for Job FUSE mounts. |
| Jobs never submit | Set `NEBIUS_IAM_TOKEN` (`nebius iam get-access-token`), `NEBIUS_PROJECT_ID`, `NEBIUS_BUCKET_ID`, `NEBIUS_SUBNET_ID`, and a non-empty `job.image` in `config/models.yaml`. |
| Agent tool-calling is flaky | `claude mcp add santa -- python -m santa.mcp` |

`santa doctor` does not stop anything. `santa teardown` does.
