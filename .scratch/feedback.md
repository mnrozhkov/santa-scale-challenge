# Feedback parking lot

Append ideas, quality notes, and feature requests here. Do **not** turn them into specs or tickets until v1 (including `santa animate_batch`) has been tested.

Newest first. One dated block per dump. Use glossary terms (KidProfile, GiftCard, Wish, role, mood bank, run).

---

## 2026-09-10 — prototype UI real mode (next steps)

Integrated `_DEV/app` into `santa-service` with a Sim/Real toggle. Real mode wires Gallery, Magic (GiftCard), Animate, and Let it snow (Jobs). Kept the prototype in `_DEV/app` unchanged.

Not in Real mode yet (graph still shows request/result nodes, not a live stream):

- **Log streaming.** The LOG panel is Sim-only. Real mode has no SSE/`santa doctor` tail. Add a `/api/runs/{id}/events` stream (adapter latency, job state transitions) and restore the LOG panel.
- **Live DAG during a card.** Magic waits for `POST /api/cards` then paints llm/image/bucket as done. No per-step events while Token Factory / Sana run.
- **Wan poll progress.** Animate is one blocking `POST /api/cards/{id}/animate`. No `/v1/videos` progress % on the Wan node.
- **Let it snow card phase.** Real Let it snow is Jobs-only over published `cards/{id}/card.png` (same as `santa animate_batch`). It does not generate GiftCards from `kids.csv`. Generating N cards then submitting Jobs would match the Sim graph.
- **Interests / city / mood on KidProfile.** Real Magic appends them onto `wishlist` text. They are not schema fields, so Gallery filters are inferred from wish/gift keywords.
- **Cold Sana toggle** is Sim-only. Real fallback is `SANTA_FALLBACK` + adapter metrics after the call.

---

## 2026-09-09 — media quality after first live cards / animate

Source: live GiftCards (`out/529c7874-…`, `out/ec493971-…`) and `santa animate … --mood-bank`. Illustrations from the image role looked good; the composed card and the MP4 did not.

### GiftCard face looks like dumped model output

- Wish text is too long. Pillow wraps at width 42 and **hard-cuts at 8 lines**, so the letter ends mid-sentence (“just for”, “may your heart be as”) and then the gift bullets start. Inconsistent from card to card.
- The Wish prompt already says mention gifts magically and do not list them. `gpt-oss-120b` still enumerates every gift in the prose, then render prints the same gifts again as `•` lines. Reads like a system-prompt result, not a card.
- Layout is one flowing column with no reserved regions, so long Wishes collide with the gift list and leave empty right-hand space.

Ideas (not a plan): cap Wish length in the prompt and/or schema; fixed text box that always fits; treat the gift list as a designed footer (or drop it from the PNG if the Wish already covers it).

### Image role still paints letters sometimes

Prompt says no text / no letters. Some illustrations still get garbled fake words on the art (e.g. “Charisttca”). Parked — pictures were otherwise fine.

### Video barely moves

`santa animate` posts the **composed** GiftCard PNG (illustration + truncated Wish + bullets) as `input_reference`. Motion prompt asks for object-centric storybook motion and no text. I2V then has to hold letters still, so the clip is almost a still.

Ideas: keep an illustration-only PNG next to `card.png` and send that to the video role; stronger motion prompt / Wan options only after the input is the scene, not the letter.

Adapters now letterbox the reference to the role `size` (and JPEG if the PNG would trip nginx’s 1m body). That fixed 413 / Sora “inpaint image must match width and height”. It does not add motion.

### Soundtrack is a test tone

`--mood-bank` (and Jobs) pick `data/fallback/moods/<mood>.mp3`. Those files are **8s sine placeholders**, not music. Issue 10 already says regenerate with `scripts/make_mood_bank.py --force` against the audio role (ACE-Step), or replace with real instrumentals.

Ideas: commit royalty-free tracks per mood tag; or generate the bank once and check it in / upload to `audio/moods/`. Default `--mood-bank` should not sound like noise. Live ACE-Step per card (`--fresh-music`) is a separate path — prompts in `config/prompts.yaml` `music:` may still need work if that output is noisy too.

### Later

Do not `/to-tickets` this file until v1 + batch is tested.
