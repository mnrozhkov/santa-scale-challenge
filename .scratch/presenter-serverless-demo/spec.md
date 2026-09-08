# Presenter demo: Serverless media gen (card + video endpoint + 4 GPU Jobs)

Status: superseded

Superseded by `.scratch/workshop-media-gen` (2026-09). The presenter-operated local demo (SkyPilot removed, shared `santa_demo` app, Recraft unused) was folded into the workshop: every participant runs CLI + CPU service + GPU Jobs in **their** account. See `spec.md` there, `README.md`, `WORKSHOP.md`.

Do not implement issues in this folder.

## Problem Statement

I need a presenter-operated demo that shows how media generation runs on Nebius Serverless — one personalized Santa gift card from an image endpoint, one clip from a video endpoint, and a short burst of parallel GPU Jobs for batch video — before we lock the Nordic Tech Week workshop format. Today the repo is a SkyPilot + Recraft batch pipeline. It cannot show those three Serverless patterns from a laptop browser.

## Solution

A local presenter web app (no login) on my machine. I fill a kid form and get a GiftCard (HTML + PNG) whose illustration comes from our Serverless image endpoint, using the existing `process_kid` engine and Token Factory for gift recommendation and wish. I can animate a card through our Wan video endpoint, and I can submit four GPU Jobs (Wan container, one PNG each) and watch clips land. Four fallback cards ship with the demo; I can optionally fold in the last live card. SkyPilot is removed. Recraft is not a demo path. Workshop run-of-show, tenant model, and the workload agent stay parked.

## User Stories

1. As a presenter, I want a local web app I start on my laptop, so that I can run the demo without deploying a public site first.
2. As a presenter, I want the app to require no login, so that I am not debugging auth on stage.
3. As a presenter, I want a single screen with the three scenarios, so that I do not flip between tools mid-demo.
4. As a presenter, I want to enter a kid’s name, age, and wish (or childhood wish), so that the card is a real KidProfile, not a canned prompt.
5. As a presenter, I want invalid age or empty name rejected before any model is called, so that I do not burn endpoint time on a bad form.
6. As a presenter, I want Token Factory to produce a GiftRecommendation, so that the card has a reasoned gift, not a hardcoded toy.
7. As a presenter, I want Token Factory to produce a Wish, so that the card has personal copy.
8. As a presenter, I want the illustration generated on our Serverless image endpoint, so that S1 proves “media gen on Serverless,” not a closed API.
9. As a presenter, I want the UI to call `process_kid` as it exists, so that gift, wish, image, and card assembly stay one pipeline.
10. As a presenter, I want the GiftCard PNG from html2image on my machine, so that S2 and S3 have a raster to animate without changing the engine.
11. As a presenter, I want the HTML the formatter already builds saved and viewable, so that I can show a shareable card page.
12. As a presenter, I want the last GiftCard visible on the screen (image + wish + gifts), so that the room sees the artifact, not a log line.
13. As a presenter, I want a clear error if the image endpoint URL or its token is missing, so that I do not silently fall back to Recraft.
14. As a presenter, I want a clear error if Token Factory is missing or fails, so that I can switch to a fallback card and keep talking.
15. As a presenter, I want Recraft unused by this UI, so that I cannot accidentally demo the old backend.
16. As a presenter, I want “animate this card” to send the current PNG to the Wan video endpoint, so that S2 shows endpoint-based video.
17. As a presenter, I want animate to use a fallback PNG if I have not run S1, so that video still works if card generation failed.
18. As a presenter, I want the MP4 to play in the page when the endpoint returns, so that S2 is visible, not a download scavenger hunt.
19. As a presenter, I want a clear error if the video endpoint URL or token is missing or cold-fails, so that I can skip to S3 or a pre-made clip.
20. As a presenter, I want batch video to submit four GPU Jobs, so that S3 is visibly parallel, not one container looping.
21. As a presenter, I want each Job to take one PNG and run the Wan container, so that the pattern is “Job = one video,” not “Job = call our endpoint.”
22. As a presenter, I want those four PNGs to default to committed fallback GiftCard rasters, so that S3 always has fuel.
23. As a presenter, I want an “include last card” option that swaps the live PNG into the set when it exists, so that a card we just made can appear in the burst.
24. As a presenter, I want “include last card” ignored (or disabled) when there is no live PNG, so that I do not submit a broken Job.
25. As a presenter, I want the UI to show four Job identities and states as they run, so that the room sees Serverless Jobs, not a spinner.
26. As a presenter, I want each finished Job’s MP4 to appear as it lands, so that parallelism is obvious.
27. As a presenter, I want a failed Job not to hide the others, so that one preemption or timeout does not kill the scene.
28. As a presenter, I want Job outputs in object storage, so that clips survive the local process and match how Jobs actually write.
29. As a presenter, I want GPU Jobs eligible for preemptible, so that the cost line we tell is true (CPU Jobs are not preemptible).
30. As a presenter, I want K fixed at four for this spike, so that quota is predictable.
31. As a presenter, I want environment variables to be the only config, so that I am not maintaining a model registry before the workshop pass.
32. As a presenter, I want the app to fail fast on missing required env (Token Factory, image endpoint, video endpoint, Job/project/storage creds for batch), so that I discover that in rehearsal, not on stage.
33. As a presenter, I want SkyPilot configs and the SkyPilot dependency gone, so that the repo cannot launch the old cluster path by mistake.
34. As a presenter, I want the existing prototype left as the engine, so that KidProfile, clients, prompts, and `process_kid` are not rewritten for the demo.
35. As a presenter, I want to run the happy path on localhost first, so that deploy-as-a-CPU-endpoint is optional later.
36. As a presenter, I want no participant accounts or multi-tenant project logic in this app, so that workshop tenancy stays out of the spike.
37. As a presenter, I want no agent step in this app, so that the dropped agent stays an open question, not half-built UI.
38. As a presenter, I want no Echo integration in this app, so that Echo remains a Console helper later, not a fake workload agent.
39. As a presenter, I want no music generation or mux step, so that S2/S3 stay video-only.
40. As a presenter, I want no CPU card-batch Jobs in this app, so that “dozens of card Jobs” is not a live scenario yet.
41. As a presenter, I want no BYOC deploy flow in this app, so that template-vs-container stays a Console talking point.
42. As a later follower (out of this spec’s build, but a constraint), I want the demo not to assume I will run the four-Job burst, so that we do not design S3 as a participant reproduce-the-burst exercise.
43. As a later follower, I want the lasting hold to be “my media endpoints + one HTML GiftCard,” so that this demo does not quietly require me to ship MP4s or Jobs.
44. As a maintainer, I want fallback rasters generated once and committed (or a one-shot generate command), so that a clean checkout can run S3.
45. As a maintainer, I want fakes at the demo-session seam, so that CI does not call Token Factory, endpoints, or Job create.
46. As a maintainer, I want existing evaluation notebooks and Recraft helpers left alone, so that v1 research does not break.
47. As a maintainer, I want job and endpoint resources taggable for later teardown, so that a rehearsal does not leave orphan GPUs (teardown script itself can be thin).
48. As a maintainer, I want the workshop PRD left as draft context, so that this spike does not pretend the eight-step tent script is approved.

## Implementation Decisions

- Build a presenter web app (FastAPI + server-rendered pages) that talks only to a **demo session** module. The session is the product API; the web layer is a thin driver.
- The demo session exposes three actions: generate a GiftCard from a KidProfile; animate one PNG via the video endpoint; submit a four-way GPU Job batch for video.
- Generate delegates to existing `process_kid` with an injected LLM client (Token Factory) and an injected ImageClient aimed at the Serverless image endpoint. Do not fork gift/wish/image prompt logic.
- ImageClient is configured from env (endpoint URL + token). Treat the endpoint as OpenAI-compatible images. Do not select Recraft from the UI or as a fallback.
- Accept `process_kid`’s current finish: html2image PNG plus the HTML the card formatter already produces. Chrome/html2image is a presenter-machine dependency, not a participant one.
- Animate reads the live GiftCard PNG if present, otherwise a fallback raster. It calls a small video-endpoint adapter (image-to-video, OpenAI-shaped if the template allows; if not, one adapter for that template). No audio role.
- Batch video always starts from four committed fallback rasters. If “include last card” is on and a live PNG exists, replace one slot with that PNG. Submit four GPU Jobs, one PNG each, Wan container as the Job image (not four CPU Jobs calling the video endpoint). Poll status and surface MP4 locations from object storage.
- Persist session leftovers in process memory plus local output dir: last GiftCard, last endpoint MP4, last batch Job handles. Restarting the app clears “last card.”
- Configuration is environment variables only: Token Factory, image endpoint URL/token, video endpoint URL/token, object storage, Nebius project/Job credentials, Job image reference. No model registry file in this spike.
- Remove SkyPilot: drop the SkyPilot dependency group and the SkyPilot job manifests. Do not remove prototype modules, notebooks, or Recraft client code.
- Do not add a model registry, doctor CLI, MCP shim, shared-UI auth, wall, or credits redemption.
- Localhost is the acceptance bar. A later Serverless CPU deploy of this app is allowed but not required to close the spec.
- Domain types stay KidProfile, GiftRecommendation, Wish, CardImage, GiftCard. Do not introduce a “postcard” model.

## Testing Decisions

- Good tests assert **external behavior of the demo session**: given a KidProfile and fakes, a GiftCard comes back with illustration attributed to the image endpoint client (not Recraft); animate returns an MP4 from the video fake; batch submit is invoked four times with the fallback set, or three fallbacks plus the live PNG when the flag is on; missing image-endpoint env fails before any Recraft client is constructed; one Job failure leaves the other three results visible.
- Do not test template HTML, CSS, or OpenAI/Nebius wire formats. Do not re-unit-test `process_kid` internals (gift JSON parsing, html2image). Do not hit live Token Factory, endpoints, or Job create in CI.
- **Single seam:** the demo session façade. Inject fakes for LLM, ImageClient, video endpoint, Job runner, and storage. The web app is covered only by a thin “routes call the session” check if cheap; not a second behavioral suite.
- Prior art is thin: existing test samples only build KidProfile / GiftRecommendation fixtures for notebooks. Reuse those fixture helpers for KidProfiles. There is no existing pytest suite around `process_kid`; do not start one unless a session test is blocked by an untestable `process_kid` (then wrap, don’t rewrite).

## Out of Scope

- Workshop format, eight-step clock, live-deploy cap, pre-email, credits, printed table cards, participant follow-along CLI.
- Whose Nebius project (individual vs shared); lock later.
- Workload agent (Pydantic AI, MCP). Keep as an open question.
- Echo as anything but a future Console talking point.
- CPU card-batch Jobs, music generation, mux, BYOC image, image-edit, model registry file, doctor CLI.
- Recraft as a demo backend; SkyPilot as a run path.
- Deploying the presenter app as a public CPU endpoint (optional follow-on).
- Rewriting the workshop PRD to match this spike.

## Further Notes

- Test seam (confirmed): one demo session façade. Presenter UI and tests both call it. Card generation delegates to existing `process_kid`. Video endpoint and four-job submit/poll sit behind the same façade. Not tested: FastAPI templates, Nebius SDK internals, Recraft, SkyPilot.
- Public Luma still promises “connect the deployed model to an agent.” That is explicitly dropped from this spec and remains an open question for the workshop pass.
- One-off video is the Wan **endpoint**. Batch video is **Jobs** as a separate pattern. Followers are not expected to reproduce the Job burst.
- Preemptible is GPU-only. Do not claim a preemptible discount on CPU workers. The honest cost line for S3 is GPU Job-seconds (and preemptible Sana endpoints when we talk deploy later).
- Fallback rasters must exist before S3 is demoable; generating them is a staff prerequisite, not a live tent step.
