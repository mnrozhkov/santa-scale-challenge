# 14: `WORKSHOP.md`, `AFTER_THE_WORKSHOP.md`, README, `AGENTS.md`/`CONTEXT.md`

**What to build:** The repo reads participant-first: README is one screen (what it is, `uv sync`, `santa doctor`, `santa card`), `WORKSHOP.md` is the eight steps with copy-paste commands, `AFTER_THE_WORKSHOP.md` covers stop/start and cost, calling your endpoint with the OpenAI SDK, swapping a model in `models.yaml`, deploying video/audio yourself, BYOC via `job/Dockerfile`, and scaling the batch.

**Blocked by:** 01, 02, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13

**Status:** ready-for-human

- [x] README rewritten (participant-first, ≤1 screen + links); presenter/service/job docs moved to `docs/`
- [x] `WORKSHOP.md`: steps 0–8, one command block per step, expected output, "stuck? set `OPENAI_API_KEY` — fallbacks kick in"
- [x] `AFTER_THE_WORKSHOP.md`: stop/start, cost, OpenAI SDK call, swap model, deploy video/audio, BYOC, Jobs at scale, credits
- [x] `AGENTS.md` + `CONTEXT.md` glossary (KidProfile, GiftCard, role, adapter, run, chunk, mood bank); `.scratch/presenter-serverless-demo` marked superseded
- [ ] All commands in the docs executed once on a clean laptop
- [ ] Run a real `santa batch --kids 200 --jobs 40` (live GPU) — stub summary ships for `--offline`

## Comments

2026-09-08: Docs written against the `santa` CLI and `data/fallback/` stub assets. Offline commands (`santa card|animate|batch --offline`) were run. Live workshop (doctor + endpoints + 20/4 batch) left as a later checkbox.
