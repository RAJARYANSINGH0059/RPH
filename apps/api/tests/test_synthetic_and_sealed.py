"""Synthetic determinism, sealed ground truth isolation, same-pipeline guarantee."""
import json
import os

from app.synthetic import sealed_store
from app.synthetic.artifacts import build_bundle
from app.synthetic.generator import Generator


def test_generator_is_deterministic():
    a, ta, ma = build_bundle(Generator("investment_scam", "high_noise", "medium", 123))
    b, tb, mb = build_bundle(Generator("investment_scam", "high_noise", "medium", 123))
    assert a.keys() == b.keys()
    assert all(a[k] == b[k] for k in a), [k for k in a if a[k] != b[k]]
    assert ma == mb
    c, _, _ = build_bundle(Generator("investment_scam", "high_noise", "medium", 124))
    assert c["technical_observations.json"] != a["technical_observations.json"]


def test_generator_uses_only_fictional_ranges():
    files, truth, _ = build_bundle(Generator("multi_victim_network", "adversarial", "large", 5))
    for d in truth.domains:
        assert d["domain"].endswith(".test")
        assert d["ip"].startswith(("192.0.2.", "198.51.100.", "203.0.113."))
    for name, data in files.items():
        if name.endswith((".csv", ".json")):
            assert b"SYNTHETIC DATA" in data
    assert len(truth.transactions) <= 900


def test_all_scenarios_and_difficulties_generate():
    from app.synthetic.generator import DIFFICULTIES, SCENARIOS
    for s in SCENARIOS:
        for d in DIFFICULTIES:
            files, truth, _ = build_bundle(Generator(s, d, "small", 1))
            assert "complaint.pdf" in files and truth.paths


def test_sealed_truth_not_reachable_from_analyst_api(client, analyst, admin, synthetic_case):
    cid = synthetic_case["case"]["id"]
    # 1. response bodies of every analyst-facing route contain no truth keys
    bodies = [json.dumps(synthetic_case)]
    for path in (f"/api/cases/{cid}", f"/api/cases/{cid}/graph", f"/api/cases/{cid}/paths", f"/api/cases/{cid}/timeline",
                 f"/api/cases/{cid}/transactions", f"/api/cases/{cid}/report.json", f"/api/synthetic/cases/{cid}/manifest",
                 f"/api/cases/{cid}/files", f"/api/cases/{cid}/parse-runs", f"/api/cases/{cid}/audit"):
        r = client.get(path, headers=analyst)
        assert r.status_code == 200, path
        bodies.append(r.text)
    blob = "\n".join(bodies)
    for leak in ("mule_accounts", "false_edges", "true_edges", "sealed_truth_ref", "\"path_id\"", "\"role\": \"mule", "campaign_vpa", "ground_truth"):
        assert leak not in blob, leak
    # 2. the sealed store lives outside the upload storage tree and is not served
    sealed_dir = os.environ["BENCHMARK_STORE_DIR"]
    assert os.listdir(sealed_dir)
    assert not os.environ["STORAGE_DIR"].startswith(sealed_dir)
    # 3. no HTTP route exposes the benchmark store (even to admin)
    for path in ("/api/benchmark", "/api/synthetic/truth", f"/api/synthetic/cases/{cid}/truth", "/api/sealed"):
        assert client.get(path, headers=admin).status_code == 404


def test_synthetic_files_go_through_public_upload_pipeline(client, analyst, synthetic_case):
    """The factory calls ingest_upload; uploading the same bytes manually must produce identical parse results."""
    files, _, _ = build_bundle(Generator("phishing_to_mule", "adversarial", "small", 11))
    new_case = client.post("/api/cases", json={"title": "manual re-upload"}, headers=analyst).json()["id"]
    name = next(n for n in files if n.endswith(".csv"))
    r = client.post(f"/api/cases/{new_case}/upload", files=[("files", (name, files[name], "text/csv"))], headers=analyst)
    assert r.status_code == 200
    manual = r.json()[0]
    auto = next(f for f in synthetic_case["files"] if f["file"]["original_name"] == name)
    assert manual["file"]["sha256"] == auto["file"]["sha256"]
    assert manual["parse_run"]["stats"]["transactions"] == auto["parse_run"]["stats"]["transactions"]
    assert manual["parse_run"]["column_mapping"] == auto["parse_run"]["column_mapping"]


def test_sealed_store_roundtrip_and_ref_validation():
    ref = sealed_store.seal({"x": 1}, "phishing_to_mule", "clean", "small", 99, "1")
    assert sealed_store.unseal(ref) == {"x": 1}
    import pytest
    with pytest.raises(ValueError):
        sealed_store.unseal("../etc/passwd")
