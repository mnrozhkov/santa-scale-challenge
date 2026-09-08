## Agent skills

### Issue tracker

Issues and specs live as markdown under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical roles, same strings: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Serverless AI skills

Load `skills/serverless-ai` (or vendored paths) when inspecting or stopping the participant's Nebius endpoints and jobs. Cleanup: `santa teardown`. Echo prompts: `skills/README.md`.
