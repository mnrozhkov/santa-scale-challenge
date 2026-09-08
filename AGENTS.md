## Agent skills

### Issue tracker

Issues and specs live as markdown under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical roles, same strings: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Glossary: `CONTEXT.md` at the repo root (KidProfile, GiftCard, role, adapter, run, chunk, mood bank). ADRs: `docs/adr/` when present. See `docs/agents/domain.md`.

### Serverless AI skills

Load `skills/serverless-ai` (or vendored paths) when inspecting or stopping the participant's Nebius endpoints and jobs. Cleanup: `santa teardown`. Echo prompts: `skills/README.md`.

### Superseded specs

`.scratch/presenter-serverless-demo` is superseded by `.scratch/workshop-media-gen` (participant-owned endpoints, `santa/` package, no SkyPilot presenter app).
