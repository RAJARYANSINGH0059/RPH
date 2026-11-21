"""Optional ML triage signal. Loads ml/artifacts/triage_model.joblib if present (checksum-verified); otherwise the
transparent rules baseline is the only triage signal. Output is a triage cue requiring human review, never a decision."""
from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

from app.core.config import API_ROOT

DEFAULT_DIR = API_ROOT.parent.parent / "ml" / "artifacts"


@lru_cache
def load_bundle() -> dict | None:
    d = Path(os.environ.get("ML_MODEL_DIR", str(DEFAULT_DIR)))
    model_path = d / "triage_model.joblib"
    if not model_path.exists():
        return None
    try:
        expected = (d / "triage_model.sha256").read_text().strip()
        actual = hashlib.sha256(model_path.read_bytes()).hexdigest()
        if expected != actual:
            return None  # refuse a tampered/mismatched artefact
        import joblib
        b = joblib.load(model_path)
        b["sha256"] = actual
        b["schema"] = json.loads((d / "feature_schema.json").read_text())
        return b
    except Exception:
        return None


def score(features: dict) -> dict | None:
    b = load_bundle()
    if b is None:
        return None
    import numpy as np
    x = np.array([[float(features.get(f, 0.0)) for f in b["features"]]])
    s = float(b["model"].predict_proba(x)[0, 1])
    return {"triage_score": round(s, 4), "flag": bool(s >= b["threshold"]), "model": b["model_name"], "artifact_sha256": b["sha256"][:16],
            "semantics": "synthetic-trained triage cue (uncalibrated beyond synthetic data); requires human review; not a probability of guilt"}


def status() -> dict:
    b = load_bundle()
    return {"available": b is not None, "model": b["model_name"] if b else None, "artifact_sha256": b["sha256"][:16] if b else None,
            "dataset_version": b["dataset_version"] if b else None}
