"""Object storage: boto3 upload/exists/list/download, plus FUSE-safe ``staged_write``."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from santa.config import REPO_ROOT


class StorageError(RuntimeError):
    """S3/bucket call failed; message is participant-readable."""


# One folder per kid: cards/{id}/card.png|html|json and video.mp4
CARD_PNG = "card.png"
CARD_HTML = "card.html"
CARD_JSON = "card.json"
CARD_VIDEO = "video.mp4"


def card_png_key(kid_id: str) -> str:
    return f"cards/{kid_id}/{CARD_PNG}"


def card_html_key(kid_id: str) -> str:
    return f"cards/{kid_id}/{CARD_HTML}"


def card_json_key(kid_id: str) -> str:
    return f"cards/{kid_id}/{CARD_JSON}"


def card_video_key(kid_id: str) -> str:
    return f"cards/{kid_id}/{CARD_VIDEO}"


def id_from_card_png_key(key: str) -> str | None:
    """Return the id if ``key`` is ``cards/{id}/card.png``."""
    parts = key.split("/")
    if len(parts) == 3 and parts[0] == "cards" and parts[2] == CARD_PNG and parts[1]:
        return parts[1]
    return None


def staged_write(dest: Path | str, data: bytes) -> Path:
    """Write ``data`` to ``dest`` via a sibling tmp file then rename (safe on FUSE)."""
    path = Path(dest)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    return path


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def _denied_hint(exc: BaseException) -> str:
    text = str(exc)
    status = None
    error = getattr(exc, "response", None)
    if isinstance(error, dict):
        status = error.get("ResponseMetadata", {}).get("HTTPStatusCode")
        code = str(error.get("Error", {}).get("Code", ""))
        if not text:
            text = code
    if status == 403 or "403" in text or "Forbidden" in text or "AccessDenied" in text:
        return (
            " Check AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY "
            "(Object Storage access keys for this bucket, not NEBIUS_IAM_TOKEN), "
            "NEBIUS_BUCKET_NAME (the bucket name, not NEBIUS_BUCKET_ID), "
            "and AWS_ENDPOINT_URL=https://storage.<region>.nebius.cloud"
        )
    if "CERTIFICATE_VERIFY_FAILED" in text or "SSL" in text:
        return " TLS failed (laptop CA bundle). Retry with AWS_CA_BUNDLE=/etc/ssl/cert.pem"
    return ""


def use_system_certs() -> None:
    """macOS/corporate laptops often fail TLS with certifi; trust the OS store."""
    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:
        pass


def _tls_verify() -> str | bool:
    """CA bundle boto3 should use. Prefer the OS store over a stale cert.pem."""
    for name in ("AWS_CA_BUNDLE", "REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        path = _env(name)
        if path:
            return path
    try:
        import truststore

        truststore.inject_into_ssl()
        return True
    except Exception:
        pass
    mac = Path("/etc/ssl/cert.pem")
    if mac.is_file():
        return str(mac)
    return True


def _boto_s3_client() -> Any:
    """Nebius Object Storage client. Never fall through to ~/.aws or AWS_SESSION_TOKEN."""
    import boto3
    from botocore.config import Config

    key = _env("AWS_ACCESS_KEY_ID")
    secret = _env("AWS_SECRET_ACCESS_KEY")
    if not key or not secret:
        raise StorageError(
            "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env "
            "(Object Storage access keys from the console, not NEBIUS_IAM_TOKEN)."
        )
    endpoint = _env("AWS_ENDPOINT_URL") or "https://storage.eu-north1.nebius.cloud"
    endpoint = endpoint.rstrip("/")
    if endpoint.endswith(":443"):
        endpoint = endpoint[: -len(":443")]
    return boto3.client(
        "s3",
        aws_access_key_id=key,
        aws_secret_access_key=secret,
        endpoint_url=endpoint,
        region_name=_env("AWS_DEFAULT_REGION") or "eu-north1",
        verify=_tls_verify(),
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


class Storage:
    """Thin boto3 wrapper. Keys are POSIX paths (``cards/{id}/card.png``)."""

    def __init__(self, client: Any, bucket: str) -> None:
        if not bucket:
            raise StorageError("Bucket name is empty. Set NEBIUS_BUCKET_NAME in .env.")
        self.client = client
        self.bucket = bucket

    @classmethod
    def from_env(cls, client: Any | None = None) -> Storage:
        name = _env("NEBIUS_BUCKET_NAME") or _env("AWS_S3_BUCKET")
        if not name:
            raise StorageError("Set NEBIUS_BUCKET_NAME (or AWS_S3_BUCKET) in .env.")
        if client is None:
            client = _boto_s3_client()
        return cls(client, name)

    def upload(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        extra: dict[str, str] = {}
        if content_type:
            extra["ContentType"] = content_type
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, **extra)
        except Exception as exc:
            raise StorageError(f"upload {key} failed: {exc}.{_denied_hint(exc)}") from exc

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
            raise StorageError(f"exists {key} failed: {exc}.{_denied_hint(exc)}") from exc

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
            raise StorageError(f"list {prefix!r} failed: {exc}.{_denied_hint(exc)}") from exc
        return items

    def download(self, key: str) -> bytes:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
            body = resp["Body"]
            return body.read() if hasattr(body, "read") else bytes(body)
        except Exception as exc:
            raise StorageError(f"download {key} failed: {exc}") from exc


def card_profile_key(kid_id: str) -> str:
    return f"cards/{kid_id}/profile.json"


class DiskStorage:
    """StorageLike over a local ``out/{id}/`` tree. Keys stay ``cards/{id}/card.png``."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _path_for(self, key: str) -> Path:
        parts = [p for p in Path(key).parts if p not in (".", "..")]
        if len(parts) >= 3 and parts[0] == "cards":
            kid_id, name = parts[1], parts[-1]
            folder = self.root / kid_id
            if name == CARD_VIDEO:
                local = folder / "card.mp4"
                if local.is_file():
                    return local
                return folder / CARD_VIDEO
            return folder / name
        return self.root.joinpath(*parts)

    def upload(self, key: str, data: bytes, *, content_type: str | None = None) -> None:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def exists(self, key: str) -> bool:
        return self._path_for(key).is_file()

    def list(self, prefix: str = "") -> list[str]:
        return [k for k, _ in self.list_with_mtime(prefix)]

    def list_with_mtime(self, prefix: str = "") -> list[tuple[str, float]]:
        items: list[tuple[str, float]] = []
        if not self.root.is_dir():
            return items
        for folder in sorted(self.root.iterdir()):
            if not folder.is_dir() or folder.name in {"mlruns", "runs"}:
                continue
            mapping = (
                (folder / CARD_PNG, card_png_key(folder.name)),
                (folder / CARD_HTML, card_html_key(folder.name)),
                (folder / CARD_JSON, card_json_key(folder.name)),
                (folder / "profile.json", card_profile_key(folder.name)),
                (folder / "card.mp4", card_video_key(folder.name)),
                (folder / CARD_VIDEO, card_video_key(folder.name)),
            )
            seen: set[str] = set()
            for path, object_key in mapping:
                if not path.is_file() or object_key in seen:
                    continue
                if prefix and not object_key.startswith(prefix):
                    continue
                seen.add(object_key)
                items.append((object_key, path.stat().st_mtime))
        runs = self.root / "runs"
        if runs.is_dir() and (
            not prefix or prefix.startswith("runs") or "runs/".startswith(prefix)
        ):
            for path in runs.rglob("*"):
                if not path.is_file():
                    continue
                object_key = path.relative_to(self.root).as_posix()
                if prefix and not object_key.startswith(prefix):
                    continue
                items.append((object_key, path.stat().st_mtime))
        return items

    def download(self, key: str) -> bytes:
        path = self._path_for(key)
        if not path.is_file():
            raise StorageError(f"missing {key}")
        return path.read_bytes()


def storage_for_service(out_root: Path | None = None) -> Any:
    """S3 when bucket creds are set; otherwise local ``out/`` so the CPU UI runs on a laptop.

    ``SANTA_LOCAL_STORAGE=1`` forces disk even if AWS keys are present (laptop TLS / no bucket).
    """
    root = out_root or REPO_ROOT / "out"
    if _env("SANTA_LOCAL_STORAGE").lower() in {"1", "true", "yes"}:
        return DiskStorage(root)
    name = _env("NEBIUS_BUCKET_NAME") or _env("AWS_S3_BUCKET")
    key = _env("AWS_ACCESS_KEY_ID")
    if not name or not key:
        return DiskStorage(root)
    return Storage.from_env()


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
