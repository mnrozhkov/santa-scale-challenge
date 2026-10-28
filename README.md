# 🎄 Santa Scale Challenge

**AI Orchestration & Agentic Deployment on Nebius Infrastructure**

A reference implementation for orchestrating LLMs and image, video, and audio models to create personalized gift cards at scale using Nebius Serverless AI, Token Factory, GPU Jobs, and MLflow.

## 🗂️ Repository Structure

```
santa-scale-challenge/
├── santa/                 # One package: CLI, CPU service, GPU job
│   ├── cli.py             # santa doctor | card | animate | animate_batch | teardown
│   ├── card.py            # Gift rec + wish + illustration → PNG/HTML
│   ├── animate.py         # Wan I2V + music → card.mp4
│   ├── batch.py           # Inventory cards/{id}/card.png → K GPU Jobs
│   ├── service/           # FastAPI UI + /wall
│   └── job.py             # GPU Job entrypoint
├── config/
│   ├── models.yaml        # Roles (llm, image, video, audio) + job spec
│   └── prompts.yaml       # Motion / mood prompts
├── notebooks/             # Playgrounds + research evals
├── data/
│   ├── kids.csv           # 200 KidProfiles (santa card / CPU UI)
│   └── fallback/          # Offline cards, mp4, moods, run summary
├── docker/
│   ├── service.Dockerfile # CPU UI / API
│   └── job.Dockerfile     # BYOC GPU Job image
├── skills/                # Echo prompts + Serverless AI skill
├── scripts/               # Deploy kiosk, mood bank, model sync, teardown, benches
├── tests/
└── docs/                  # Service + job contracts
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

# Keys you already have — not GPU endpoints
cp .env.example .env
# TOKEN_FACTORY_API_KEY=…     # llm role (required for a live card)
# OPENAI_API_KEY=…            # optional fallback for llm / image / video
# SANTA_FALLBACK=auto         # auto | off | only
```

`uv sync` with no groups is the laptop core: `santa doctor`, `santa card`.

GPU endpoint URLs go in `.env` after you deploy them (step 1 below). Nebius bucket / Jobs IDs go in when you create those resources (step 3). The CLI loads `.env` from the repository root automatically. Roles are named in `config/models.yaml`; secrets and URLs live in `.env`. Swap a model in the yaml only — then re-run `santa doctor`.

## 🧪 Running Locally (test/debug)

Check that `.env` and Token Factory resolve (image / video / audio may SKIP until you deploy them):

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
santa animate_batch --offline
```

CPU UI on the laptop:

```bash
uv sync --group service
npm install --prefix santa/service/ui && npm run build --prefix santa/service/ui
santa-service          # HOST=0.0.0.0 PORT=8000  →  GET /  (Sim/Real UI) and  GET /wall
```

Public kiosk (QR, `--auth none`): [docs/service.md](docs/service.md) — `./scripts/deploy-service.sh ship`, then `./scripts/deploy-service.sh url`. Operator unlock is `/?op=<SANTA_OPERATOR_TOKEN>`. `santa teardown` still stops this endpoint.

Set `SANTA_LOCAL_STORAGE=1` to use local `out/` even if AWS keys are in `.env`.

Playground notebooks: [notebooks/README.md](notebooks/README.md).

```bash
uv sync --group dev && uv run jupyter lab
```

## ☁️ Running with Serverless AI

Everything below runs in **your** Nebius project. Workshop walkthrough: [WORKSHOP.md](WORKSHOP.md) (steps 0–6).

**1. Deploy endpoints** from the console templates (Create Endpoint). When each one is ready, paste its URL and token into `.env`:

```bash
# Image (Sana) — required for a live card
IMAGE_ENDPOINT_URL=https://your-sana-endpoint
IMAGE_ENDPOINT_TOKEN=your_endpoint_token

# Video (Wan I2V) — santa animate
VIDEO_ENDPOINT_URL=https://your-wan-endpoint
VIDEO_ENDPOINT_TOKEN=your_endpoint_token

# Audio (ACE-Step) — or skip and use --mood-bank
AUDIO_ENDPOINT_URL=https://your-acestep-endpoint
AUDIO_ENDPOINT_TOKEN=your_endpoint_token
```

- Image — [Sana (L40S)](https://console.nebius.com/serverless/endpoint/create?image=cr.eu-north1.nebius.cloud%2Fe00gw2b7v3pxetvpy7%2Fsana-serve%3Ad315ae1&targetPort=8000&platform=gpu-l40s-a&preset=1gpu-8vcpu-32gb&diskSize=500GiB&preemptible=true) → `IMAGE_ENDPOINT_*`
- Video — [Wan 2.2 I2V A14B (H100)](https://console.nebius.com/serverless/endpoint/create?image=vllm%2Fvllm-omni%3Av0.24.0&command=vllm%20serve%20Wan-AI%2FWan2.2-I2V-A14B-Diffusers%20--omni%20--host%200.0.0.0%20--port%208000&targetPort=8000&platform=gpu-h100-sxm&preset=1gpu-16vcpu-200gb&diskSize=500GiB&preemptible=true) → `VIDEO_ENDPOINT_*`
- Audio — [ACE-Step 1.5 (H100)](https://console.nebius.com/serverless/endpoint/create?image=cr.eu-north1.nebius.cloud%2Fe00gw2b7v3pxetvpy7%2Facestep-serve%3Ad315ae1&targetPort=8000&platform=gpu-h100-sxm&preset=1gpu-16vcpu-200gb&diskSize=500GiB&preemptible=true) → `AUDIO_ENDPOINT_*`

Catalog: [serverless-ai-cookbook/templates](https://github.com/nebius/serverless-ai-cookbook/tree/main/templates). Re-run `santa doctor` until the **image** (and later **video**) rows are OK.

**2. Animate a card** (Wan + mood-bank tracks, or a live ACE-Step endpoint):

```bash
santa animate out/<id>/card.png --mood-bank
```

**3. Animate batch** — publish GiftCards via the API, then K preemptible GPU Jobs over `cards/{id}/card.png`. Add bucket + IAM to `.env` (create these in the console if you have not yet) and set `job.image` in `config/models.yaml`:

```bash
# Object Storage (publish + santa animate_batch)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_ENDPOINT_URL=https://storage.eu-north1.nebius.cloud
NEBIUS_BUCKET_NAME=your-bucket-name

# GPU Jobs
NEBIUS_IAM_TOKEN=your_iam_token          # nebius iam get-access-token
NEBIUS_PROJECT_ID=your_project_id
NEBIUS_BUCKET_ID=your_bucket_id
NEBIUS_SUBNET_ID=your_subnet_id
```

Then:

```bash
santa card --name Emma --age 7 --wish "a telescope" --publish
santa animate_batch --jobs 4
```

`--no-wait` + `santa animate_batch --status <run_id>` to poll later. Existing `cards/{id}/video.mp4` are skipped.

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
| No GPU endpoints yet | `SANTA_FALLBACK=only` skips primaries. Or `santa card --offline` / `santa animate --offline` / `santa animate_batch --offline` (copies `data/fallback/`, calls no models). |
| `santa animate_batch` / publish 403 | Use Object Storage access keys (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`), not `NEBIUS_IAM_TOKEN`. Bucket **name** is `NEBIUS_BUCKET_NAME`; bucket **id** (`NEBIUS_BUCKET_ID`) is only for Job FUSE mounts. |
| `santa animate_batch` empty `cards/` | Publish GiftCards first (`santa card … --publish`), then `santa animate_batch --jobs 4`. Animate batch is Jobs only — it does not make GiftCards. |
| Jobs never submit | Publish GiftCards, then set `NEBIUS_IAM_TOKEN` (`nebius iam get-access-token`), `NEBIUS_PROJECT_ID`, `NEBIUS_BUCKET_ID`, `NEBIUS_SUBNET_ID`, and a non-empty `job.image` in `config/models.yaml` (`docker build --platform linux/amd64 -f docker/job.Dockerfile`). |

`santa doctor` does not stop anything. `santa teardown` does.
