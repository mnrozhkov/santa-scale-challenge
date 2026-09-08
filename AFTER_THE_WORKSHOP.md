# After the workshop

Keep going in the same account. Stop what you started; the bill is yours.

## Stop / start

```bash
santa teardown --dry-run    # list endpoints + jobs, print $/h that would be saved
santa teardown              # stop endpoints, cancel non-terminal jobs
```

Start an endpoint again from the Nebius console (or `nebius ai endpoint start`). Jobs are one-shot: re-run `santa batch` (same `--run-id` skips videos that already exist).

Echo prompts for an agent: `skills/README.md`.

## Cost

`out/runs/<run_id>/summary.json` has per-job `cost_usd` / `on_demand_cost_usd` and `savings_usd` (preemptible vs on-demand). Rates live in `santa/cost.py` (H100 NVLink: $3.85/h on-demand, $2.15/h preemptible as of 2026-09-07). CPU service is `cpu-e2` vCPU + RAM.

A 20-kid / 4-job run is the workshop size. `--kids 200 --jobs 40` is the same command, more hours.

## Call your endpoint with the OpenAI SDK

Sana is OpenAI-compatible `images.generate`:

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url=os.environ["IMAGE_ENDPOINT_URL"],
    api_key=os.environ["IMAGE_ENDPOINT_TOKEN"],
)
img = client.images.generate(
    model="sana",
    prompt="A wrapped telescope under a starry winter sky, no people, no text",
    size="1024x1024",
)
```

Token Factory is the same SDK against `https://api.tokenfactory.nebius.com/v1` with `TOKEN_FACTORY_API_KEY`. Video/audio are **not** that shape — see `santa/models.py` (`wan_omni`, `acestep_audio`) or the playground notebooks.

## Swap a model

Edit `config/models.yaml` only. Code never names a model. Example: pick a different `llm` (uncomment a candidate) or point `image.fallback.model` at another OpenAI image model. Then `santa doctor` and `santa card --form`.

`SANTA_FALLBACK=only` skips the primary (useful before the endpoint is RUNNING). `off` disables fallbacks.

## Deploy video / audio yourself

Console templates (your project):

- Video: Wan 2.2 I2V A14B on H100 — `VIDEO_ENDPOINT_URL` / `VIDEO_ENDPOINT_TOKEN`
- Audio: ACE-Step 1.5 on H100 — `AUDIO_ENDPOINT_URL` / `AUDIO_ENDPOINT_TOKEN`

Then `santa animate out/<id>/card.png` (fresh ACE-Step) or `--mood-bank` (bundled `data/fallback/moods/`). Rebuild the bank with `uv run scripts/make_mood_bank.py --force` once the audio endpoint is up.

## BYOC (bring your own container)

`docker/job.Dockerfile` is the GPU Job image **and** the BYOC example: CUDA + `santa[job]`, entrypoint `python -m santa.job`.

```bash
docker build --platform linux/amd64 -f docker/job.Dockerfile -t santa-job:local .
docker tag santa-job:local cr.eu-north1.nebius.cloud/<your-registry>/santa-job:<tag>
docker push cr.eu-north1.nebius.cloud/<your-registry>/santa-job:<tag>
```

Paste that tag into `config/models.yaml` `job.image`. Pre-bake weights once: `uv run --with huggingface_hub scripts/sync_models.py` (bucket `models/`, job `HF_HOME=/data/models`).

CPU UI: [docs/service.md](docs/service.md). Job contract: [docs/job.md](docs/job.md).

## Jobs at scale

```bash
santa batch --kids 200 --jobs 40
```

Same path as step 6: cards (CPU service or `--local`) → 40 preemptible H100 chunks → `run_summary.json`. Idempotent: existing `videos/{id}.mp4` are skipped. Cancel one job and re-run the same `--run-id` to fill the gap.

Wall: `GET /wall` on the service lists `cards/`, `videos/`, latest `runs/*/summary.json`.

## Credits

Workshop credits are in **your** billing account. `santa teardown` before you walk away. `doctor` does not stop anything.
