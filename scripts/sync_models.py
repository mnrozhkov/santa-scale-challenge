#!/usr/bin/env python3
"""Pre-bake Wan weights: Hugging Face → local HF_HOME → bucket ``models/``.

Idempotent: existing object keys are left alone. Jobs mount the bucket at
``/data`` with ``HF_HOME=/data/models`` and only hit the Hub if the cache is
missing. Laptop:

    uv run --with huggingface_hub scripts/sync_models.py
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from santa.config import REPO_ROOT, Settings

PREFIX = "models"


class StorageLike(Protocol):
    def exists(self, key: str) -> bool:
        ...

    def upload(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        ...


DownloadFn = Callable[[str, Path], Path]


def download_from_hf(model_id: str, dest: Path) -> Path:
    """Populate ``dest`` as an ``HF_HOME`` tree (``dest/hub/models--…``)."""
    dest.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(dest)
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise SystemExit(
            "huggingface_hub is required. Run: uv run --with huggingface_hub scripts/sync_models.py"
        ) from exc
    snapshot_download(repo_id=model_id)
    return dest


def sync_models(
    *,
    model_id: str,
    local_dir: Path,
    storage: StorageLike,
    download: DownloadFn | None = None,
    prefix: str = PREFIX,
) -> dict[str, int]:
    """Download ``model_id`` into ``local_dir`` and upload new files under ``prefix/``."""
    dest = Path(local_dir)
    dest.mkdir(parents=True, exist_ok=True)
    (download or download_from_hf)(model_id, dest)
    slug = "models--" + model_id.replace("/", "--")
    uploaded = 0
    skipped = 0
    for path in sorted(p for p in dest.rglob("*") if p.is_file()):
        rel = path.relative_to(dest).as_posix()
        if slug not in rel:
            continue
        key = f"{prefix.rstrip('/')}/{rel}"
        if storage.exists(key):
            skipped += 1
            continue
        storage.upload(key, path.read_bytes())
        uploaded += 1
    return {"uploaded": uploaded, "skipped": skipped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local-dir",
        type=Path,
        default=REPO_ROOT / ".cache" / "hf",
        help="Local HF_HOME (default: .cache/hf)",
    )
    parser.add_argument("--model", default="", help="Override config/models.yaml job.model")
    parser.add_argument("--prefix", default=PREFIX, help="Bucket prefix (default: models)")
    args = parser.parse_args(argv)
    settings = Settings.load()
    model_id = args.model or settings.job.model
    if not model_id:
        print("job.model is empty in config/models.yaml", file=sys.stderr)
        return 1
    from santa.storage import Storage

    store = Storage.from_env()
    result = sync_models(
        model_id=model_id,
        local_dir=args.local_dir,
        storage=store,
        prefix=args.prefix,
    )
    print(
        f"{model_id}: uploaded {result['uploaded']}, skipped {result['skipped']} → {args.prefix}/"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
