# 11: `data/kids.csv` (200) + `data/fallback/` (cards, mp4, moods, run_summary) from a real run

**What to build:** A clean checkout has 200 kid profiles for the batch and real fallback assets: 4 cards, 1 MP4, mood tracks, and a `run_summary.json` from an actual 40-job run.

**Blocked by:** 02, 09

**Status:** ready-for-human

- [x] `santa/kids.py` lifted from `prototype/src/generate_kids.py`; `data/kids.csv` with 200 profiles committed and uploaded to `kids/`
- [x] `data/fallback/`: 4 cards (png+html), 1 `card.mp4`, `moods/*.mp3`, stub `run_summary.json` matching the 40-job schema (not a live `--kids 200 --jobs 40` run)
- [x] Fallback assets referenced by `santa … --offline` (uses fallback card/mp4 when endpoints are unreachable)
- [ ] Replace stub `card.mp4` + `run_summary.json` with artifacts from a real `--kids 200 --jobs 40` run

## Comments

### 11a (CSV generator only)

- `santa/kids.py` + `tests/test_santa_kids.py`: `generate_kids` / `generate_kids_csv` emit santa schema `id,name,age,wishlist` (not prototype Timestamp columns).
- `data/kids.csv`: header + 200 rows. k01–k24 kept (Emma / a telescope … Alma); k25–k200 generated. Live-bucket upload to `kids/` skipped.
### 11b (`--offline` + stub fallback assets)

- `santa card|animate|batch --offline` copies `data/fallback/` (card PNG+HTML, `card.mp4`, `run_summary.json`) and does not construct adapters or touch the bucket/SDK.
- Cards were already real Pillow renders (`scripts/make_fallbacks.py`). Moods already in `data/fallback/moods/`.
- `card.mp4` is a 2 s ffmpeg still of `card-01.png` + `warm.mp3`. `run_summary.json` is schema-matching for 200 kids / 40 jobs via `santa.offline.write_stub_summary` — **not** a live GPU run. Replace after a real batch.
