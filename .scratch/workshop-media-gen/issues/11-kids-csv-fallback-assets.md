# 11: `data/kids.csv` (200) + `data/fallback/` (cards, mp4, moods, run_summary) from a real run

**What to build:** A clean checkout has 200 kid profiles for the batch and real fallback assets: 4 cards, 1 MP4, mood tracks, and a `run_summary.json` from an actual 40-job run.

**Blocked by:** 02, 09

**Status:** ready-for-agent

- [x] `santa/kids.py` lifted from `prototype/src/generate_kids.py`; `data/kids.csv` with 200 profiles committed and uploaded to `kids/`
- [ ] `data/fallback/`: 4 cards (png+html), 1 `card.mp4`, `moods/*.mp3`, `run_summary.json` from a real `--kids 200 --jobs 40` run
- [ ] Fallback assets referenced by `santa … --offline` (uses fallback card/mp4 when endpoints are unreachable)

## Comments

### 11a (CSV generator only)

- `santa/kids.py` + `tests/test_santa_kids.py`: `generate_kids` / `generate_kids_csv` emit santa schema `id,name,age,wishlist` (not prototype Timestamp columns).
- `data/kids.csv`: header + 200 rows. k01–k24 kept (Emma / a telescope … Alma); k25–k200 generated. Live-bucket upload to `kids/` skipped.
- Not in this slice: fallback cards/mp4/moods/`run_summary`, `--offline`. First checkbox marked done for the generator+CSV; upload remains a live step.
