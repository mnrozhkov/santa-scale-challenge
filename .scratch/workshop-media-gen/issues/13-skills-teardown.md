# 13: `skills/` vendored Serverless AI skills + `scripts/teardown.sh` + `santa teardown`

**What to build:** A participant's coding agent can load the Serverless AI skills from the repo to inspect endpoints and jobs; after the session `santa teardown` stops the participant's endpoints, cancels lingering jobs and lists leftovers.

**Blocked by:** 07

**Status:** ready-for-human

- [x] `skills/` vendored from `nebius/skills` + `serverless-factory/cookbook/skills` (Serverless AI subset) with a README and Echo prompt list; `AGENTS.md` section on loading them
- [x] `scripts/teardown.sh` + `santa teardown [--dry-run]`: list endpoints/jobs in the project, stop/cancel, print what remains and estimated $/h saved
- [ ] Tested on a rehearsal project

## Comments

- Upstream skills were missing: `github.com/nebius/skills` 404; `nebius/serverless-ai-cookbook` has no `skills/` or `.claude/skills` tree (only sample workloads). Local skill at `skills/serverless-ai/SKILL.md` plus Echo prompts in `skills/README.md`.
- `santa/teardown.py` implements `run(..., endpoints, jobs)` with SDK ports (`SdkEndpointPort` / `SdkJobPort`). `scripts/teardown.sh` calls `uv run python -m santa.teardown`. CLI: `santa teardown [--dry-run]`.
- Tests use fake ports only (`tests/test_santa_teardown.py`). Rehearsal-project checkbox left unchecked on purpose.
