# Santa Scale Challenge

Personalized holiday gift cards on **your** Nebius Serverless AI account: Token Factory for the wish, a Sana endpoint for the illustration, GPU Jobs for video, ACE-Step for music.

## Laptop

```bash
uv sync
cp .env.example .env   # paste Token Factory + endpoint URL/token (and OPENAI_API_KEY)
santa doctor
santa card --form
```

Stuck? Set `OPENAI_API_KEY` — fallbacks kick in. No endpoints yet? `santa card --offline`.

Next: **[WORKSHOP.md](WORKSHOP.md)** (steps 0–8). After the session: **[AFTER_THE_WORKSHOP.md](AFTER_THE_WORKSHOP.md)**.

## Layout

| Path | What |
| --- | --- |
| `santa/` | One package: CLI, CPU service, GPU job |
| `config/` | `models.yaml` (roles) + `prompts.yaml` |
| `notebooks/` | Playgrounds + research evals |
| `data/kids.csv` | 200 profiles for `santa batch` |
| `data/fallback/` | Offline cards, mp4, moods, run summary |
| `docker/` | `service.Dockerfile` · `job.Dockerfile` (BYOC) |
| `skills/` | Echo prompts + Serverless AI skill |

Ops: [docs/service.md](docs/service.md) (CPU UI / `/wall`) · [docs/job.md](docs/job.md) (GPU Jobs). Domain language: [CONTEXT.md](CONTEXT.md).

```bash
santa agent "make a card for a 7-year-old who wants a telescope"
santa animate out/<id>/card.png
santa batch --kids 20 --jobs 4
santa teardown --dry-run
```
