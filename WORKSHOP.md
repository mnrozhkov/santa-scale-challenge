# Workshop

Seven steps. One command block each. Everything runs in **your** Nebius project. Endpoints bill while RUNNING — finish with Step 6 before you leave.

Stuck at any step? Set `OPENAI_API_KEY` in `.env` — fallbacks kick in (`SANTA_FALLBACK=auto`). Still no network? `santa card --offline` / `santa animate --offline` / `santa animate_batch --offline` copies bundled files from `data/fallback/`.

## Step 0 - Setup

```bash
uv sync
source .venv/bin/activate
cp .env.example .env
# TOKEN_FACTORY_API_KEY=…     # llm role (required for a live card)
# OPENAI_API_KEY=…            # optional fallback
# SANTA_FALLBACK=auto         # auto | off | only
santa doctor
```

Expected: a table of OK / WARN / SKIP / FAIL. **llm** should be OK (or WARN with OpenAI fallback). **image** / **video** / **audio** may SKIP until Step 1. GPU endpoint URLs and Nebius bucket / Jobs IDs go in `.env` after you create those resources (Steps 1 and 5).

## Step 1 - Deploy image, video and audio generation Endpoints

Create three endpoints in **your** project (console → Create Endpoint from each template). Token Factory from Step 0 covers the llm role — it is not a GPU endpoint. When each endpoint is ready, paste its URL and token into `.env`:

```bash
# Image (Sana) — required for a live card (Step 2)
IMAGE_ENDPOINT_URL=https://your-sana-endpoint
IMAGE_ENDPOINT_TOKEN=your_endpoint_token

# Video (Wan I2V) — santa animate (Step 4)
VIDEO_ENDPOINT_URL=https://your-wan-endpoint
VIDEO_ENDPOINT_TOKEN=your_endpoint_token

# Audio (ACE-Step) — or skip and use --mood-bank
AUDIO_ENDPOINT_URL=https://your-acestep-endpoint
AUDIO_ENDPOINT_TOKEN=your_endpoint_token
```

- Image — [Sana (L40S)](https://console.nebius.com/serverless/endpoint/create?image=cr.eu-north1.nebius.cloud%2Fe00gw2b7v3pxetvpy7%2Fsana-serve%3Ad315ae1&targetPort=8000&platform=gpu-l40s-a&preset=1gpu-8vcpu-32gb&diskSize=500GiB&preemptible=true) → `IMAGE_ENDPOINT_*`
- Video — [Wan 2.2 I2V A14B (H100)](https://console.nebius.com/serverless/endpoint/create?image=vllm%2Fvllm-omni%3Av0.24.0&command=vllm%20serve%20Wan-AI%2FWan2.2-I2V-A14B-Diffusers%20--omni%20--host%200.0.0.0%20--port%208000&targetPort=8000&platform=gpu-h100-sxm&preset=1gpu-16vcpu-200gb&diskSize=500GiB&preemptible=true) → `VIDEO_ENDPOINT_*`
- Audio — [ACE-Step 1.5 (H100)](https://console.nebius.com/serverless/endpoint/create?image=cr.eu-north1.nebius.cloud%2Fe00gw2b7v3pxetvpy7%2Facestep-serve%3Ad315ae1&targetPort=8000&platform=gpu-h100-sxm&preset=1gpu-16vcpu-200gb&diskSize=500GiB&preemptible=true) → `AUDIO_ENDPOINT_*` (skip if you will only use `--mood-bank`)

Catalog: [serverless-ai-cookbook/templates](https://github.com/nebius/serverless-ai-cookbook/tree/main/templates).

```bash
santa doctor
```

Expected: **image**, **video**, and **audio** (and **llm**) are OK, or WARN if a fallback covers them. RUNNING in the console is not ready — wait until doctor pings `/v1/models`. Last line: `All required checks passed. Next: santa card --form`. Step 5 runs Wan **inside** GPU Jobs, not this video endpoint.

## Step 2 — Generate a gift card (API inference)

```bash
santa card --form
# or: santa card --name Emma --age 7 --wish "a telescope"
```

Expected (a few seconds):

```text
llm: openai/gpt-oss-120b (primary, …ms)
image: Efficient-Large-Model/Sana_1600M_1024px_diffusers (primary, …ms)
Wrote out/<id>/card.png
Wrote out/<id>/card.html
```

If Token Factory or Sana is cold you will see `(fallback, …)` and still get a card.

## Step 3 — Ask Echo (agent in the console)

In Cursor / Claude Code, load `skills/serverless-ai` (see `skills/README.md`) and paste one Echo prompt: list endpoints, or estimate H100 cost.

Expected: a list of *your* endpoints (id, state, platform) — not a shared pool.

## Step 4 - Animate a gift card (API inference)

Uses the Wan endpoint from Step 1. `--mood-bank` muxes bundled tracks instead of calling ACE-Step. Use the PNG from Step 2.

```bash
santa animate out/<id>/card.png --mood-bank
```

Expected: `out/<id>/card.mp4`. `--no-wait` writes a ticket; `santa animate --status out/<id>/animate.ticket.json` polls it.

Publish to the wall after Step 5 has bucket creds (service must be up, or `--local`):

```bash
santa animate out/<id>/card.png --mood-bank --publish
```

`--publish` writes `cards/{id}/video.mp4` next to the GiftCard files if those were published too.

## Step 5 – Animate batch of gift cards (batch inference)

`santa animate_batch` is Jobs-only. It does not manufacture GiftCards and does not call the Wan endpoint from Step 1. Add bucket + IAM to `.env` (create these in the console if you have not yet) and set `job.image` in `config/models.yaml`. Mint the token with `nebius iam get-access-token`. `santa doctor` shows a skip/warn if `job.image` is still empty — build/push `docker/job.Dockerfile` for `linux/amd64` and paste the registry tag.

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

Then publish illustrations (same API as Step 2). Each kid lands in one bucket folder: `cards/{id}/card.png`, `card.html`, `card.json`. Jobs add `video.mp4` next to them.

```bash
santa card --name Emma --age 7 --wish "a telescope" --publish
santa card --name Lucas --age 5 --wish "a train" --publish
santa animate_batch --jobs 4
```

Expected: a live table of four Jobs moving QUEUED → RUNNING → COMPLETED, then

```text
summary done … skipped … failed … cost $… saved $… → out/runs/<run_id>/summary.json
```

`--no-wait` + `santa animate_batch --status <run_id>` to poll later. Re-run the same `--run-id` to fill video gaps only. Empty `cards/` exits with a publish hint (`santa card … --publish`).

## Step 6 — Clean up resources

Do this before you walk away. Endpoints keep charging while RUNNING even if you are not calling them. Needs `NEBIUS_IAM_TOKEN` and `NEBIUS_PROJECT_ID` (same as Step 5: `nebius iam get-access-token`).

```bash
santa teardown --dry-run    # list endpoints + jobs, print $/h that would be saved
santa teardown              # stop endpoints, cancel non-terminal jobs
```

Expected: a list of what stopped/cancelled and `$…/h` saved. Then in the console: **no** RUNNING endpoints. Ask Echo to double-check:

```text
What resources am I currently paying for in this project?
```
