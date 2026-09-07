"""GPU Job entrypoint: a chunk of card ids → Wan I2V + mood mux → ``videos/{id}.mp4``.

``python -m santa.job`` reads ``CHUNK`` / ``RUN_ID`` / ``HF_HOME``. Tests inject a
``ClipRenderer`` so CI never loads torch. Exit 0 on per-card failures; non-zero
only when setup (chunk, pipeline, mount) fails.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from santa.animate import load_prompts, motion_prompt
from santa.config import Settings
from santa.mux import mux
from santa.storage import staged_write

DEFAULT_DATA_ROOT = Path("/data")
DEFAULT_MOOD = "warm"


class JobSetupError(RuntimeError):
    """Fatal: missing chunk, mount, or pipeline. The process should exit non-zero."""


class ClipRenderer(Protocol):
    def render(self, image: Path, prompt: str) -> bytes:
        """Return silent MP4 bytes for one card PNG."""


@dataclass
class ItemResult:
    id: str
    status: str
    seconds: float
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        row: dict[str, Any] = {"id": self.id, "status": self.status, "seconds": self.seconds}
        if self.error:
            row["error"] = self.error
        return row


@dataclass
class JobReport:
    run_id: str
    chunk: str
    items: list[ItemResult] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "chunk": self.chunk,
            "items": [i.as_dict() for i in self.items],
        }


def pick_mood_track(moods_dir: Path, mood: str) -> Path:
    """``audio/moods/{mood}.mp3``, else ``default.mp3``. Same rule as ``local_tracks``."""
    tag = (mood or DEFAULT_MOOD).strip() or DEFAULT_MOOD
    chosen = moods_dir / f"{tag}.mp3"
    if chosen.is_file():
        return chosen
    fallback = moods_dir / "default.mp3"
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(f"no track for mood {tag!r} in {moods_dir}")


def _chunk_index(chunk_path: Path) -> str:
    return chunk_path.stem


def _load_chunk(chunk_path: Path) -> list[dict[str, str]]:
    try:
        raw = json.loads(chunk_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise JobSetupError(f"CHUNK not found: {chunk_path}") from exc
    except json.JSONDecodeError as exc:
        raise JobSetupError(f"CHUNK is not JSON: {chunk_path}") from exc
    if not isinstance(raw, list):
        raise JobSetupError(f"CHUNK must be a list of {{id, mood}}, got {type(raw).__name__}")
    items: list[dict[str, str]] = []
    for row in raw:
        if not isinstance(row, dict) or not row.get("id"):
            raise JobSetupError(f"CHUNK row missing id: {row!r}")
        items.append({"id": str(row["id"]), "mood": str(row.get("mood") or DEFAULT_MOOD)})
    return items


def _write_status(data_root: Path, run_id: str, chunk: str, report: JobReport) -> Path:
    dest = data_root / "runs" / run_id / "jobs" / f"{chunk}.json"
    staged_write(dest, (json.dumps(report.as_dict(), indent=2) + "\n").encode())
    return dest


def _one_card(
    *,
    kid_id: str,
    mood: str,
    data_root: Path,
    renderer: ClipRenderer,
    prompt: str,
) -> ItemResult:
    dest = data_root / "videos" / f"{kid_id}.mp4"
    if dest.is_file() and dest.stat().st_size > 0:
        return ItemResult(id=kid_id, status="skipped", seconds=0.0)
    t0 = time.time()
    png = data_root / "cards" / f"{kid_id}.png"
    if not png.is_file():
        return ItemResult(
            id=kid_id, status="failed", seconds=round(time.time() - t0, 3), error=f"missing {png}"
        )
    try:
        silent = renderer.render(png, prompt)
        audio = pick_mood_track(data_root / "audio" / "moods", mood)
        with tempfile.TemporaryDirectory(prefix=f"santa-job-{kid_id}-") as tmp:
            tmp_dir = Path(tmp)
            video_path = tmp_dir / "silent.mp4"
            muxed_path = tmp_dir / "muxed.mp4"
            video_path.write_bytes(silent)
            mux(video_path, audio, muxed_path)
            staged_write(dest, muxed_path.read_bytes())
    except Exception as exc:
        return ItemResult(
            id=kid_id, status="failed", seconds=round(time.time() - t0, 3), error=str(exc)
        )
    return ItemResult(id=kid_id, status="done", seconds=round(time.time() - t0, 3))


def run_job(
    *,
    data_root: Path | str,
    chunk_path: Path | str,
    run_id: str,
    renderer: ClipRenderer,
    prompts: dict[str, Any] | None = None,
) -> JobReport:
    """Process every id in the chunk. Never raises on per-card failure."""
    root = Path(data_root)
    chunk = Path(chunk_path)
    index = _chunk_index(chunk)
    rows = _load_chunk(chunk)
    prompt = motion_prompt(prompts if prompts is not None else load_prompts())
    report = JobReport(run_id=run_id, chunk=index)
    for row in rows:
        report.items.append(
            _one_card(
                kid_id=row["id"],
                mood=row["mood"],
                data_root=root,
                renderer=renderer,
                prompt=prompt,
            )
        )
        _write_status(root, run_id, index, report)
    return report


def load_wan_pipeline(
    model_id: str,
    hf_home: str,
    *,
    options: dict[str, Any] | None = None,
) -> ClipRenderer:
    """Load ``WanImageToVideoPipeline`` from the pre-baked HF cache (download if missing)."""
    os.environ.setdefault("HF_HOME", hf_home)
    try:
        import torch
        from diffusers import WanImageToVideoPipeline
    except ImportError as exc:
        raise JobSetupError(
            "Wan pipeline deps missing. Build docker/job.Dockerfile (santa[job])."
        ) from exc

    cache = Path(hf_home)
    cache.mkdir(parents=True, exist_ok=True)
    local_only = _cache_has_model(cache, model_id)
    try:
        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
        pipe = WanImageToVideoPipeline.from_pretrained(
            model_id,
            torch_dtype=dtype,
            local_files_only=local_only,
        )
        device = "cuda" if torch.cuda.is_available() else "cpu"
        pipe.to(device)
    except Exception as exc:
        raise JobSetupError(f"failed to load {model_id} from HF_HOME={hf_home}: {exc}") from exc
    return WanRenderer(pipe, options or {}, device=device)


def _cache_has_model(hf_home: Path, model_id: str) -> bool:
    slug = "models--" + model_id.replace("/", "--")
    hub = hf_home / "hub" / slug
    if hub.is_dir() and any(hub.rglob("*.safetensors")):
        return True
    local = hf_home / model_id
    return local.is_dir() and any(local.rglob("*.safetensors"))


class WanRenderer:
    """Adapter: cookbook ``WanImageToVideoPipeline`` → silent MP4 bytes."""

    def __init__(self, pipe: Any, options: dict[str, Any], *, device: str) -> None:
        self.pipe = pipe
        self.options = options
        self.device = device

    def render(self, image: Path, prompt: str) -> bytes:
        import torch
        from diffusers.utils import export_to_video, load_image

        opts = self.options
        size = str(opts.get("size", "832x480"))
        width_s, height_s = size.lower().replace("*", "x").split("x", 1)
        width, height = int(width_s), int(height_s)
        num_frames = int(opts.get("num_frames", 81))
        fps = int(opts.get("fps", 16))
        steps = int(opts.get("num_inference_steps", 20))
        guidance = float(opts.get("guidance_scale", 1.0))
        pil = load_image(str(image)).resize((width, height))
        kw: dict[str, Any] = {
            "image": pil,
            "prompt": prompt,
            "height": height,
            "width": width,
            "num_frames": num_frames,
            "num_inference_steps": steps,
            "guidance_scale": guidance,
        }
        guidance_2 = opts.get("guidance_scale_2")
        if guidance_2 is not None:
            kw["guidance_scale_2"] = float(guidance_2)
        if torch.cuda.is_available():
            kw["generator"] = torch.Generator(device=self.device).manual_seed(0)
        try:
            frames = self.pipe(**kw).frames[0]
        except TypeError:
            kw.pop("guidance_scale_2", None)
            frames = self.pipe(**kw).frames[0]
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            dest = Path(tmp.name)
        try:
            export_to_video(frames, str(dest), fps=fps)
            return dest.read_bytes()
        finally:
            dest.unlink(missing_ok=True)


def _video_options(settings: Settings) -> dict[str, Any]:
    spec = settings.models.roles.get("video")
    return dict(spec.options) if spec is not None else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m santa.job")
    parser.add_argument("--chunk", default="", help="Override CHUNK env (path to k.json)")
    parser.add_argument("--data-root", default="", help="Override mount (default job.mount_path)")
    parser.add_argument("--run-id", default="", help="Override RUN_ID env")
    args = parser.parse_args(argv)
    try:
        settings = Settings.load()
    except Exception as exc:
        print(f"setup failed: {exc}", file=sys.stderr)
        return 1
    data_root = Path(args.data_root or settings.job.mount_path or DEFAULT_DATA_ROOT)
    chunk_raw = args.chunk or os.environ.get("CHUNK") or ""
    if not chunk_raw:
        print("setup failed: set CHUNK or pass --chunk", file=sys.stderr)
        return 1
    chunk_path = Path(chunk_raw)
    if not chunk_path.is_absolute():
        chunk_path = data_root / chunk_raw
    run_id = args.run_id or os.environ.get("RUN_ID") or ""
    if not run_id:
        print("setup failed: set RUN_ID or pass --run-id", file=sys.stderr)
        return 1
    try:
        _load_chunk(chunk_path)
    except JobSetupError as exc:
        print(f"setup failed: {exc}", file=sys.stderr)
        return 1
    hf_home = os.environ.get("HF_HOME") or settings.job.hf_home or str(data_root / "models")
    os.environ["HF_HOME"] = hf_home
    try:
        renderer = load_wan_pipeline(settings.job.model, hf_home, options=_video_options(settings))
        run_job(
            data_root=data_root,
            chunk_path=chunk_path,
            run_id=run_id,
            renderer=renderer,
        )
    except JobSetupError as exc:
        print(f"setup failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
