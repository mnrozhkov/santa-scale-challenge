# 🎄 Santa Scale Challenge

## AI Orchestration & Agentic Deployment on Nebius Infrastructure

A reference implementation for orchestrating LLMs and image generation models to create personalized gift cards at scale using **Nebius GPU infrastructure**, **SkyPilot**, and **MLflow**.

---

## 🗂️ Repository Structure

```text
santa-scale-challenge/
├── prototype/           # Prototype workflows and experiments
│   ├── santa_workflow.py          # Main workflow: CSV → gift cards
│   ├── src/                       # Core modules
│   │   ├── benchmark_llm.py       # LLM benchmarking tool
│   │   ├── generate_kids.py      # Generate kid profiles CSV
│   │   ├── data_upload.py         # S3 upload utility
│   │   └── ...
│   └── data/                      # Data and outputs
└── infra/               # SkyPilot configuration
    └── sky/
        └── santa_workflow.yaml     # SkyPilot job config
```

---

## 🚀 Installation

### Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) package manager

### Setup

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone repository
git clone https://github.com/<your-org>/santa-scale-challenge
cd santa-scale-challenge

# Create virtual environment
uv python install 3.12
uv venv --python 3.12
source .venv/bin/activate

# Laptop CLI only (core deps; ~1 s from a warm uv cache on this machine, well under 60 s)
uv sync

# Service UI/API + tests (fastapi via the dev group)
uv sync --group dev

# Optional: GPU job weights pipeline, or research/MLflow notebooks
# uv sync --group job
# uv sync --group research
```

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the repository root:

```bash
# LLM API Keys (at least one required)
OPENAI_API_KEY=your_openai_key
TOKEN_FACTORY_API_KEY=your_token_factory_key

# Image Generation API Key
RECRAFT_API_KEY=your_recraft_key

# MLflow Tracking (for remote tracking)
MLFLOW_TRACKING_URI=https://your-mlflow-server
MLFLOW_TRACKING_USERNAME=your_username
MLFLOW_TRACKING_PASSWORD=your_password

# S3 Storage (for SkyPilot)
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_ENDPOINT_URL=https://storage.eu-north1.nebius.cloud:443
NEBIUS_S3_BUCKET=nebius://santa-storage-s3
```

The script automatically loads `.env` from the repository root.

---

## 🧪 Running Locally

### 1. Generate Kid Profiles

```bash
python prototype/src/generate_kids.py 20 --output prototype/data/santa_workflow/kids.csv
```

### 2. Run LLM Benchmarking

Benchmark different LLM models with remote MLflow tracking:

```bash
python prototype/src/benchmark_llm.py \
  --models gpt-4o-mini gpt-4-turbo \
  --mlflow-tracking-uri $MLFLOW_TRACKING_URI \
  --mlflow-username $MLFLOW_TRACKING_USERNAME \
  --mlflow-password $MLFLOW_TRACKING_PASSWORD
```

Options:
- `--models`: Space-separated list of model names
- `--concurrency`: Number of concurrent requests (default: 1)
- `--num-requests`: Number of requests per model (default: 10)
- `--output-csv`: Path to save results CSV

### 3. Run Santa Workflow

Generate personalized gift cards from CSV:

```bash
python prototype/santa_workflow.py prototype/data/santa_workflow/kids.csv \
  --llm-model gpt-4o-mini \
  --image-model recraftv3 \
  --output-dir prototype/data/santa_workflow/cards \
  --intermediate-dir prototype/data/santa_workflow/intermediate \
  --no-drive-upload
```

Options:
- `--llm-model`: LLM model name (default: gpt-4o-mini)
- `--image-model`: Image model name (default: recraftv3)
- `--output-dir`: Directory for PNG cards
- `--intermediate-dir`: Directory for intermediate JSON files
- `--no-drive-upload`: Skip Google Drive upload
- `--default-age`: Default age for kids (default: 10)

The workflow:

1. Reads kid profiles from CSV
2. Generates gift recommendations (LLM)
3. Generates personalized wishes (LLM)
4. Generates card images (Image API)
5. Creates final PNG cards
6. Saves intermediate results as JSON

---

## ☁️ Running with SkyPilot

### Prerequisites

1. Install SkyPilot:
```bash
uv pip install -e ".[skypilot]"
```

2. Configure SkyPilot for Nebius:
```bash
sky check
```

3. Set environment variables (see Configuration section)

### Launch New Cluster and Run Workflow

Launch a new SkyPilot cluster and automatically run the santa_workflow:

```bash
sky launch \
  --secret RECRAFT_API_KEY \
  --secret OPENAI_API_KEY \
  --secret AWS_ACCESS_KEY_ID \
  --secret AWS_SECRET_ACCESS_KEY \
  infra/sky/santa_workflow.yaml
```

The workflow will:

- Provision H100 GPU instance on Nebius
- Clone repository and install dependencies
- Generate kid profiles
- Run santa_workflow.py
- Upload results to S3

### Run Job on Existing Cluster

Execute the workflow on an existing SkyPilot cluster:

```bash
sky exec <SKYPILOT_CLUSTER_NAME> \
  --secret RECRAFT_API_KEY \
  --secret OPENAI_API_KEY \
  --secret AWS_ACCESS_KEY_ID \
  --secret AWS_SECRET_ACCESS_KEY \
  infra/sky/santa_workflow.yaml
```

Replace `<SKYPILOT_CLUSTER_NAME>` with your cluster name (e.g., `santa_workflow`).

### Monitor and Manage

```bash
# View logs
sky logs santa_workflow -t

# SSH into the instance
sky ssh santa_workflow

# Stop the cluster
sky down santa_workflow
```

### SkyPilot Configuration

Edit `infra/sky/santa_workflow.yaml` to customize:

- Number of GPUs (`accelerators: H100:1`)
- Instance type
- Environment variables
- Secrets (API keys)
- Run commands

---

## 📊 MLflow Integration

The project integrates with MLflow for tracking:

- Model performance metrics
- Latency and throughput
- Cost estimates
- Generated artifacts (images, cards)

When `MLFLOW_TRACKING_URI` is set, all runs are automatically logged to the remote MLflow server.

View results:
```bash
# If running MLflow locally
mlflow ui

# Or access your remote MLflow UI
open $MLFLOW_TRACKING_URI
```

---

## 🧱 Data Models

### KidProfile

```python
id: str
name: str
age: int
wishlist: List[str]
```

### GiftCard Pipeline

1. **GiftRecommendation** - LLM-generated gift suggestions
2. **Wish** - Personalized holiday wish text
3. **CardImage** - Generated card illustration
4. **GiftCard** - Final rendered PNG card

---

## 🔧 Utilities

### Upload to S3

```bash
# Upload a file
python prototype/src/data_upload.py \
  --source-file prototype/data/santa_workflow/kids.csv \
  --destination-bucket nebius://santa-storage-s3 \
  --s3-prefix santa_workflow

# Upload a directory
python prototype/src/data_upload.py \
  --source-dir prototype/data/santa_workflow/cards \
  --destination-bucket nebius://santa-storage-s3 \
  --s3-prefix santa_workflow
```

---

## 🧯 Troubleshooting

- **Import errors?** Ensure virtual environment is activated: `source .venv/bin/activate`
- **API key errors?** Check `.env` file exists and contains required keys
- **MLflow connection errors?** Verify `MLFLOW_TRACKING_URI` and credentials are correct
- **SkyPilot errors?** Run `sky check` to verify Nebius configuration

---

## Agent / MCP

If Token Factory tool-calling is flaky, the same card pipeline is a one-tool MCP server (`generate_card`).

Claude Code:

```bash
claude mcp add santa -- python -m santa.mcp
```

Cursor (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "santa": {
      "command": "python",
      "args": ["-m", "santa.mcp"]
    }
  }
}
```

Or: `santa agent "make a card for a 7-year-old who wants a telescope"`

---

## 📄 License

MIT — use freely for workshops, training, and holiday-themed AI adventures.
