# 07: `nebius_jobs.py` + `cost.py` port, `storage.py`, `santa batch` cards phase

**What to build:** The batch command's first half works end to end without GPUs: `santa batch --kids 20 --jobs 4` picks 20 kids from `data/kids.csv`, gets their cards made (via the participant's service when `SANTA_SERVICE_URL` is set, otherwise — or with `--local` — from the laptop), uploads `cards/` to the bucket, and writes `runs/<run_id>/chunks/<k>.json`. Job submission primitives are in place and tested with fakes.

**Blocked by:** 02

**Status:** ready-for-human

- [x] `santa/nebius_jobs.py` ported from the dubbing repo: `create_and_wait`, `_wait_for_job_completion` (state timeline), `_cancel_nebius_job`, `NebiusJobError`; spec built from `job:` block (image, platform, preset, preemptible, disk, `/data` volume by `NEBIUS_BUCKET_ID`, env `RUN_ID`, `CHUNK`, `HF_HOME`)
- [x] `santa/cost.py` ported; H100 preemptible/on-demand + cpu-e2 rows verified against nebius.com/prices on the day
- [x] `santa/storage.py`: boto3 upload/exists/list/download + `staged_write` (tmp → rename) for FUSE
- [x] `santa batch` phase 1: select kids → `POST /api/cards/batch` (if `SANTA_SERVICE_URL`) or local thread pool (`--local` / unset) → skip kids whose `cards/{id}.png` exists → chunk ids into K → `runs/<run_id>/chunks/`
- [x] Tests: chunking 20/4, skip-existing, JobSpec built from yaml, timeline recording with a fake JobService

## Comments

- Cost rows checked 2026-09-07 against https://docs.nebius.com/compute/resources/pricing: H100 NVLink $3.85/GPU-h on-demand, $2.15 preemptible (from 1 June 2026); cpu-e2 Intel Ice Lake $0.012/vCPU-h + $0.0032/GiB-h (e.g. `2vcpu-8gb` = $0.0496/h).
- `data/kids.csv` is 24 rows so `--kids 20` works; issue 11 replaces this with 200 generated profiles.
- GPU job *submission* is not in this ticket (issue 09). `create_and_wait` is tested with a fake JobService.
- Bucket upload is required: without `NEBIUS_BUCKET_NAME` the CLI exits 1 (no MemoryStorage fallback). `--kids-csv` and `--out` are extra flags for tests and local runs.
