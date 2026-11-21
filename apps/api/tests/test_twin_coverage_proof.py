"""Digital twin, victim journey, replay, evidence coverage, proof manifest + offline verifier, temporal fusion."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def mirage(client, analyst):
    r = client.post("/api/synthetic/generate", json={"scenario_type": "desert_mirage", "difficulty": "messy", "size": "small", "seed": 2002}, headers=analyst)
    assert r.status_code == 201, r.text
    return r.json()["case"]["id"]


def test_twin_event_classes_and_manual_events_stay_reported(client, analyst, mirage):
    tw = client.get(f"/api/cases/{mirage}/twin", headers=analyst).json()
    classes = set(tw["counts_by_class"])
    assert {"directly_observed", "corroborated", "reported"} <= classes and "extracted" in classes
    assert all(e["evidence_class"] in tw["legend"] for e in tw["events"])
    assert all(l["type"] != "CAUSES" for l in tw["links"]) and any(l["type"] == "REPORTED_BEFORE" and "not causation" in l["note"] for l in tw["links"])
    r = client.post(f"/api/cases/{mirage}/twin/events", json={"event_type": "VICTIM_CONTACT_REPORTED", "description": "Victim says a call came at 10:12", "event_time": "2026-03-01T04:42:00Z", "time_precision": "minute"}, headers=analyst)
    assert r.status_code == 201 and r.json()["evidence_class"] == "reported"
    tw2 = client.get(f"/api/cases/{mirage}/twin?layers=victim_journey", headers=analyst).json()
    ev = next(e for e in tw2["events"] if e["attributes"].get("manual_entry"))
    assert ev["evidence_class"] == "reported" and ev["layer"] == "victim_journey"
    assert client.post(f"/api/cases/{mirage}/twin/events", json={"event_type": "NOT_A_TYPE", "description": "unknown type"}, headers=analyst).status_code == 400


def test_victim_journey_reports_and_checks(client, analyst, mirage):
    j = client.get(f"/api/cases/{mirage}/twin/journey", headers=analyst).json()
    assert j["journeys"] and all(jj["evidence_class"] == "reported" for jj in j["journeys"])
    statuses = {c["status"] for jj in j["journeys"] for c in jj["consistency_checks"]}
    assert "corroborated_by_statement" in statuses


def test_replay_is_monotone_in_ingestion_time(client, analyst, mirage):
    rp = client.get(f"/api/cases/{mirage}/twin/replay", headers=analyst).json()
    first = rp["first_event_at"]
    early = client.get(f"/api/cases/{mirage}/twin/replay?at={first}&compare_to={rp['last_event_at']}", headers=analyst).json()
    assert early["snapshot"]["events"] <= early["compare"]["snapshot"]["events"]
    assert early["compare"]["snapshot"]["files"] >= early["snapshot"]["files"]


def test_coverage_detects_missing_month_and_never_zero(client, analyst, mirage):
    cov = client.get(f"/api/cases/{mirage}/coverage", headers=analyst).json()
    partial = [s for s in cov["statements"] if s["state"] == "PARTIAL_COVERAGE"]
    assert partial and partial[0]["gaps"] and partial[0]["gaps"][0]["unexplained_balance_change_minor"] != 0 and partial[0]["gaps"][0]["span_days"] > 20
    assert cov["not_supplied"] and all(r["state"] == "NOT_SUPPLIED" for r in cov["not_supplied"])
    assert all("not absence of activity" in r["note"] for r in cov["not_supplied"])
    assert cov["negative_claim_warnings"] and all("Do not assert" in w["warning"] for w in cov["negative_claim_warnings"])
    assert any(i["state"] == "CURRENT_ONLY" for i in cov["infrastructure"])
    assert any(n["evidence"].startswith("Statement of") for n in cov["next_evidence"])
    assert "OBSERVED_ZERO" not in cov["summary"] or all(s["observed_zero_months"] == [] or not s["gaps"] for s in cov["statements"])


def test_proof_manifest_verifies_offline_and_detects_tampering(client, analyst, mirage, tmp_path):
    m = client.get(f"/api/cases/{mirage}/paths/0/proof.json", headers=analyst).json()
    assert m["integrity"]["manifest_sha256"] and m["hops"] and m["rules"]["path_algorithm_version"] == "2.0.0"
    assert "mule_accounts" not in json.dumps(m) and "false_edges" not in json.dumps(m)  # no sealed truth leaks
    (tmp_path / "proof.json").write_text(json.dumps(m), encoding="utf-8")
    fdir = tmp_path / "files"
    fdir.mkdir()
    for f in m["source_files"]:
        r = client.get(f"/api/cases/{mirage}/files/{f['id']}/download", headers=analyst)
        assert r.status_code == 200
        (fdir / f["name"]).write_bytes(r.content)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_proof.py"), str(tmp_path / "proof.json"), "--files", str(fdir), "--json", str(tmp_path / "out.json")], capture_output=True, text=True, env=env)
    assert res.returncode == 0, res.stdout + res.stderr
    out = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert out["verdict"] == "PASS" and out["failed"] == 0 and any(c["check"].startswith("hop1_amount_rederived") and c["status"] == "pass" for c in out["checks"])
    # tamper with a cited file -> FAIL
    target = fdir / m["source_files"][0]["name"]
    target.write_bytes(target.read_bytes() + b"\n#tampered")
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_proof.py"), str(tmp_path / "proof.json"), "--files", str(fdir)], capture_output=True, text=True, env=env)
    assert res.returncode == 1 and "MODIFIED" in res.stdout
    # tamper with the manifest itself -> FAIL
    m2 = dict(m)
    m2["hops"] = [dict(m["hops"][0], amount_minor=m["hops"][0]["amount_minor"] + 100)] + m["hops"][1:]
    (tmp_path / "proof2.json").write_text(json.dumps(m2), encoding="utf-8")
    res = subprocess.run([sys.executable, str(ROOT / "scripts" / "verify_proof.py"), str(tmp_path / "proof2.json")], capture_output=True, text=True, env=env)
    assert res.returncode == 1 and "manifest_sha256" in res.stdout
    assert client.get(f"/api/cases/{mirage}/paths/0/proof.pdf", headers=analyst).content[:4] == b"%PDF"
    assert client.get(f"/api/cases/{mirage}/paths/999/proof.json", headers=analyst).status_code == 404


def test_temporal_fusion_current_only_cannot_support_history(client, analyst, mirage):
    tp = client.get(f"/api/cases/{mirage}/temporal", headers=analyst).json()
    cur = [c for c in tp["claims"] if c["current_only"]]
    assert cur and all(c["verdict"] == "cannot_support_historical_claim" for c in cur)
    assert any(c["verdict"] == "temporal_contradiction" for c in tp["claims"])  # stale planted observation
    unknown_tz = [r for r in tp["records"] if "unknown" in str(r["source_timezone"])]
    assert unknown_tz, "non-statement records must not get an assumed timezone"
    amb = [r for r in tp["records"] if r["interval"]["precision"] == "ambiguous"]
    assert amb and all(r["interval"].get("alternative_reading") or r["interval"]["end"] for r in amb)
    win = client.get(f"/api/cases/{mirage}/temporal?window_from=2000-01-01T00:00:00Z&window_to=2000-01-02T00:00:00Z", headers=analyst).json()["window"]
    assert win["included"] == [] and win["excluded"]


def test_other_user_cannot_read_twin_or_proof(client, other_analyst, mirage):
    assert client.get(f"/api/cases/{mirage}/twin", headers=other_analyst).status_code == 404
    assert client.get(f"/api/cases/{mirage}/paths/0/proof.json", headers=other_analyst).status_code == 404
