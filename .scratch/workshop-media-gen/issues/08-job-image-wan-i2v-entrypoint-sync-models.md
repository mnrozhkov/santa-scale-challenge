# 08: `santa-job` image + `santa.job` entrypoint (Wan I2V in-container, mood bank, mux, idempotent) + weight pre-bake

**What to build:** One GPU Job takes a chunk file, loads Wan2.2-I2V-A14B from the pre-baked cache on `/data/models`, and for each card id renders `videos/{id}.mp4` (video + music) with a staged write, skipping ids that already exist. A killed job re-run only fills the gaps. The same Dockerfile is the BYOC example referenced in `AFTER_THE_WORKSHOP.md`.

**Blocked by:** 05, 07

**Status:** ready-for-human

- [x] `docker/job.Dockerfile`: CUDA base + `santa[job]`; entrypoint `python -m santa.job`
- [x] `santa/job.py`: reads `CHUNK`, loads `WanImageToVideoPipeline` (model from `job.model`, `HF_HOME` on `/data/models`), per id: `cards/{id}.png` → video (832×480, 81 frames, motion prompt) → pick mood track from `audio/moods/` → mux → `staged_write(videos/{id}.mp4)`; skip if exists; per-id status → `runs/<run_id>/jobs/<k>.json`; exit 0 with partial failures, non-zero only on setup failure
- [x] `scripts/sync_models.py`: HF → local → bucket `models/` once (idempotent); job downloads only if cache is missing
- [ ] Image built for amd64, pushed to Container Registry; tag written to `config/models.yaml` `job.image`
- [ ] One real single-job run on H100 preemptible: cold start, per-clip seconds, cost recorded in the issue
- [x] Tests: `job.py` with a fake pipeline on 2 PNGs → 2 MP4s via staged write, second run skips both; mood pick deterministic

## Comments

- Code + CI tests are in. `python -m santa.job` is the entrypoint; fakes cover staged write, skip, mood pick, incremental `jobs/<k>.json`, and setup-failure exit codes. Torch/diffusers stay in `santa[job]` / the job group, not laptop core.
- Build (participant account, amd64): `docker build --platform linux/amd64 -f docker/job.Dockerfile -t santa-job:local .` then push to `cr.eu-north1.nebius.cloud/<registry>/santa-job:<tag>` and paste that into `config/models.yaml` `job.image`.
- Pre-bake: `uv run --with huggingface_hub scripts/sync_models.py` (HF → `.cache/hf` → bucket `models/`; existing keys skipped). Job sets `HF_HOME=/data/models` and uses `local_files_only` when the cache already has weights.
- Live H100 validation still needs a human: one preemptible `gpu-h100-sxm` / `1gpu-16vcpu-200gb` job, then record cold start, per-clip seconds, and cost here. On-demand $3.85/GPU-h, preemptible $2.15 (from `santa.cost`, 2026-09-07).
