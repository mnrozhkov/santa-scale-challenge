# Skills

Load `skills/serverless-ai` in the participant's coding agent when inspecting or stopping Nebius endpoints and jobs. Cleanup: `santa teardown` (or `scripts/teardown.sh`).

Upstream `nebius/skills` and `nebius/serverless-ai-cookbook` (`skills/`, `.claude/skills`) had no Serverless AI skill tree to vendor (checked 2026-09-08). This folder is a local subset: endpoints, jobs, logs — not Token Factory finetune/observability.

## Echo prompts

Workshop Step 4 is Console / `nebius echo`. Paste one prompt at a time.

**List endpoints**

```
List every Serverless AI endpoint in my current Nebius project. For each, show id, name, state, platform, preset, and whether it is preemptible. Use `nebius ai endpoint list`.
```

**Stop endpoints**

```
Stop (do not delete) every RUNNING or STARTING Serverless AI endpoint in my current project. Print the ids you stopped. Use `nebius ai endpoint stop`.
```

**Cancel jobs**

```
Cancel every Serverless AI job in my current project that is not in a terminal state (COMPLETED, FAILED, CANCELLED, SUCCEEDED, ERROR, CANCELED). Print the ids. Use `nebius ai job cancel`.
```

**Estimate H100 cost**

```
Estimate the USD per hour of a running on-demand H100 Serverless AI endpoint (`gpu-h100-sxm`, preset `1gpu-16vcpu-200gb`). Then the preemptible rate for the same shape. Cite current Nebius compute pricing.
```
