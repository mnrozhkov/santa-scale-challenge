"""scripts/sync_models.py: HF → local → bucket models/, skip keys that already exist."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from santa.storage import MemoryStorage

ROOT = Path(__file__).resolve().parents[1]


def _sync():
    path = ROOT / "scripts" / "sync_models.py"
    spec = importlib.util.spec_from_file_location("sync_models", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sync_uploads_cache_then_skips_existing(tmp_path: Path) -> None:
    mod = _sync()
    local = tmp_path / "hf"
    store = MemoryStorage()

    def download(model_id: str, dest: Path) -> Path:
        blob = dest / "hub" / "models--Wan-AI--demo" / "weight.safetensors"
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(b"weights-v1")
        (dest / "unrelated.bin").write_bytes(b"nope")
        return dest

    first = mod.sync_models(
        model_id="Wan-AI/demo",
        local_dir=local,
        storage=store,
        download=download,
    )
    assert first["uploaded"] == 1 and first["skipped"] == 0
    assert store.download("models/hub/models--Wan-AI--demo/weight.safetensors") == b"weights-v1"
    assert not store.exists("models/unrelated.bin")

    def download_again(model_id: str, dest: Path) -> Path:
        blob = dest / "hub" / "models--Wan-AI--demo" / "weight.safetensors"
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(b"weights-v2")
        return dest

    second = mod.sync_models(
        model_id="Wan-AI/demo",
        local_dir=local,
        storage=store,
        download=download_again,
    )
    assert second["uploaded"] == 0 and second["skipped"] == 1
    assert store.download("models/hub/models--Wan-AI--demo/weight.safetensors") == b"weights-v1"
