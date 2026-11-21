"""Integration: upload security, ingestion provenance, graph rules, counter-evidence, review workflow, reports."""
import json

import pytest

CSV_FIXTURE = (
    "Txn Date,Narration,Ref No,Debit,Credit,Balance,Account,Counterparty,Beneficiary Name\n"
    "01-03-2026 10:00:00,UPI/REF1/scam,REF1,1500.00,,8500.00,111122223333,mule1@fictbank,Mule One\n"
    "03/04/26 11:00,UPI/REF2/again,REF2,250.00,,8250.00,111122223333,mule1@fictbank,Mule One\n"
    "03/04/26 11:00,UPI/REF2/again,REF2,250.00,,8250.00,111122223333,mule1@fictbank,Mule One\n"
    "05-03-2026 09:00:00,SALARY,REF3,,50000.00,58250.00,111122223333,,\n"
).encode()


@pytest.fixture(scope="module")
def case_with_csv(client, analyst):
    cid = client.post("/api/cases", json={"title": "CSV fixture case"}, headers=analyst).json()["id"]
    r = client.post(f"/api/cases/{cid}/upload", files=[("files", ("statement.csv", CSV_FIXTURE, "text/csv"))], headers=analyst)
    assert r.status_code == 200, r.text
    return cid, r.json()[0]


def test_upload_rejects_unknown_binary(client, analyst):
    cid = client.post("/api/cases", json={"title": "bad upload"}, headers=analyst).json()["id"]
    r = client.post(f"/api/cases/{cid}/upload", files=[("files", ("evil.exe", b"MZ\x90\x00\x03\x00\x00\x00\x04", "application/octet-stream"))], headers=analyst)
    assert r.status_code == 415
    r = client.post(f"/api/cases/{cid}/upload", files=[("files", ("empty.csv", b"", "text/csv"))], headers=analyst)
    assert r.status_code == 400


def test_spoofed_extension_is_detected_by_magic_bytes(client, analyst):
    cid = client.post("/api/cases", json={"title": "spoof"}, headers=analyst).json()["id"]
    r = client.post(f"/api/cases/{cid}/upload", files=[("files", ("looks_like.csv", b"%PDF-1.4\n%%EOF", "text/csv"))], headers=analyst)
    assert r.status_code == 200
    f = r.json()[0]
    assert f["file"]["detected_kind"] == "pdf"
    assert any(w.startswith("extension_mismatch") for w in f["parse_run"]["warnings"])


def test_statement_provenance_and_flags(client, analyst, case_with_csv):
    cid, up = case_with_csv
    run = up["parse_run"]
    assert run["column_mapping"]["debit"] == "Debit"
    assert run["stats"]["transactions"] == 4
    assert run["stats"]["ambiguous_dates"] == 2
    assert run["stats"]["duplicates"] == 1
    assert any(w.startswith("balance_reconciliation_mismatch") for w in run["warnings"])
    txs = client.get(f"/api/cases/{cid}/transactions", headers=analyst).json()
    assert len(txs) == 4
    first = next(t for t in txs if t["external_reference"] == "REF1")
    assert first["amount_minor"] == 150000 and first["direction"] == "debit" and first["channel"] == "UPI"
    assert first["amount_raw"] == "1500.00"  # raw preserved
    ev = client.get(f"/api/cases/{cid}/evidence/{first['evidence_item_id']}", headers=analyst).json()
    assert ev["source_locator"]["row"] == 2 and ev["raw_value"]
    assert json.loads(ev["raw_value"])["Debit"] == "1500.00"
    dup = [t for t in txs if t["external_reference"] == "REF2"]
    assert len(dup) == 2 and sum(1 for t in dup if t["duplicate_of"]) == 1  # both kept, one flagged
    assert all(t["time_precision"] == "ambiguous" for t in dup)
    missing = next(t for t in txs if t["external_reference"] == "REF3")
    assert missing["counterparty_ref"] is None and "missing_counterparty" in missing["warnings"]  # nothing invented


def test_column_remap_preserves_original(client, analyst, case_with_csv):
    cid, up = case_with_csv
    r = client.post(f"/api/cases/{cid}/files/{up['file']['id']}/remap", json={"mapping": {"narration": "Beneficiary Name"}}, headers=analyst)
    assert r.status_code == 200
    assert r.json()["parse_run"]["column_mapping"]["narration"] == "Beneficiary Name"
    files = client.get(f"/api/cases/{cid}/files", headers=analyst).json()
    assert len({f["sha256"] for f in files}) == 1 and len(files) == 2  # same immutable original, new parse


def test_synthetic_graph_rules(client, analyst, synthetic_case):
    cid = synthetic_case["case"]["id"]
    g = client.get(f"/api/cases/{cid}/graph", headers=analyst).json()
    types = {}
    for e in g["edges"]:
        types[e["type"]] = types.get(e["type"], 0) + 1
    # shared CDN IP must produce only candidate SHARED_INFRASTRUCTURE edges, never common ownership
    assert "COMMON_OPERATOR" not in types and "COMMON_OWNER" not in types
    shared = [e for e in g["edges"] if e["type"] == "SHARED_INFRASTRUCTURE"]
    assert shared and all(e["evidence_level"] == "candidate" for e in shared)
    assert all("shared_ip_is_not_proof_of_common_control" in e["limitations"] for e in shared)
    # every edge has evidence or is explicitly a candidate
    for e in g["edges"]:
        if e["evidence_level"] not in {"candidate"}:
            d = client.get(f"/api/cases/{cid}/edges/{e['id']}", headers=analyst).json()
            assert d["supporting_evidence"] or e["type"] in {"DOCUMENTS"}, e["type"]
    # stale DNS observation (planted) is marked stale with counter-evidence
    stale = [e for e in g["edges"] if e["evidence_level"] == "stale"]
    assert stale
    d = client.get(f"/api/cases/{cid}/edges/{stale[0]['id']}", headers=analyst).json()
    assert any(c["kind"] == "observation_outside_event_window" for c in d["counter_evidence"])
    # similar names never merge: distinct entities remain, SIMILAR_NAME is candidate with conflict counter-evidence
    for e in [e for e in g["edges"] if e["type"] == "SIMILAR_NAME"]:
        assert e["evidence_level"] == "candidate"
        assert e["source"] != e["target"]
    # edge detail of a shared-infra edge returns evidence + counter-evidence, not just a score
    d = client.get(f"/api/cases/{cid}/edges/{shared[0]['id']}", headers=analyst).json()
    assert d["supporting_evidence"] and d["counter_evidence"][0]["kind"] == "multi_tenant_infrastructure"
    assert "not a calibrated probability" in d["method"]["score_semantics"]


def test_paths_and_triage(client, analyst, synthetic_case):
    cid = synthetic_case["case"]["id"]
    p = client.get(f"/api/cases/{cid}/paths", headers=analyst).json()
    assert p["paths"] and max(x["hop_count"] for x in p["paths"]) >= 2
    labels = {v["triage"]["label"] for v in p["features"].values()}
    assert labels <= {"possible_mule_pattern_requires_review", "weak_signal", "no_rule_signal"}
    assert "criminal" not in json.dumps(p).lower()


def test_review_workflow_requires_supervisor_for_candidate_promotion(client, analyst, supervisor, synthetic_case):
    cid = synthetic_case["case"]["id"]
    g = client.get(f"/api/cases/{cid}/graph", headers=analyst).json()
    cand = next(e for e in g["edges"] if e["evidence_level"] == "candidate")
    r = client.post(f"/api/cases/{cid}/edges/{cand['id']}/review", json={"decision": "supported", "reason": "x"}, headers=analyst)
    assert r.status_code == 403
    r = client.post(f"/api/cases/{cid}/edges/{cand['id']}/review", json={"decision": "needs_more_evidence", "reason": "need identifier bridge"}, headers=analyst)
    assert r.status_code == 200
    # supervisor needs case access; add via admin? supervisors are not auto-members: expect 404 unless member
    r = client.post(f"/api/cases/{cid}/edges/{cand['id']}/review", json={"decision": "supported", "reason": "verified"}, headers=supervisor)
    assert r.status_code == 404
    audit = client.get(f"/api/cases/{cid}/audit", headers=analyst).json()
    assert any(a["action"] == "edge.reviewed" for a in audit)


def test_timeline_marks_uncertain_times(client, analyst, case_with_csv):
    cid, _ = case_with_csv
    tl = client.get(f"/api/cases/{cid}/timeline", headers=analyst).json()
    assert any(e["time_precision"] == "ambiguous" for e in tl)


def test_reports(client, analyst, synthetic_case):
    cid = synthetic_case["case"]["id"]
    rep = client.get(f"/api/cases/{cid}/report.json", headers=analyst).json()
    assert rep["case"]["data_status"] == "SYNTHETIC DATA"
    assert "human verification required" in rep["disclaimer"]
    assert rep["sources"] and all(len(s["sha256"]) == 64 for s in rep["sources"])
    assert rep["relationships"] and rep["counter_evidence"]
    assert all("sources" in r for r in rep["relationships"])
    txt = json.dumps(rep).lower()
    assert "court-proof" not in txt and "admissible" not in txt.replace("not establish guilt, ownership or legal admissibility", "")
    pdf = client.get(f"/api/cases/{cid}/report.pdf", headers=analyst)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    csv_ = client.get(f"/api/cases/{cid}/report/transactions.csv", headers=analyst)
    assert csv_.status_code == 200 and csv_.text.startswith("SYNTHETIC DATA")
