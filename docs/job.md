# GPU Jobs (`python -m santa.job`)

One Job = one **chunk** of card ids. Inside the container: Wan I2V (diffusers) → mood-bank mp3 → mux → `videos/{id}.mp4`. Preemptible H100 by default (`config/models.yaml` `job:`).

## Contract

Env: `RUN_ID`, `CHUNK=/data/runs/<run_id>/chunks/<k>.json`, `HF_HOME=/data/models`. Bucket FUSE-mounted at `/data` (`NEBIUS_BUCKET_ID`).

Reads `cards/{id}.png`. Writes `videos/{id}.mp4` via staged rename; skips if the object exists. Appends `runs/<run_id>/jobs/<k>.json`. Exit 0 even with per-card failures; non-zero only on setup failure.

`santa batch` submits K jobs and writes `runs/<run_id>/summary.json` (timelines, cost, savings vs on-demand).

## Build / push

See `docker/job.Dockerfile` (BYOC example) and [AFTER_THE_WORKSHOP.md](../AFTER_THE_WORKSHOP.md). Tag must be set in `job.image` before `santa batch`.
