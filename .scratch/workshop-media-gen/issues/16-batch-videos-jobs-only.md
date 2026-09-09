# 16: `santa batch` is Jobs-only video inference (no GiftCard factory)

**Category:** enhancement

**Blocked by:** 07, 08, 09, 14

**Status:** ready-for-agent

**What to build:** After publishing GiftCards with the card command, a participant runs `santa batch --jobs 4` and gets K Nebius GPU Jobs that write `videos/{id}.mp4` from illustrations already in `cards/`. The command never manufactures GiftCards, never reads the kids CSV, and never POSTs to the CPU service.

Two workshop patterns stay unmixed: API inference on endpoints (`santa card`, `santa agent`, `santa animate`) versus batch inference on GPU Jobs (`santa batch`). GiftCards are never a Job and never a batch CLI.

- [x] `santa batch --jobs 4` inventories `cards/*.png`, skips existing videos, submits K Jobs, writes a run summary
- [x] Empty `cards/` exits non-zero with a publish hint (`santa card … --publish`)
- [x] `--kids`, `--kids-csv`, and `--local` are gone from `santa batch`
- [x] `santa doctor` warns/skips on an empty Job image tag with a docker build/push fix
- [x] Workshop Step 6 and README describe publish-via-API, then Jobs (no `--kids`)

## Problem Statement

`santa batch --kids 20 --jobs 4` does two jobs in one command. First it manufactures GiftCards (laptop thread pool, or HTTP to the CPU service which then calls the image endpoint). Then it submits Nebius GPU Jobs to animate those PNGs. When the Job image tag is empty, cards can still “succeed” (or skip) while Jobs never start. Workshop Step 6 therefore teaches the wrong lesson: that batch means “make a pile of cards, then maybe videos.”

Participants need to see:

1. One HTTP call to a running endpoint → one artifact (`santa card --publish`, `santa animate`).
2. K GPU Jobs over objects already in the bucket → many videos (`santa batch`).

A GiftCard batch command, `--kids`, or flags like `--images` / `--videos` would still mix those patterns.

## Solution

`santa batch` only submits Nebius AI Jobs (SDK `JobService`, IAM token). It lists GiftCard illustrations already in object storage under the `cards/` prefix, skips ids that already have `videos/{id}.mp4`, splits the rest into K chunks (default 4), and writes muxed MP4s plus a run summary.

Inputs to batch are bucket objects, not `kids.csv`. Filling `cards/` is repeated API calls: `santa card … --publish` (Step 3). One-video API demo stays `santa animate` (Wan endpoint), distinct from Wan-inside-the-Job.

Empty `cards/` is a hard error with a hint to publish a GiftCard first. `--kids`, `--kids-csv`, `--local`, and any POST to the CPU service card-batch route are removed from this command.

## User Stories

1. As a workshop participant, I want `santa batch` to mean GPU Jobs only, so I can see batch inference as a different pattern from calling an endpoint.
2. As a workshop participant, I want to publish GiftCards with `santa card --publish` (the same API path as Step 3), so the bucket has illustrations before I batch videos.
3. As a workshop participant, I want to run `santa batch --jobs 4` after publishing a few cards, so K independent Jobs animate whatever PNGs are in `cards/`.
4. As a workshop participant, I want the default job count to be 4, so the copy-paste in Step 6 matches the live table of four Jobs.
5. As a workshop participant, I want Jobs to skip ids that already have a video object, so a re-run of the same bucket only fills gaps.
6. As a workshop participant, I want an empty `cards/` prefix to fail with “publish a card first”, so I do not wait on Jobs that have nothing to animate.
7. As a workshop participant, I want `--kids` gone from `santa batch`, so I am not tempted to treat GiftCards as a Job.
8. As a workshop participant, I want `--kids-csv` gone from `santa batch`, so the CSV is not an input to batch inference.
9. As a workshop participant, I want `--local` gone from `santa batch`, so “run on the laptop” is not confused with submitting Jobs.
10. As a workshop participant, I want `SANTA_SERVICE_URL` to have no effect on `santa batch`, so the CPU service is not a hidden GiftCard factory for this command.
11. As a workshop participant, I want `santa animate` unchanged, so I can still demo one video via the Wan endpoint (API inference).
12. As a workshop participant, I want `santa card` unchanged, so one GiftCard is still gift rec + wish + illustration on endpoints.
13. As a workshop participant, I want mood-bank audio inside the Job (from the GiftCard JSON mood when present, otherwise warm), so batch videos still have music without calling ACE-Step per clip.
14. As a workshop participant, I want `--no-wait` and `--status <run_id>` to keep working on Jobs, so I can poll without tying up the tent laptop.
15. As a workshop participant, I want Ctrl-C to cancel submitted Jobs, so I do not leave GPUs running after a mistake.
16. As a workshop participant, I want `out/runs/<run_id>/summary.json` (and the same object in the bucket) with timelines and cost, so I can talk about preemptible vs on-demand.
17. As a workshop participant, I want `santa batch --offline` to still copy the stub summary, so Step 6 works with no cloud.
18. As a workshop participant, I want `santa doctor` to tell me when the Job image tag is empty, with a docker build/push hint, so I am not blocked by a silent yaml placeholder.
19. As a workshop participant, I want `santa doctor` to keep the IAM-token hint as `nebius iam get-access-token`, so I do not look for that token on an endpoint page.
20. As a workshop participant, I want Workshop Step 6 to show publish-via-API, then Job image + IAM, then `santa batch --jobs 4`, so the two patterns are consecutive copy-paste blocks.
21. As a workshop participant, I want README troubleshooting to say “publish GiftCards, then batch Jobs”, so I do not search for `--kids`.
22. As a facilitator, I want the wall to keep listing `cards/` and `videos/`, so published Step-3 GiftCards and batch MP4s still show up.
23. As a facilitator, I want no `santa cards` (plural) command, so we do not invent a second GiftCard factory.
24. As a facilitator, I want no `--images` / `--videos` flags on `batch`, so batch is not a mode switch.
25. As an implementer, I want inventory to be PNG keys under `cards/`, so Jobs are driven by objects that already exist.
26. As an implementer, I want chunk files to still be `{id, mood}` lists, so the Job entrypoint does not change.
27. As an implementer, I want the Job to keep reading `cards/{id}.png` and writing `videos/{id}.mp4`, so the container contract stays stable.
28. As an implementer, I want the CLI to construct the Job service only after inventory succeeds, so an empty bucket fails before IAM/image errors when possible (empty bucket is the first check; missing IAM/image still fail at submit).
29. As a service maintainer, I want `POST /api/cards/batch` unused by `santa batch`, so the workshop CLI does not teach HTTP batch-of-cards as Jobs. The route may remain for the CPU UI if it already uses it.
30. As a CI maintainer, I want tests to use a fake Job service and in-memory storage, so we never call Nebius in CI.
31. As a CI maintainer, I want no new tests that generate N GiftCards through `santa batch`, so the removed factory cannot regress back in via tests.
32. As a participant with some videos already in the bucket, I want K to shrink when fewer ids remain, so we do not submit empty Jobs.
33. As a participant whose Job image is unset, I want a readable error pointing at the Job Dockerfile build/push and the yaml image field, so I can finish Step 6 without reading old issue numbers.
34. As a participant, I want `--run-id` to still resume gap-fill on videos, so killing one Job and re-running is the same story as before.
35. As a reader of the architecture spec, I want D9 withdrawn (cards-via-service for batch) so the written decision matches the workshop.

## Implementation Decisions

- Two inference patterns, named by runtime: endpoints (one request, one artifact) versus Jobs (one image, a chunk of inputs, many videos). GiftCard production stays on the card command and optional `--publish`.
- `santa batch` options: job count (default 4), run id, no-wait, status, out directory, offline. Delete kids count, kids CSV path, and local-cards override from this command.
- Source of work for a run: PNG object keys under `cards/`. Stem of the key is the id. Skip ids that already have a non-empty `videos/{id}.mp4`.
- Empty inventory: non-zero exit; message tells the participant to publish a GiftCard with the card command.
- Chunking: existing even split into K lists of `{id, mood}`. Mood from the sibling GiftCard JSON when present, else `warm`. Upload chunk files under `runs/<run_id>/chunks/` as today.
- Job submission: existing Nebius Job SDK wrapper (bearer IAM token), not HTTP to the CPU service, not the Wan endpoint adapter. Preemptible H100 spec remains in the models yaml `job:` block.
- Job runtime contract unchanged: env `RUN_ID`, `CHUNK`, `HF_HOME`; mount at `/data`; Wan I2V in-container; mood-bank mux; staged write of `videos/{id}.mp4`.
- Remove the cards phase from the batch CLI (select kids → make GiftCards → optional service POST). Do not keep a public card-batch path on this command. Delete or stop exporting that phase if nothing else needs it.
- CPU service card-batch HTTP route: not called by `santa batch`. Leave it if the UI still posts there; do not document it as Step 6.
- Doctor: optional row when the yaml Job image field is empty; fix is build/push the Job Dockerfile for amd64 and paste the registry tag into that field. IAM row stays “mint access token via CLI, paste into env.”
- Workshop Step 6: (1) publish GiftCards via the card command, (2) Job image + IAM + bucket/project/subnet, (3) `santa batch --jobs 4` with the four-Job table and summary path. README batch blurb matches. Do not mention `--kids`.
- Wall and publish key prefixes stay `cards/` and `videos/`.
- Offline batch still copies the bundled summary and does not submit Jobs.
- Spec D9 (batch cards via CPU service / local thread pool) is withdrawn. Q3 likewise: GiftCards are not a batch decision.
- Domain glossary: a **run** is K Jobs over published GiftCard illustrations plus one summary — not “N kids.” The kids CSV generator is not an input to `santa batch`.
- Architecture CLI contract: `santa batch [--jobs 4] [--run-id …] [--no-wait] [--status …]` → run summary. No `--kids` / `--local`.
- The CPU service card-batch HTTP route is unused by the wall UI (the form posts a single GiftCard). `santa batch` must not call it. Leaving or deleting that route is allowed if service tests still cover a single-card API.
- Run summary may keep its existing id-list field name (avoid a rename sweep). Values are illustration ids from `cards/`, not a CSV row count.

## Testing Decisions

**Seam (one, highest):** the batch CLI + storage list/exists + a fake Job service. GiftCard generation is not on this seam. The Job entrypoint stays on its existing fake-pipeline tests (PNG under `cards/` → MP4 under `videos/`).

A good test observes external behavior: which bucket keys are listed, which Job specs are submitted (image, chunk path, count), skip/idempotency, and CLI exit text. It does not assert internal helper names or that a particular HTTP client was imported.

Modules under test: batch inventory + job phase, the batch CLI, doctor’s Job-image row. Job entrypoint tests stay on a fake pipeline and `cards/*.png` on a fake data root.

Prior art: existing batch tests that inject in-memory storage and a fake Job service; existing CLI runner tests for `santa batch`; doctor presence checks for IAM/project/bucket.

Required behaviors:

- `santa batch --jobs 4` with three PNGs in `cards/` and no videos submits Jobs whose chunks cover those ids and never calls GiftCard generation.
- Existing `videos/{id}.mp4` objects are omitted from chunks.
- No PNGs → non-zero exit mentioning the card command and `--publish`.
- `--kids` is not a valid option (Typer rejects it).
- Offline path still writes the stub summary.
- Doctor reports the empty Job image field with a docker build/push fix (not an old ticket number).

Do not add tests that drive N KidProfiles through `santa batch`.

## Out of Scope

- Any GiftCard batch CLI (`santa cards`, `--kids`, thread pool of card generation inside batch).
- Renaming the `cards/` prefix to `images/`.
- Generating GiftCards inside the GPU Job.
- Changing Wan-in-Job versus `santa animate` (keep both: Jobs = batch pattern, animate = API pattern).
- Building or pushing the amd64 Job image in CI, or writing a real registry tag into yaml (still a human / earlier Job-image ticket).
- A wrapper script for docker build.
- Deleting the CPU service or its UI form.
- Filling the mood bank or pre-baking weights (existing scripts).

## Further Notes

Live GPU validation (one preemptible Job, record cold start) remains on the Job-image ticket. This issue only stops mixing endpoint GiftCard manufacture into the Jobs command and retargets Step 6 copy-paste.

Chunk JSON shape `{id, mood}` is already what the Job entrypoint reads; inventory should produce that list from storage rather than from a CSV of KidProfiles.

## Comments

> *This was generated by AI during `/to-spec` (workshop plan: batch = video Jobs only).*

2026-09-09: `/to-spec` re-run against the issue file. Status stays `ready-for-agent`. Verified vs current CLI (still `--kids` + cards phase + service POST), Job entrypoint (`cards/{id}.png` → `videos/{id}.mp4`), doctor (IAM presence only; no Job image row), wall UI (no call to card-batch HTTP). Added glossary/`run` decision, CLI contract, unused service route, and acceptance checkboxes.

2026-09-09: Implemented. `santa batch` inventories `cards/*.png`, skips existing videos, submits K Jobs. GiftCard factory (`--kids`, `--kids-csv`, `--local`, `run_cards_phase`) removed. Doctor has a skip row for empty `job.image` with a docker build/push fix. Workshop Step 6 / README / AFTER_THE_WORKSHOP retargeted to publish-via-API then Jobs.
