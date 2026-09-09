# Workshop

Eight steps. One command block each. Everything runs in **your** Nebius project.

Stuck at any step? Set `OPENAI_API_KEY` in `.env` — fallbacks kick in (`SANTA_FALLBACK=auto`). Still no network? `santa card --offline` / `santa animate --offline` / `santa batch --offline` copies bundled files from `data/fallback/`.

## 0 · Setup

```bash
uv sync
cp .env.example .env
# paste TOKEN_FACTORY_API_KEY, IMAGE_ENDPOINT_URL, IMAGE_ENDPOINT_TOKEN
# optional: OPENAI_API_KEY, VIDEO_*, AUDIO_*, NEBIUS_*, AWS_*
santa doctor
```

Expected: a table of OK / WARN / SKIP / FAIL. Required red rows must go green (or WARN if a fallback covers them). Last line: `All required checks passed. Next: santa card --form`.

## 1–2 · Deploy the image endpoint

Open the [Sana template](https://console.nebius.com/serverless/endpoint/create?image=cr.eu-north1.nebius.cloud%2Fe00gw2b7v3pxetvpy7%2Fsana-serve%3Ad315ae1&targetPort=8000&platform=gpu-l40s-a&preset=1gpu-8vcpu-32gb&diskSize=500GiB&preemptible=true) in the Nebius console (Create Endpoint, L40S). Create it, then copy its URL and token into `.env` as `IMAGE_ENDPOINT_URL` / `IMAGE_ENDPOINT_TOKEN`. Re-run `santa doctor` until the **image** row is OK (or WARN with fallback).

Catalog of other models: [serverless-ai-cookbook/templates](https://github.com/nebius/serverless-ai-cookbook/tree/main/templates).

Expected: `image` check pings `/v1/models`. RUNNING in the console is not the same as ready — wait until doctor is happy.

## 3 · One card

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

## 4 · Echo (agent in the console)

In Cursor / Claude Code, load `skills/serverless-ai` (see `skills/README.md`) and paste one Echo prompt: list endpoints, or estimate H100 cost.

Expected: a list of *your* endpoints (id, state, platform) — not a shared pool.

## 5 · Agent

```bash
santa agent "make a card for a 7-year-old who wants a telescope"
```

Expected: `Wrote out/<id>/card.png`. The agent calls `recommend_gift`, `write_wish`, `generate_image`, `save_card`.

MCP fallback (if tool-calling is flaky):

```bash
claude mcp add santa -- python -m santa.mcp
```



## 6 · Batch (GPU Jobs)

Two patterns, consecutive: publish GiftCards via the API (same as Step 3), then submit K GPU Jobs over whatever PNGs are already in `cards/`. Batch does not manufacture GiftCards.

Publish a few illustrations (repeat as needed):

```bash
santa card --name Emma --age 7 --wish "a telescope" --publish
santa card --name Lucas --age 5 --wish "a train" --publish
```

Needs a Job image tag in `config/models.yaml` `job.image`, plus bucket + IAM (`NEBIUS_BUCKET_*`, `NEBIUS_IAM_TOKEN`, `NEBIUS_PROJECT_ID`, `NEBIUS_SUBNET_ID`). Mint the token with `nebius iam get-access-token`. `santa doctor` shows a skip/warn if `job.image` is still empty — build/push `docker/job.Dockerfile` for `linux/amd64` and paste the registry tag.

```bash
santa batch --jobs 4
```

Expected: a live table of four Jobs moving QUEUED → RUNNING → COMPLETED, then

```text
summary done … skipped … failed … cost $… saved $… → out/runs/<run_id>/summary.json
```

`--no-wait` + `santa batch --status <run_id>` to poll later. Re-run the same `--run-id` to fill video gaps only. Empty `cards/` exits with a publish hint.

## 7 · Video card

Needs a Wan endpoint: [Wan 2.2 I2V A14B](https://console.nebius.com/serverless/endpoint/create?image=vllm%2Fvllm-omni%3Av0.24.0&command=vllm%20serve%20Wan-AI%2FWan2.2-I2V-A14B-Diffusers%20--omni%20--host%200.0.0.0%20--port%208000&targetPort=8000&platform=gpu-h100-sxm&preset=1gpu-16vcpu-200gb&diskSize=500GiB&preemptible=true) → `VIDEO_ENDPOINT_URL` / `VIDEO_ENDPOINT_TOKEN`. Audio uses [ACE-Satep 1.5](https://console.nebius.com/serverless/endpoint/create?image=cr.eu-north1.nebius.cloud%2Fe00gw2b7v3pxetvpy7%2Facestep-serve%3Ad315ae1&targetPort=8000&platform=gpu-h100-sxm&preset=1gpu-16vcpu-200gb&diskSize=500GiB&preemptible=true), or `--mood-bank` for bundled tracks.

```bash
santa animate out/<id>/card.png --mood-bank
```

Expected: `out/<id>/card.mp4`. `--no-wait` writes a ticket; `santa animate --status out/<id>/animate.ticket.json` polls it.

Publish to the wall (service must be up, or `--local` with bucket creds):

```bash
santa card --name Emma --age 7 --wish "a telescope" --publish
santa animate out/<id>/card.png --mood-bank --publish
```



## 8 · Keep building

- [AFTER_THE_WORKSHOP.md](AFTER_THE_WORKSHOP.md) — stop/start, cost, OpenAI SDK, swap a model, deploy video/audio, BYOC, scale the batch, credits
- [notebooks/README.md](notebooks/README.md) — one playground per endpoint
- `santa teardown --dry-run` before you leave, then `santa teardown`
