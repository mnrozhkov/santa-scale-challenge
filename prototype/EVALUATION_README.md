# Model Evaluation Framework

This directory contains the Model Evaluation Framework for comparing different LLM and image generation models based on cost, speed, and quality.

## Structure

```
prototype/
├── src/
│   ├── clients/
│   │   ├── llm_client.py          # LLM client for OpenAI-compatible and vLLM services
│   │   └── image_client.py        # Image generation client for various services
│   └── evaluation.py              # MLflow integration and metrics utilities
├── 02_gift_rec_eval.ipynb          # Gift recommendation LLM evaluation
├── 03_wish_model_eval.ipynb       # Wish generation LLM evaluation
└── 04_image_generation_eval.ipynb # Image generation evaluation
```

## Setup

### 1. Install Dependencies

```bash
# Install base dependencies
uv pip install -e .

# Install MLflow and evaluation dependencies
uv pip install -e ".[mlflow]"

# Install development dependencies (includes Jupyter)
uv pip install -e ".[dev]"
```

### 2. Configure Environment Variables

Create a `.env` file in the repository root with the following variables:

```bash
# MLflow Tracking Server Configuration
MLFLOW_TRACKING_URI=https://your-mlflow-server.nebius.cloud
MLFLOW_TRACKING_USERNAME=your_username
MLFLOW_TRACKING_PASSWORD=your_password

# AI Studio / Nebius API
NEBIUS_API_KEY=your_nebius_api_key

# OpenAI API (optional, for comparison)
OPENAI_API_KEY=your_openai_api_key

# Token Factory API (optional, for comparison)
TOKEN_FACTORY_API_KEY=your_token_factory_api_key
TOKEN_FACTORY_BASE_URL=https://api.tokenfactory.ai/v1

# Recraft API (for image generation)
RECRAFT_API_KEY=your_recraft_api_key

# Self-hosted vLLM endpoint (when running locally or on Nebius)
VLLM_BASE_URL=http://localhost:8000/v1
VLLM_MODEL_7B=meta-llama/Llama-2-7b-chat-hf
VLLM_MODEL_13B=meta-llama/Llama-2-13b-chat-hf

# Self-hosted image generation endpoints
SDXL_LIGHTNING_URL=http://localhost:7860
FLUX_SELF_HOSTED_URL=http://localhost:7861
```

### 3. Set up MLflow on Nebius (Manual)

1. Deploy MLflow tracking server on Nebius
2. Configure artifact storage (Nebius Object Storage)
3. Store access credentials in `.env` file

## Running Evaluations

### Gift Recommendation Evaluation

Evaluates LLM models for generating gift recommendations.

```bash
jupyter notebook prototype/02_gift_rec_eval.ipynb
```

**Metrics tracked:**
- `latency_ms`: Time per prompt
- `tokens_in` / `tokens_out`: Inference cost basis
- `quality_score`: LLM-as-a-judge scoring
- `monthly_estimate`: Cost for 2B requests

**MLflow experiment:** `gift_recommendation_eval`

### Wish Generation Evaluation

Evaluates LLM models for generating personalized holiday wishes.

```bash
jupyter notebook prototype/03_wish_model_eval.ipynb
```

**Metrics tracked:**
- `latency_ms`: Time per prompt
- `tokens_in` / `tokens_out`: Inference cost basis
- `quality_score`: LLM-as-a-judge focusing on:
  - Warmth and personalization
  - Age-appropriateness
  - Safety (no dangerous/offensive content)
- `monthly_estimate`: Cost for 2B requests

**MLflow experiment:** `wish_generation_eval`

### Image Generation Evaluation

Evaluates image generation models for gift card illustrations.

```bash
jupyter notebook prototype/04_image_generation_eval.ipynb
```

**Metrics tracked:**
- `latency_ms`: Time per image generation
- `output_size_bytes`: Size of generated image
- `quality_score`: LLM-as-a-judge + aesthetic scoring
- `cost_per_image`: Cost per image generation
- `monthly_estimate`: Cost for 2B images

**MLflow experiment:** `image_generation_eval`

## Self-Hosted Models

### vLLM Setup

To evaluate self-hosted vLLM models:

1. Start vLLM on Nebius GPU:
   ```bash
   # Configure and start vLLM server
   # See models/llm/ for setup scripts
   ```

2. Update `.env` with vLLM endpoint:
   ```bash
   VLLM_BASE_URL=http://your-vllm-server:8000/v1
   ```

3. The evaluation notebooks will automatically detect and include vLLM models if `VLLM_BASE_URL` is set.

### Image Generation Models

For self-hosted image generation:

1. Deploy SDXL Lightning or Flux on Nebius GPU
2. Update `.env` with endpoints:
   ```bash
   SDXL_LIGHTNING_URL=http://your-sdxl-server:7860
   FLUX_SELF_HOSTED_URL=http://your-flux-server:7861
   ```

## Viewing Results

All evaluation runs are logged to MLflow. View results at:

```
https://your-mlflow-server.nebius.cloud
```

Navigate to the experiment (e.g., `gift_recommendation_eval`) to compare:
- Latency across models
- Quality scores
- Cost estimates
- Generated outputs (text/images)

## Code Structure

### LLM Client (`src/clients/llm_client.py`)

- Supports OpenAI-compatible APIs
- Supports self-hosted vLLM
- Returns metrics (latency, tokens) with each generation

### Image Client (`src/clients/image_client.py`)

- Supports Recraft API
- Supports TokenFactory API
- Supports self-hosted SDXL Lightning and Flux
- Returns metrics (latency, output size) with each generation

### Evaluation Utilities (`src/evaluation.py`)

- MLflow setup and configuration
- Logging functions for LLM and image evaluations
- Cost estimation utilities

## Notes

- All code is clean and minimalistic (no unnecessary print statements or emojis)
- Credentials are stored in `.env` file (not committed to git)
- Evaluation notebooks automatically detect available models based on environment variables
- Quality scoring uses LLM-as-a-judge when a judge client is available
