# Playground notebooks

Workshop playgrounds (`01_`–`04_`) import `santa` adapters (`adapter_for`), not cookbook HTTP.
Research evals (`10_`–`14_`) import `santa.schemas`, `santa.prompts`, `santa.card`, `santa.models`, and `santa.eval`.

```bash
uv sync --group dev && uv run jupyter lab          # playgrounds
uv sync --group research --group dev               # eval notebooks (mlflow, pandas)
```

Open `notebooks/`. Secrets come from `.env` (same keys as `.env.example`).
Eval without endpoints: `SANTA_EVAL_FAKE=1`.

## Colab

Add userdata named like `.env.example` (`IMAGE_ENDPOINT_URL`, `IMAGE_ENDPOINT_TOKEN`, …).
The setup cell copies them into `os.environ`.

- [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mnrozhkov/santa-scale-challenge/blob/serverless/notebooks/01_text_to_image.ipynb) `01_text_to_image.ipynb` — Sana / image role
- [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mnrozhkov/santa-scale-challenge/blob/serverless/notebooks/02_image_to_video.ipynb) `02_image_to_video.ipynb` — Wan / video role
- [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mnrozhkov/santa-scale-challenge/blob/serverless/notebooks/03_text_to_music.ipynb) `03_text_to_music.ipynb` — ACE-Step / audio role
- [![Open In Colab](https://colab.research.google.com/github/mnrozhkov/santa-scale-challenge/blob/serverless/notebooks/04_video_generation.ipynb) `04_video_generation.ipynb` — card → clip → music → mux

Research: `10_prototype.ipynb`, `11_gift_rec_eval.ipynb`, `12_wish_model_eval.ipynb`, `13_image_generation_eval.ipynb`, `14_benchmark_llm.ipynb`.
