"""Storage abstraction: local filesystem now; S3-compatible later.

Original files are immutable once stored. Storage keys are random, never derived from user-supplied names.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path

from app.core.config import get_settings


class LocalStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("Invalid storage key")
        return p

    def put(self, case_id: str, data: bytes, ext: str) -> str:
        safe_ext = "".join(ch for ch in ext.lower() if ch.isalnum())[:8]
        key = f"{case_id}/{secrets.token_hex(16)}.{safe_ext or 'bin'}"
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "wb") as fh:
            fh.write(data)
        return key

    def get(self, key: str) -> bytes:
        with open(self._path(key), "rb") as fh:
            return fh.read()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_storage() -> LocalStorage:
    s = get_settings()
    return LocalStorage(os.path.join(s.storage_dir, "uploads"))
