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

In the Nebius console, create a Serverless AI endpoint from the Sana template (L40S). Copy its URL and token into `.env` as `IMAGE_ENDPOINT_URL` / `IMAGE_ENDPOINT_TOKEN`. Re-run `santa doctor` until the **image** row is OK (or WARN with fallback).

Expected: `image` check pings `/v1/models`. RUNNING in the console is not the same as ready — wait until doctor is happy.

## 3 · One card

```bash
santa card --form
# or: santa card --name Emma --age 7 --wish "a telescope"
```

Expected (a few seconds):

```text
llm: openai/gpt-oss-120b (primary, …ms)
image: sana (primary, …ms)
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

## 6 · Batch

Needs bucket + IAM (`NEBIUS_BUCKET_*`, `NEBIUS_IAM_TOKEN`, `NEBIUS_PROJECT_ID`, `NEBIUS_SUBNET_ID`) and `job.image` in `config/models.yaml`. Cards first, then K GPU Jobs.

```bash
santa batch --kids 20 --jobs 4
```

Expected: four jobs moving QUEUED → RUNNING → COMPLETED, then

```text
summary done … skipped … failed … cost $… saved $… → out/runs/<run_id>/summary.json
```

`--local` makes cards on the laptop even if `SANTA_SERVICE_URL` is set. `--no-wait` + `santa batch --status <run_id>` to poll later.

## 7 · Video card

Needs `VIDEO_ENDPOINT_URL` / `VIDEO_ENDPOINT_TOKEN` (Wan). Audio uses ACE-Step, or `--mood-bank` for bundled tracks.

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
