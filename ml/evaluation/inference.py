"""Load the saved triage artefact (verifying its checksum) and score feature dicts. Used by the API if present."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ART = Path(__file__).resolve().parents[1] / "artifacts"


def load_model():
    model_path = ART / "triage_model.joblib"
    if not model_path.exists():
        return None
    expected = (ART / "triage_model.sha256").read_text().strip()
    actual = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if expected != actual:
        raise RuntimeError("triage model checksum mismatch; refusing to load")
    import joblib
    bundle = joblib.load(model_path)
    bundle["sha256"] = actual
    bundle["schema"] = json.loads((ART / "feature_schema.json").read_text())
    return bundle


def score(bundle, features: dict) -> dict:
    import numpy as np
    x = np.array([[float(features[f]) for f in bundle["features"]]])
    s = float(bundle["model"].predict_proba(x)[0, 1])
    return {"triage_score": round(s, 4), "flag": s >= bundle["threshold"], "model": bundle["model_name"], "sha256": bundle["sha256"][:16],
            "semantics": "synthetic-trained triage cue; requires human review; not a probability of guilt"}
