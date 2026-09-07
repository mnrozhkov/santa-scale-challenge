# 05: Step 7 — `santa animate`: Wan I2V (async) + ACE-Step music + local mux → `card.mp4`

**What to build:** A participant runs `santa animate out/<id>/card.png [--motion "…"]`; the CLI submits the image to the Wan endpoint, requests a short instrumental from ACE-Step (mood from the wish), muxes both locally with the bundled ffmpeg, and writes `card.mp4`. With `--no-wait` it returns a ticket and `santa animate --status` picks it up later.

**Blocked by:** 01

**Status:** ready-for-human

- [x] `wan_omni` adapter: `POST /v1/videos/sync` multipart (`model`, `input_reference` file, `prompt`, `size=832x480`, `num_frames=81`, `fps=16`, `num_inference_steps=20`, `guidance_scale=1.0`, `guidance_scale_2=1.0`, `flow_shift=12.0`, `boundary_ratio=0.875`, `seed`) → raw MP4; async path `POST /v1/videos` + poll if the endpoint supports it (probe `/v1/models` + try async first)
- [x] `acestep_audio` adapter: `POST /v1/audio/generations` JSON (`task_type=text2music`, `thinking=false`, `audio_duration=8`, `inference_steps=8`, `audio_format=mp3`) → mp3 bytes
- [x] `openai_video` adapter (video fallback): OpenAI Videos API image-to-video (`input_reference`), poll until complete, download MP4
- [x] `local_tracks` adapter (audio fallback): pick `data/fallback/moods/<mood>.mp3`, else the bundled default track
- [x] `santa/mux.py`: `imageio-ffmpeg` binary, `-shortest`, AAC; no system ffmpeg
- [x] `config/prompts.yaml`: default motion prompt (gentle storybook motion, no faces/text), mood → music prompt map
- [x] `santa animate <png> [--motion] [--fresh-music|--mood-bank] [--wait|--no-wait] [--publish]`; roles resolved through `Resilient` so a cold Wan or ACE-Step endpoint falls back automatically
- [x] Tests: multipart field names incl. `input_reference`; JSON shapes; `openai_video` request/poll shape; `local_tracks` pick; mux on two fixture files produces a playable MP4 (probe with ffprobe from imageio-ffmpeg)
