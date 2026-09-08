# 12: `notebooks/` — one playground per media endpoint

**What to build:** Four Colab-runnable notebooks let a participant call each endpoint directly, change prompts and parameters, and see the result inline: text-to-image (Sana), image-to-video (Wan), text-to-music (ACE-Step), and an end-to-end video-generation notebook (card → clip → music → MP4). All import the `santa` adapters.

**Blocked by:** 05

**Status:** ready-for-human

- [x] `notebooks/01_text_to_image.ipynb`, `02_image_to_video.ipynb`, `03_text_to_music.ipynb`, `04_video_generation.ipynb`; each reads `.env` or Colab secrets, uses the `santa` adapters (with fallbacks), shows output inline
- [x] "Open in Colab" badges; `uv run jupyter lab` path documented
- [ ] Executed once end to end; outputs stripped before commit

## Comments

2026-09-08: Added `notebooks/01_text_to_image.ipynb`, `02_image_to_video.ipynb`, `03_text_to_music.ipynb`, `04_video_generation.ipynb`, and `notebooks/README.md`. Each loads `Settings`, copies Colab userdata into `os.environ` when `google.colab` is importable, and calls `adapter_for` (04 also uses `make_card` + `mux`). Colab badges point at `blob/serverless/notebooks/…`. Outputs left empty — not executed against live endpoints.
