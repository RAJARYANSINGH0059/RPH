"""Storage abstraction: local filesystem (development) or S3-compatible object storage (production).

Rules: random storage keys (never user-supplied names), originals immutable, SHA-256 verified on read, private bucket,
server-only credentials, short-lived signed URLs only through `signed_url()`, no public listing.

Configure S3 with: STORAGE_BACKEND=s3, S3_BUCKET, S3_ENDPOINT_URL (R2/MinIO/etc.; blank for AWS), S3_REGION,
S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, optional S3_PREFIX. Falls back to local storage with a visible warning if
any required variable is missing.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class StorageError(RuntimeError):
    pass


class LocalStorage:
    backend = "local"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("Invalid storage key")
        return p

    def put(self, case_id: str, data: bytes, ext: str, content_type: str = "application/octet-stream") -> str:
        safe_ext = "".join(ch for ch in ext.lower() if ch.isalnum())[:8]
        key = f"{case_id}/{secrets.token_hex(16)}.{safe_ext or 'bin'}"
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data)
        (p.with_suffix(p.suffix + ".sha256")).write_text(sha256_bytes(data))
        return key

    def get(self, key: str, expected_sha256: str | None = None) -> bytes:
        with open(self._path(key), "rb") as fh:
            data = fh.read()
        if expected_sha256 and sha256_bytes(data) != expected_sha256:
            raise StorageError("stored object hash mismatch")
        return data

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def signed_url(self, key: str, expires_seconds: int = 300) -> str | None:
        return None  # local files are only served through the API

    def status(self) -> dict:
        return {"backend": "local", "durable": False, "path": str(self.root),
                "note": "Local filesystem; on Render free plan this is ephemeral across deploys. Configure S3 for durable evidence."}


class S3Storage:
    backend = "s3"
    MAX_OBJECT_BYTES = 100 * 1024 * 1024

    def __init__(self, bucket: str, endpoint_url: str | None, region: str | None, access_key: str, secret_key: str, prefix: str = ""):
        import boto3
        from botocore.config import Config
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = boto3.client("s3", endpoint_url=endpoint_url or None, region_name=region or None, aws_access_key_id=access_key,
                                   aws_secret_access_key=secret_key, config=Config(signature_version="s3v4", retries={"max_attempts": 3}, connect_timeout=5, read_timeout=30))
        self._endpoint = endpoint_url or "aws"

    def _k(self, key: str) -> str:
        if ".." in key or key.startswith("/"):
            raise ValueError("Invalid storage key")
        return f"{self.prefix}/{key}" if self.prefix else key

    def put(self, case_id: str, data: bytes, ext: str, content_type: str = "application/octet-stream") -> str:
        if len(data) > self.MAX_OBJECT_BYTES:
            raise StorageError("object too large")
        safe_ext = "".join(ch for ch in ext.lower() if ch.isalnum())[:8]
        key = f"{case_id}/{secrets.token_hex(16)}.{safe_ext or 'bin'}"
        digest = sha256_bytes(data)
        self.client.put_object(Bucket=self.bucket, Key=self._k(key), Body=data, ContentType=content_type,
                               Metadata={"sha256": digest}, ACL="private") if self._endpoint == "aws" else \
            self.client.put_object(Bucket=self.bucket, Key=self._k(key), Body=data, ContentType=content_type, Metadata={"sha256": digest})
        # read-after-write verification
        head = self.client.head_object(Bucket=self.bucket, Key=self._k(key))
        if head.get("Metadata", {}).get("sha256") != digest or int(head.get("ContentLength", -1)) != len(data):
            raise StorageError("object verification failed after write")
        return key

    def get(self, key: str, expected_sha256: str | None = None) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=self._k(key))
        data = obj["Body"].read()
        stored = obj.get("Metadata", {}).get("sha256")
        if (expected_sha256 and sha256_bytes(data) != expected_sha256) or (stored and stored != sha256_bytes(data)):
            raise StorageError("stored object hash mismatch")
        return data

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._k(key))
            return True
        except Exception:
            return False

    def signed_url(self, key: str, expires_seconds: int = 300) -> str | None:
        return self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": self._k(key)}, ExpiresIn=min(expires_seconds, 900))

    def status(self) -> dict:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            reachable = True
        except Exception as exc:
            reachable = f"unreachable: {type(exc).__name__}"
        return {"backend": "s3", "durable": True, "bucket": self.bucket, "endpoint": "custom" if self._endpoint != "aws" else "aws", "reachable": reachable}


@lru_cache
def get_storage():
    s = get_settings()
    backend = os.environ.get("STORAGE_BACKEND", "local").lower()
    if backend == "s3":
        bucket, ak, sk = os.environ.get("S3_BUCKET", ""), os.environ.get("S3_ACCESS_KEY_ID", ""), os.environ.get("S3_SECRET_ACCESS_KEY", "")
        if bucket and ak and sk:
            return S3Storage(bucket, os.environ.get("S3_ENDPOINT_URL") or None, os.environ.get("S3_REGION") or None, ak, sk, os.environ.get("S3_PREFIX", ""))
        local = LocalStorage(os.path.join(s.storage_dir, "uploads"))
        local.misconfigured = True  # type: ignore[attr-defined]
        return local
    return LocalStorage(os.path.join(s.storage_dir, "uploads"))


def storage_status() -> dict:
    st = get_storage()
    out = st.status()
    if getattr(st, "misconfigured", False):
        out["warning"] = "STORAGE_BACKEND=s3 but S3_BUCKET / S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY are incomplete; using local storage"
    return out
