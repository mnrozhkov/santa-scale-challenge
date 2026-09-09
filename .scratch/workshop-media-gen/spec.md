# Santa v2 — workshop media-gen tech demo

Status: ready-for-agent

Approved 2026-09-07 (Q1 H100/A14B · Q2 pre-bake · Q3 both, default service · Q4/Q5 IAM token + bucket ID · Q8 rename). **Revised 2026-09-07 (R1–R4):** no shared/ours/theirs — every participant runs everything in their own account · all Dockerfiles under `docker/` · `prototype/` → `notebooks/` (last issue) · every role has a fallback, OpenAI by default. Issues in `issues/`.

Inputs: workshop spec §1, §5, §6, §7 · your answers (cards = CPU service with UI calling model endpoints; videos = batch inference on preemptible GPU Jobs; CPU = regular VM; LLM candidates; Chrome dropped) · cookbook READMEs for `endpoint-sana`, `endpoint-wan22-i2v-a14b`, `endpoint-ace-step-1-5` · `docs.nebius.com/serverless/jobs/manage` · dubbing repo `nebius.py` / `cost.py`.

## 1. Architecture

Everything below runs in **the participant's own Nebius account**: their endpoints, their CPU service, their Jobs, their bucket. There is no shared infrastructure.

```text
                       ┌──────── Token Factory (OpenAI-compatible) ─────────┐   ┌──── OpenAI (fallback for every role) ────┐
                       │  llm: gift rec · wish · agent reasoning             │   │  gpt-4o-mini · gpt-image-1 · sora-2      │
                       └─────────────────────────────────────────────────────┘   └──────────────────────────────────────────┘
                                   ▲                                                       ▲ (SANTA_FALLBACK=auto)
 laptop                            │                                                       │
 ┌──────────────────────┐          │                          ┌────────────────────────────┴───┐
 │ santa CLI            │──────────┘                          │ santa-service  (CPU endpoint)  │
 │  doctor · card ·     │                                     │  FastAPI UI + /api + /wall     │
 │  agent · batch ·     │───── image role ──► Sana endpoint ◄─│  same `santa` package          │
 │  animate · publish   │                     (L40S)          └──────────────┬─────────────────┘
 │ santa-mcp (shim)     │                                                    │ reads/writes
 └──────────┬───────────┘                                                    ▼
            │ Nebius SDK                                     ┌─────────── Object Storage bucket ───────────┐
            ▼                                                │ kids/ · cards/{id}.png|.html · videos/{id}.mp4│
 ┌──────────────────────────────┐    /data FUSE mount        │ audio/moods/*.mp3 · runs/{run_id}/summary.json│
 │ K × Serverless Jobs (GPU,    │◄──────────────────────────►│ models/ (pre-baked HF cache)                  │
 │ preemptible) santa-job image │                            └───────────────────────────────────────────────┘
 │  chunk → Wan I2V → +music →  │
 │  mux → videos/{id}.mp4       │──── audio role ──► ACE-Step endpoint (H100)    video role ──► Wan endpoint (H100, `animate`)
 └──────────────────────────────┘
```

One package, three runtimes: `santa` CLI on the laptop, `santa-service` on a CPU endpoint, `python -m santa.job` inside GPU Jobs.

## 2. Scenario → component

| Step (spec §7) | Participant runs                         | Component                                                                                  | Model role · where                              |
| -------------- | ---------------------------------------- | ------------------------------------------------------------------------------------------ | ----------------------------------------------- |
| 0 Setup        | `santa doctor`                           | `cli.py` → `doctor.py`: `.env`, TF ping, endpoint `/v1/models`, fallbacks, bucket, SDK auth | —                                               |
| 1–2 Deploy     | Console (template)                       | — (`AFTER_THE_WORKSHOP.md` documents BYOC `job/Dockerfile` as the container example)       | image · Sana on L40S                            |
| 3 One card     | `santa card --form` · or service UI      | `card.py`: gift+wish (TF) → image (endpoint) → Pillow render → `card.png` + `card.html`   | llm · TF; image · Sana endpoint                 |
| 4 Echo         | Console / `nebius echo`                  | — (skills vendored under `skills/` for their agent)                                        | —                                               |
| 5 Agent        | `santa agent "…"`                        | `agent.py` (Pydantic AI, ≤40 lines) · `mcp.py` shim for Claude Code / Cursor              | llm · TF (tool-calling model); image · Sana     |
| 6 Batch        | `santa batch --kids 20 --jobs 4`         | `batch.py`: cards for N kids (thread pool, pool) → upload → K GPU Jobs (`job.py`) → `run_summary.json` | video · Wan **in the Job**; audio · ACE-Step endpoint |
| 7 Video card   | `santa animate out/card.png`             | `animate.py`: Wan endpoint `/v1/videos` (async) + ACE-Step → `mux.py` → `card.mp4`         | video · Wan on H100; audio · ACE-Step on H100   |
| Wall           | `--publish`                              | `storage.py` uploads → `santa-service /wall` lists bucket                                  | —                                               |
| 8 Keep building| —                                        | `WORKSHOP.md`, `AFTER_THE_WORKSHOP.md`, `notebooks/`                                       | —                                               |

## 3. Target layout

```text
santa-scale-challenge/
├── config/
│   ├── models.yaml            # roles llm/image/video/audio, each with `fallback:` · job    (W1)
│   └── prompts.yaml           # image prompt, motion prompt, mood→music prompt
├── santa/                     # one package, three runtimes (CLI · service · job)
│   ├── cli.py                 # typer: doctor card agent batch animate publish teardown
│   ├── config.py              # models.yaml + .env → Settings (pydantic-settings)
│   ├── models.py              # adapters + Resilient(primary, fallback): openai_chat · openai_images · wan_omni · openai_video · acestep_audio · local_tracks
│   ├── schemas.py             # KidProfile GiftRecommendation Wish CardImage GiftCard (lifted from prototype)
│   ├── prompts.py             # lifted from prototype/src/prompts.py
│   ├── card.py                # process_kid v2: TF → image → render
│   ├── render.py              # Pillow renderer → PNG; Jinja → HTML with OG tags   (replaces html2image)
│   ├── agent.py               # Pydantic AI, 4 tools, ≤40 lines                     (W7)
│   ├── mcp.py                 # FastMCP shim: generate_card tool                     (Step 5 fallback)
│   ├── animate.py             # Wan async submit/poll + ACE-Step + mux
│   ├── mux.py                 # imageio-ffmpeg: mp4 + mp3 → mp4
│   ├── batch.py               # chunk → K jobs → wait → run_summary.json            (W3)
│   ├── nebius_jobs.py         # create_and_wait / cancel / timeline — ported from dubbing repo
│   ├── cost.py                # preset → $/h — ported
│   ├── storage.py             # boto3: upload/exists/list; staged_write for FUSE
│   ├── job.py                 # Job entrypoint: `python -m santa.job --chunk /data/runs/<id>/chunks/k.json`
│   ├── doctor.py
│   └── service/               # FastAPI (from santa_demo): UI form, /api/cards, /wall
├── docker/
│   ├── job.Dockerfile         # santa-job: CUDA + diffusers + santa; also the BYOC example
│   └── service.Dockerfile     # santa-service: CPU image
├── notebooks/                 # was prototype/ — research notebooks kept, + 01_text_to_image · 02_image_to_video · 03_text_to_music · 04_video_generation; import `santa`
├── skills/                    # vendored Serverless AI skills + README (Echo prompts)     (§1.6)
├── scripts/                   # make_fallbacks.py · bench_tool_calling.py · make_mood_bank.py · sync_models.py · teardown.sh (W9)
├── data/                      # kids.csv (200) · fallback/ (cards, mp4, mp3, run_summary.json) · out/ (ignored)
├── tests/
├── .env.example · WORKSHOP.md · AFTER_THE_WORKSHOP.md · README.md
```

`santa_demo/` is folded into `santa/service/`. `prototype/` becomes `notebooks/` in the **last** issue: notebooks kept and re-pointed at `santa`, `prototype/src/` and `prototype/data/` removed. `sys.path` hack (`proto.py`) goes.

## 4. Design decisions

| #   | Decision                                                                                                                                                                                                                                                              | Why                                                                                                                     |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| D1  | **Roles in `models.yaml`, secrets in `.env`.** Code never names a model. Adapter per API shape: `openai_chat`, `openai_images`, `wan_omni`, `openai_video`, `acestep_audio`, `local_tracks`                                                                                | W1; a template swap = yaml edit                                                                                          |
| D2  | **Sana via OpenAI SDK** `images.generate(prompt, size="1024x1024", seed)` → `b64_json`. Verified shape in cookbook README                                                                                                                                              | Existing `ImageClient` already does this for `/v1` URLs; drop Recraft/TF branches                                        |
| D3  | **Wan via multipart** `POST /v1/videos/sync` (`input_reference`, `size=832x480`, `num_frames`, `fps=16`, `flow_shift=12`, `boundary_ratio=0.875`, guidance 1.0) → raw MP4. `animate` uses async `POST /v1/videos` + poll when available, sync as fallback              | Current `VideoClient` (JSON `image` field, `/videos/generations`) is wrong per README                                    |
| D4  | **ACE-Step via** `POST /v1/audio/generations` JSON (`task_type=text2music`, `thinking=false`, `audio_duration=8`, `inference_steps=8`, `audio_format=mp3`) → mp3 bytes                                                                                                | Verified shape; endpoint is single-worker (lock)                                                                        |
| D5  | **Mood bank instead of per-card music in batch.** `scripts/make_mood_bank.py` generates ~8 instrumental tracks (mood tags) once → `audio/moods/`. Jobs pick by the wish's mood; `animate` may generate fresh (`--fresh-music`)                                            | 200 × 8 s on a single-worker endpoint = 25+ min; bank = seconds. Still "audio role via endpoint"                         |
| D6  | **Batch = GPU Jobs run Wan inside the job** (diffusers `WanImageToVideoPipeline`), one chunk per job, `videos/{id}.mp4`, skip if exists (idempotent), `run_summary.json` with state transitions + cost. Preemptible                                                     | Your answer 2; W3; dubbing pattern                                                                                       |
| D7  | **Job model default `Wan2.2-I2V-A14B`** on `gpu-h100-sxm 1gpu-16vcpu-200gb` preemptible (same model as the endpoint); `Wan2.2-TI2V-5B` on L40S as yaml alternative                                                                                                     | Decision Q1: H100 by default. Pre-baked weights (D8) absorb the 35 GB cold start                                          |
| D8  | **Weights pre-baked to bucket** `models/` (`scripts/sync_models.py`, HF → bucket once); job sets `HF_HOME=/data/models`, downloads only if missing                                                                                                                       | Dubbing pattern; removes the per-job Hub pull. Approved                                                                  |
| D9  | **Cards for the batch: via the participant's CPU service** when `SANTA_SERVICE_URL` is set (`POST /api/cards/batch` writes `cards/` to the bucket), else the same thread pool runs locally (`--local` forces it)                                                        | Decision Q3: both, service default. Sana ≈ 1–3 s/img → 200 cards ≈ 4–10 min on one endpoint; no GPU job for images         |
| D10 | **Job submission via Nebius Python SDK** (`nebius` pkg), port `create_and_wait`; auth from `NEBIUS_IAM_TOKEN` (`nebius iam get-access-token`) with `doctor` check; CLI shell-out removed                                                                              | Typed states, timeline, cancel-on-exit; no stdout grepping. Approved; bucket mounted by `NEBIUS_BUCKET_ID`, our bucket   |
| D11 | **Pillow renderer** replaces html2image everywhere (CLI, service, job). HTML card keeps OG tags for sharing                                                                                                                                                             | Your answer 8; one renderer, no Chrome                                                                                  |
| D12 | **Agent:** Pydantic AI `OpenAIModel(provider=TF)`; tools bound to roles; `scripts/bench_tool_calling.py` runs the 4-tool card task ×10 on GLM-5.3-Flash, Nemotron-3.5-Lightning, DeepSeek-V4-Flash-0731, gpt-oss-120b → success rate + p50 latency → winner into `models.yaml` | Your answer 7                                                                                                           |
| D13 | **Fallback per role** (`fallback:` block; OpenAI by default: `gpt-4o-mini`, `gpt-image-1`, `sora-2`; audio → bundled `local_tracks`). `Resilient` wrapper: primary first, switch on `AdapterError` or when the primary isn't configured. `SANTA_FALLBACK=auto\|off\|only` | R4: nobody sits idle if an endpoint is cold or misbehaving; `only` lets Step 3 run before the endpoint is RUNNING            |
| D14 | **Service = same package** on `cpu-e2` regular VM in the participant's project; UI form uses the service's `.env` roles                                                                                                                                                | Your answer 2                                                                                                             |
| D15 | Core deps: `openai pydantic pydantic-settings pyyaml typer rich requests python-dotenv pillow jinja2 imageio-ffmpeg boto3 nebius pydantic-ai`. Groups: `service` (fastapi, uvicorn), `job` (torch, diffusers), `research` (mlflow, pandas, google-*)                     | W4: `uv sync` in a tent                                                                                                 |

## 5. Contracts

**`config/models.yaml`** — see the file; shape per role:
```yaml
roles:
  image:
    adapter: openai_images
    url_env: IMAGE_ENDPOINT_URL
    token_env: IMAGE_ENDPOINT_TOKEN
    model: sana
    options: {size: 1024x1024}
    fallback: {adapter: openai_images, base_url: https://api.openai.com/v1, api_key_env: OPENAI_API_KEY, model: gpt-image-1}
job: {image: …/santa-job:<tag>, model: Wan-AI/Wan2.2-I2V-A14B-Diffusers, platform: gpu-h100-sxm, preset: 1gpu-16vcpu-200gb, preemptible: true, mount_path: /data, hf_home: /data/models}
```

**`.env.example`** — Steps 0–5/7: `TOKEN_FACTORY_API_KEY`, `IMAGE_ENDPOINT_URL/TOKEN`, `VIDEO_ENDPOINT_URL/TOKEN`, `AUDIO_ENDPOINT_URL/TOKEN`. Fallbacks: `OPENAI_API_KEY`, `SANTA_FALLBACK`. Batch/service/publish: `SANTA_SERVICE_URL`, `NEBIUS_IAM_TOKEN`, `NEBIUS_PROJECT_ID`, `NEBIUS_SUBNET_ID`, `NEBIUS_BUCKET_ID`, `NEBIUS_BUCKET_NAME`, `AWS_*`.

**CLI**
```
santa doctor
santa card  --form | --profile me.json | --name --age --wish   [--publish] [--out out/]
santa agent "<request>"
santa batch --kids 20 --jobs 4 [--run-id …] [--no-wait] [--local]  → runs/<run_id>/summary.json  (--local: cards from laptop even if SANTA_SERVICE_URL is set)
santa animate out/card.png [--motion "…"] [--fresh-music] [--wait|--no-wait] [--publish]
santa publish out/…                                            → bucket → /wall
santa teardown [--dry-run]                                     (your endpoints + running jobs)
```

**Job contract** (`python -m santa.job`): env `RUN_ID`, `CHUNK=/data/runs/<run_id>/chunks/<k>.json` (list of card ids + moods), `HF_HOME`. Reads `cards/{id}.png`, writes `videos/{id}.mp4` via `staged_write` (tmp → rename), skips existing, appends `runs/<run_id>/jobs/<k>.json` (per-id status + seconds). Exit 0 even with per-card failures; non-zero only on setup failure.

**`run_summary.json`**: `run_id, kids, jobs[] {job_id, chunk, platform, preset, preemptible, state_transitions[], run_s, cost_usd, on_demand_cost_usd, done, skipped, failed}, totals, savings_usd`.

**Service API**: `GET /` UI · `POST /api/cards` (profile) → card json · `POST /api/cards/batch` (kids[] → cards to bucket, returns ids) · `POST /api/publish` · `GET /wall` · `GET /api/wall` (bucket listing: cards, videos, latest run summary).

## 6. Reuse

| From                              | Kept                                                                                            | Dropped                                              |
| --------------------------------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| `santa_demo/` (current branch)    | FastAPI app + templates → `santa/service/`; `DemoSession` seam idea; test fakes; `fallbacks.py` | `jobs.py` (shell-out), `video.py` (wrong API), `proto.py` |
| `prototype/src`                   | `data_scheme`, `prompts`, `generators`, `llm_client` (as `openai_chat` adapter), `generate_kids` | `card_formatter` html2image path, Recraft/TF image branches, mlflow logging |
| dubbing repo                      | `nebius.py` → `nebius_jobs.py`; `cost.py`; `storage.staged_write`; `run_summary` shape; `sync_models.py` | Hatchet                                             |

## 7. Implementation issues (proposed `.scratch/workshop-media-gen/issues/`)

| NN  | Issue                                                                                              | Blocked by | Size |
| --- | -------------------------------------------------------------------------------------------------- | ---------- | ---- |
| 01  | Package `santa/`: config (`models.yaml` + `.env`), schemas/prompts lifted, adapters `openai_chat` + `openai_images`, `doctor` | —          | M    |
| 02  | `card.py` + Pillow `render.py` + HTML/OG; `santa card` CLI; `data/fallback` real cards               | 01         | M    |
| 03  | Dependency split + `pyproject` cleanup + `.env.example` + `.gitignore` (`.env`, `*.pkg`)             | 01         | S    |
| 04  | `service/`: fold `santa_demo`, `/api/cards`, `/api/cards/batch`, `docker/service.Dockerfile`, deploy as CPU endpoint | 02       | M    |
| 05  | Adapters `wan_omni` (sync + async) + `acestep_audio` + `mux.py`; `santa animate`                     | 01         | M    |
| 06  | `scripts/bench_tool_calling.py`; `agent.py` (Pydantic AI); `mcp.py` shim; `santa agent`              | 02         | M    |
| 07  | `nebius_jobs.py` + `cost.py` port; `storage.py`; `santa batch` cards phase (service or local thread pool) + upload | 02   | M    |
| 08  | `docker/job.Dockerfile` + `santa/job.py` (diffusers Wan I2V, mood bank, mux, idempotent, staged write); `sync_models.py`; push image | 05, 07 | L |
| 09  | `santa batch` jobs phase: chunk → K jobs → wait → `run_summary.json`; kill-one → re-run fills gap test | 07, 08   | M    |
| 10  | `scripts/make_mood_bank.py`; `--publish` + `/wall`                                                   | 04, 05     | S    |
| 11  | `data/kids.csv` (200) via lifted `generate_kids`; `data/fallback/` mp4 + mp3 + `run_summary.json` from a real run | 02, 09 | S |
| 12  | `notebooks/` ×4 (text-to-image, image-to-video, text-to-music, video generation) using `santa` adapters | 05       | S    |
| 13  | `skills/` vendored + `scripts/teardown.sh` + `santa teardown`                                        | 07         | S    |
| 14  | `WORKSHOP.md`, `AFTER_THE_WORKSHOP.md`, README rewrite, `AGENTS.md`/`CONTEXT.md` update              | 01–13      | S    |
| 15  | **Last:** `prototype/` → `notebooks/`; research notebooks re-pointed at `santa`; `prototype/src/`, `prototype/data/` removed | 12, 14 | M |

Critical path: 01 → 02 → 07 → 08 → 09 (batch). 05 and 06 parallel. 08 needs a live GPU to validate the pipeline in-container. 15 is last on purpose — it deletes the code the old notebooks import.

## 8. Tests (fakes at the adapter seam, no cloud in CI)

- Adapters: request-shape tests against recorded fixtures (Sana JSON, Wan multipart fields incl. `input_reference`, ACE-Step JSON); response parsing (b64, raw mp4, mp3).
- `card.py`: GiftCard from fakes; image attributed to the configured endpoint; primary failure → fallback used and recorded in metrics.
- `batch.py`: chunking 20/4 → 4 chunks; idempotent skip when `videos/{id}.mp4` exists; one job ERROR → summary still has 3 done + failed ids; cost math.
- `job.py`: run against a fake pipeline on 2 PNGs → 2 mp4 via staged write; mood pick deterministic.
- `agent.py`: tool-call sequence with a scripted fake model.
- Service: routes call the session (thin).

## 9. Decisions log

| #   | Question                                   | Decision (2026-09-07)                                              |
| --- | ------------------------------------------ | ------------------------------------------------------------------ |
| Q1  | Job video model                            | `Wan2.2-I2V-A14B` on H100 preemptible by default; 5B/L40S in yaml  |
| Q2  | Pre-bake weights to bucket                 | Yes — `scripts/sync_models.py`, `HF_HOME=/data/models`             |
| Q3  | Batch cards: CLI or service                | Both; default = CPU service (`/api/cards/batch`), `--local` opt-in |
| Q4  | Jobs auth                                  | `NEBIUS_IAM_TOKEN` via `nebius iam get-access-token`; `doctor` checks TTL |
| Q5  | Bucket mount                               | `NEBIUS_BUCKET_ID` volume at `/data`; our bucket for the demo      |
| Q6  | Music in batch                             | Mood bank (default if unanswered)                                  |
| Q7  | Video defaults                             | 832×480 @16 fps, 81 frames; motion prompt in `config/prompts.yaml` |
| Q8  | Rename + lift prototype modules            | Approved; `prototype/` untouched                                   |
| Q9  | Agent ≤40 lines via tools in `card.py`     | Yes                                                                |
| Q10 | `--publish` path                           | Via service `POST /api/publish` (no S3 creds on laptops); `--local` uses own creds |
| R1  | Shared / ours / theirs                     | Removed. Every participant runs every scenario in their own account; no `--shared`, no pool |
| R2  | Dockerfiles                                | All under `docker/` (`job.Dockerfile`, `service.Dockerfile`)                                |
| R3  | `prototype/`                               | → `notebooks/`, last issue (15): notebooks kept + video-generation notebook, `src/`+`data/` removed |
| R4  | Model fallbacks                            | Every role has `fallback:`; OpenAI default (`gpt-4o-mini`, `gpt-image-1`, `sora-2`); audio → bundled tracks; `SANTA_FALLBACK=auto\|off\|only` |
