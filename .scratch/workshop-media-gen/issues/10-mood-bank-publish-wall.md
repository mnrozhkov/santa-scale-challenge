# 10: `scripts/make_mood_bank.py`, `--publish`, `/wall`

**What to build:** Eight short instrumental tracks (one per mood tag) are generated once via the ACE-Step endpoint and stored in the bucket; jobs and `animate --mood-bank` pick from them so 200 videos don't queue 200 music calls on a single-worker endpoint. `--publish` on `card` and `animate` sends outputs to the bucket through the service; `/wall` shows them.

**Blocked by:** 04, 05

**Status:** ready-for-human

- [x] `scripts/make_mood_bank.py`: mood tags from `config/prompts.yaml` → 8 × 8 s mp3 → `audio/moods/<tag>.mp3` + `data/fallback/moods/`
- [x] Mood inference: wish text → tag (LLM call already made in `write_wish`, returns `mood` field)
- [x] `--publish` on `santa card` / `santa animate` → `POST /api/publish` (default) or direct S3 with `--local`
- [x] `/wall`: grid of cards + autoplaying muted MP4s + live counter from the latest `runs/*/summary.json`; auto-refresh 10 s

## Comments

Mood inference is already in `santa.card.write_wish` (LLM `mood` field, clamped to `MOODS`); covered by `tests/test_santa_card.py`. Not duplicated here. Live ACE-Step generation of the 8 tracks is still untested (fakes only). `data/fallback/moods/<tag>.mp3` are 8 s sine placeholders so `--mood-bank` and jobs work before the endpoint is run; regenerate with `scripts/make_mood_bank.py --force`.
Publish keys are `cards/{id}.png|.html` and `videos/{id}.mp4` (from `kid_id` or `out/<id>/card.*`), not `cards/card.png`.
