# Playground notebooks

One notebook per media endpoint. They import `santa` adapters (`adapter_for`), not cookbook HTTP.

## Local

```bash
uv sync --group dev && uv run jupyter lab
```

Open `notebooks/`. Secrets come from `.env` (same keys as `.env.example`).

## Colab

Add userdata named like `.env.example` (`IMAGE_ENDPOINT_URL`, `IMAGE_ENDPOINT_TOKEN`, …).
The setup cell copies them into `os.environ`.

- [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mnrozhkov/santa-scale-challenge/blob/serverless/notebooks/01_text_to_image.ipynb) `01_text_to_image.ipynb` — Sana / image role
- [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mnrozhkov/santa-scale-challenge/blob/serverless/notebooks/02_image_to_video.ipynb) `02_image_to_video.ipynb` — Wan / video role
- [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mnrozhkov/santa-scale-challenge/blob/serverless/notebooks/03_text_to_music.ipynb) `03_text_to_music.ipynb` — ACE-Step / audio role
- [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/mnrozhkov/santa-scale-challenge/blob/serverless/notebooks/04_video_generation.ipynb) `04_video_generation.ipynb` — card → clip → music → mux
