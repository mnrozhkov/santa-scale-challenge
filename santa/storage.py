"""Object storage: boto3 upload/exists/list/download, plus FUSE-safe ``staged_write``."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from santa.config import REPO_ROOT


class StorageError(RuntimeError):
    """S3/bucket call failed; message is participant-readable."""


def staged_write(dest: Path | str, data: bytes) -> Path:
    """Write ``data`` to ``dest`` via a sibling tmp file then rename (safe on FUSE)."""
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


class Storage:
    """Thin boto3 wrapper. Keys are POSIX paths in the bucket (``cards/{id}.png``)."""

    def __init__(self, client: Any, bucket: str) -> None:
        if not bucket:
            raise StorageError("Bucket name is empty. Set NEBIUS_BUCKET_NAME in .env.")
        self.client = client
        self.bucket = bucket

    @classmethod
    def from_env(cls, client: Any | None = None) -> Storage:
        import boto3

        name = (
            os.environ.get("NEBIUS_BUCKET_NAME") or os.environ.get("AWS_S3_BUCKET") or ""
        ).strip()
        if not name:
            raise StorageError("Set NEBIUS_BUCKET_NAME (or AWS_S3_BUCKET) in .env.")
        if client is None:
            client = boto3.client(
                "s3",
                endpoint_url=(os.environ.get("AWS_ENDPOINT_URL") or "").strip() or None,
                region_name=(os.environ.get("AWS_DEFAULT_REGION") or "eu-north1").strip(),
            )
        return cls(client, name)

    def upload(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        extra: dict[str, str] = {}
        if content_type:
            extra["ContentType"] = content_type
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, **extra)
        except Exception as exc:
            raise StorageError(f"upload {key} failed: {exc}") from exc

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            error = getattr(exc, "response", None)
            if isinstance(error, dict):
                code = str(error.get("Error", {}).get("Code", ""))
                status = error.get("ResponseMetadata", {}).get("HTTPStatusCode")
                if status == 404 or code in {"404", "NoSuchKey", "NotFound"}:
                    return False
            if "404" in str(exc) or "NoSuchKey" in str(exc):
                return False
            raise StorageError(f"exists {key} failed: {exc}") from exc

    def list(self, prefix: str = "") -> list[str]:
        return [k for k, _ in self.list_with_mtime(prefix)]

    def list_with_mtime(self, prefix: str = "") -> list[tuple[str, float]]:
        items: list[tuple[str, float]] = []
        token = None
        try:
            while True:
                kw: dict[str, Any] = {"Bucket": self.bucket, "Prefix": prefix}
                if token:
                    kw["ContinuationToken"] = token
                resp = self.client.list_objects_v2(**kw)
                for obj in resp.get("Contents") or []:
                    key = obj["Key"]
                    stamp = obj.get("LastModified")
                    mtime = stamp.timestamp() if hasattr(stamp, "timestamp") else 0.0
                    items.append((key, mtime))
                if not resp.get("IsTruncated"):
                    break
                token = resp.get("NextContinuationToken")
        except Exception as exc:
            raise StorageError(f"list {prefix!r} failed: {exc}") from exc
        return items

    def download(self, key: str) -> bytes:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
            body = resp["Body"]
            return body.read() if hasattr(body, "read") else bytes(body)
        except Exception as exc:
            raise StorageError(f"download {key} failed: {exc}") from exc


class MemoryStorage:
    """In-memory StorageLike for tests (no boto3)."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self._mtime: dict[str, int] = {}
        self._tick = 0

    def upload(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        self._tick += 1
        self.objects[key] = data
        self._mtime[key] = self._tick

    def exists(self, key: str) -> bool:
        return key in self.objects

    def list(self, prefix: str = "") -> list[str]:
        return [k for k in sorted(self.objects) if k.startswith(prefix)]

    def list_with_mtime(self, prefix: str = "") -> list[tuple[str, float]]:
        return [(k, float(self._mtime[k])) for k in self.list(prefix)]

    def download(self, key: str) -> bytes:
        if key not in self.objects:
            raise StorageError(f"missing {key}")
        return self.objects[key]


def local_run_dir(run_id: str, root: Path | None = None) -> Path:
    return (root or REPO_ROOT / "out") / "runs" / run_id
