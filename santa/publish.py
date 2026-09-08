"""Upload card and video files to the wall: CPU service by default, Storage with ``--local``."""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

import requests

from santa.storage import Storage

CONTENT_TYPES = {
    ".png": "image/png",
    ".html": "text/html",
    ".json": "application/json",
    ".mp4": "video/mp4",
}

# kids.csv ids (k01) and default KidProfile ids (uuid4)
_KID_ID = re.compile(
    r"^(k\d+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$",
    re.I,
)


class PublishError(RuntimeError):
    """Publish failed; message is participant-readable."""


class StorageLike(Protocol):
    def upload(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        ...


PostFn = Callable[..., Any]


def wall_name(path: Path | str, *, object_id: str | None = None) -> str:
    """``out/<id>/card.png`` → ``<id>.png`` so the bucket key is ``cards/{id}.png``."""
    p = Path(path)
    suffix = (p.suffix or "").lower()
    if object_id:
        return f"{object_id}{suffix or '.bin'}"
    parent = p.parent.name
    if p.stem == "card" and parent and _KID_ID.match(parent):
        return f"{parent}{suffix}"
    return p.name or "upload"


def object_key(path: Path | str, *, content_type: str = "", object_id: str | None = None) -> str:
    """png/html/json → ``cards/``; mp4 or ``video/*`` → ``videos/``. Prefers ``{id}`` over ``card.*``."""
    name = wall_name(path, object_id=object_id)
    if content_type.lower().startswith("video/") or Path(name).suffix.lower() == ".mp4":
        return f"videos/{name}"
    return f"cards/{name}"


def content_type_for(path: Path | str) -> str:
    suffix = Path(path).suffix.lower()
    return CONTENT_TYPES.get(suffix, "application/octet-stream")


def service_url_from_env() -> str:
    return (os.environ.get("SANTA_SERVICE_URL") or "").strip().rstrip("/")


def publish_via_service(
    paths: Sequence[Path],
    *,
    service_url: str,
    post: PostFn | None = None,
    object_id: str | None = None,
) -> list[str]:
    """POST each file to ``{service_url}/api/publish`` (multipart ``file``)."""
    sender = post or requests.post
    url = f"{service_url.rstrip('/')}/api/publish"
    keys: list[str] = []
    for path in paths:
        payload = path.read_bytes()
        ctype = content_type_for(path)
        filename = wall_name(path, object_id=object_id)
        try:
            resp = sender(url, files={"file": (filename, payload, ctype)}, timeout=60)
            resp.raise_for_status()
            data = resp.json() if hasattr(resp, "json") else {}
        except Exception as exc:
            raise PublishError(f"publish {path.name} failed: {exc}") from exc
        key = data.get("key") if isinstance(data, dict) else None
        keys.append(str(key) if key else object_key(path, object_id=object_id))
    return keys


def publish_via_storage(
    paths: Sequence[Path], *, storage: StorageLike, object_id: str | None = None
) -> list[str]:
    """Upload using Storage. Same key rules as the service."""
    keys: list[str] = []
    for path in paths:
        key = object_key(path, object_id=object_id)
        storage.upload(key, path.read_bytes(), content_type=content_type_for(path))
        keys.append(key)
    return keys


def publish_files(
    paths: Sequence[Path | str],
    *,
    local: bool = False,
    service_url: str | None = None,
    storage: StorageLike | None = None,
    post: PostFn | None = None,
    object_id: str | None = None,
) -> list[str]:
    """Default: CPU service. ``local=True`` uses ``Storage.from_env()`` (S3 creds on this laptop)."""
    resolved = [Path(p) for p in paths]
    missing = [p for p in resolved if not p.is_file()]
    if missing:
        raise PublishError(f"not a file: {missing[0]}")
    if local:
        store = storage or Storage.from_env()
        return publish_via_storage(resolved, storage=store, object_id=object_id)
    url = service_url if service_url is not None else service_url_from_env()
    url = (url or "").strip().rstrip("/")
    if not url:
        raise PublishError(
            "SANTA_SERVICE_URL is not set. Point it at your CPU service, or pass --local "
            "to upload with this laptop's bucket creds."
        )
    return publish_via_service(resolved, service_url=url, post=post, object_id=object_id)
