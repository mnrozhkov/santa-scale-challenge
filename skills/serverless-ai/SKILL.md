---
name: serverless-ai
description: >-
  Inspect or stop the participant's Nebius Serverless AI endpoints and jobs.
  Use when listing, getting, stopping, or deleting endpoints; cancelling jobs;
  reading endpoint or job logs; estimating running GPU cost; or cleaning up
  with santa teardown.
---

# Serverless AI

Cleanup: `santa teardown` (or `scripts/teardown.sh`). `--dry-run` lists without stopping.

## CLI

Endpoints: `nebius ai endpoint list|get|stop|delete|logs`

Jobs: `nebius ai job list|get|cancel|logs`

Stop running/starting endpoints (do not delete unless asked). Cancel jobs that are not terminal (`COMPLETED` / `FAILED` / `CANCELLED` / `SUCCEEDED` / `ERROR` / `CANCELED`).

Auth: `NEBIUS_IAM_TOKEN`, `NEBIUS_PROJECT_ID`. Docs: https://docs.nebius.com/cli/reference/ai/endpoint and https://docs.nebius.com/cli/reference/ai/job

## This repo

| Role | Where |
| image | Sana L40S endpoint |
| video | Wan H100 endpoint |
| audio | ACE-Step H100 endpoint |
| santa-service | cpu-e2 endpoint |
| batch | preemptible GPU jobs |

Echo paste-prompts: `skills/README.md`.
