# 09: `santa batch` jobs phase: K Jobs → wait → `run_summary.json`; kill-one → re-run fills the gap

**What to build:** `santa batch --kids 20 --jobs 4` submits 4 preemptible H100 Jobs at once, shows them in the terminal as they move QUEUED → RUNNING → COMPLETED/ERROR, and writes `runs/<run_id>/summary.json` with per-job timeline, run seconds, cost and on-demand comparison. Cancelling one job and re-running the same `--run-id` only re-processes the missing videos. `--kids 200 --jobs 40` is the same command.

**Blocked by:** 07, 08

**Status:** ready-for-human

- [x] Phase 2: submit K jobs concurrently (asyncio), live table (rich), `--no-wait` returns run id; `santa batch --status <run_id>` resumes polling
- [x] `run_summary.json`: `run_id, kids, jobs[] {job_id, chunk, platform, preset, preemptible, state_transitions[], run_s, cost_usd, on_demand_cost_usd, done, skipped, failed}, totals, savings_usd`; also copied to bucket `runs/<run_id>/summary.json`
- [x] Re-run with same `--run-id`: only ids without `videos/{id}.mp4` go into chunks; verified by cancelling one job mid-run
- [x] Ctrl-C cancels submitted jobs (ported cancel-on-exit)
- [x] Tests: summary math from fake records; one ERROR job → summary has 3 done + failed ids; re-run chunking excludes existing videos

## Comments

- Jobs phase is in `santa.batch.run_jobs_phase` / `resume_jobs_phase`. Creates and waits go through `asyncio.gather` + `to_thread` against `JobService`. CI uses a scripted fake; no cloud.
- Same `--run-id`: `ids_missing_videos` drops ids that already have `videos/{id}.mp4`, then re-chunks. Tested as ERROR-on-one-job then a second run that only submits the gap.
- `--no-wait` writes `ticket.json` (local + bucket) and prints `santa batch --status <run_id>`. Live table maps Nebius `PENDING` → `QUEUED`.
- Live GPU still depends on issue 08: `job.image` in `config/models.yaml` plus `NEBIUS_IAM_TOKEN` / bucket mount. Cost math uses the 2026-09-07 H100 rows ($2.15 preemptible / $3.85 on-demand).
