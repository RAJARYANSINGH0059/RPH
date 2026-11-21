"""Inference test against the exact saved artefact (checksum verified). Skips if no model was retained."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml" / "evaluation"))
sys.path.insert(0, str(ROOT / "apps" / "api"))


def test_metrics_json_exists_and_is_honest():
    p = ROOT / "ml" / "evaluation" / "metrics.json"
    if not p.exists():
        pytest.skip("metrics.json not generated yet (run ml/training/train.py)")
    m = json.loads(p.read_text())
    assert "rules_baseline" in m["models"]
    assert "synthetic" in m["synthetic_only_statement"].lower()
    assert m["retained"] == (m.get("artifact") is not None)


def test_saved_model_loads_and_scores():
    from inference import load_model, score
    bundle = load_model()
    if bundle is None:
        pytest.skip("no model artefact retained (baseline shipped)")
    feats = {f: 0.0 for f in bundle["features"]}
    feats.update({"fan_in": 3, "out_in_ratio": 0.95, "median_holding_hours": 2.0, "tx_in": 3, "tx_out": 2})
    out = score(bundle, feats)
    assert 0.0 <= out["triage_score"] <= 1.0
    assert "human review" in out["semantics"]
    assert out["sha256"] == bundle["sha256"][:16]


def test_checksum_mismatch_refuses_load(tmp_path, monkeypatch):
    import inference
    art = ROOT / "ml" / "artifacts"
    if not (art / "triage_model.joblib").exists():
        pytest.skip("no model artefact")
    fake = tmp_path / "artifacts"
    fake.mkdir()
    (fake / "triage_model.joblib").write_bytes((art / "triage_model.joblib").read_bytes() + b"x")
    (fake / "triage_model.sha256").write_text((art / "triage_model.sha256").read_text())
    (fake / "feature_schema.json").write_text((art / "feature_schema.json").read_text())
    monkeypatch.setattr(inference, "ART", fake)
    with pytest.raises(RuntimeError):
        inference.load_model()
