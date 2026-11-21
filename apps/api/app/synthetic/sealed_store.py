"""Benchmark-only store for hidden ground truth.

This module is imported ONLY by the benchmark runner and the synthetic service (write side). No analyst
router imports it. Files live in a separate directory (BENCHMARK_STORE_DIR) outside the uploads tree.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.core.config import get_settings


def _dir() -> Path:
    p = Path(get_settings().benchmark_store_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def seal(truth: dict, scenario_type: str, difficulty: str, size: str, seed: int, version: str) -> str:
    """Write truth to the sealed namespace; return an opaque reference (sha256 of the parameters)."""
    ref = hashlib.sha256(f"{scenario_type}|{difficulty}|{size}|{seed}|{version}".encode()).hexdigest()[:40]
    path = _dir() / f"{ref}.json"
    path.write_text(json.dumps(truth, indent=1, sort_keys=True, default=str), encoding="utf-8")
    return ref


def unseal(ref: str) -> dict:
    """Benchmark use only."""
    if not ref.isalnum():
        raise ValueError("invalid ref")
    return json.loads((_dir() / f"{ref}.json").read_text(encoding="utf-8"))
