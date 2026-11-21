"""Victim claims / restitution readiness (no double counting, no auto allocation, evidence-backed holds) and cooperation pack validation."""
import io
import zipfile

import pytest


@pytest.fixture(scope="module")
def mv_case(client, analyst):
    r = client.post("/api/synthetic/generate", json={"scenario_type": "multi_victim_network", "difficulty": "clean", "size": "small", "seed": 31}, headers=analyst)
    assert r.status_code == 201, r.text
    body = r.json()
    assert any(f["file"]["original_name"] == "bank_hold_notice.txt" for f in body["files"])
    return body["case"]["id"]


def _victim_debits(client, analyst, cid):
    txs = client.get(f"/api/cases/{cid}/transactions", headers=analyst).json()
    # victims' statements: debits from victim accounts to the first-layer VPA
    out = [t for t in txs if t["direction"] == "debit" and t["counterparty_ref"] and "@" in (t["counterparty_ref"] or "") and t["amount_minor"]]
    assert len(out) >= 3
    return out


def test_claims_reconciliation_no_double_count_and_no_allocation(client, analyst, supervisor, admin, mv_case):
    cid = mv_case
    debits = _victim_debits(client, analyst, cid)
    ids = []
    for i, t in enumerate(debits[:3]):
        r = client.post(f"/api/cases/{cid}/claims", json={"victim_label": f"Victim {i + 1}", "complaint_ack_no": f"ACK-{i + 1}", "fir_reference": "FIR 12/2026",
                                                           "claimed_loss_minor": t["amount_minor"] + 50000}, headers=analyst)
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
        assert client.post(f"/api/cases/{cid}/claims/{ids[-1]}/links", json={"transaction_id": t["id"]}, headers=analyst).status_code == 201
    # the same transaction linked to a second claim => competing, counted once in account inflow
    assert client.post(f"/api/cases/{cid}/claims/{ids[1]}/links", json={"transaction_id": debits[0]["id"]}, headers=analyst).status_code == 201
    assert client.post(f"/api/cases/{cid}/claims/{ids[1]}/links", json={"transaction_id": debits[0]["id"]}, headers=analyst).status_code == 409
    assert client.post(f"/api/cases/{cid}/claims/{ids[0]}/links", json={"transaction_id": debits[0]["id"], "amount_minor": debits[0]["amount_minor"] + 1}, headers=analyst).status_code in {400, 409}
    rec = client.get(f"/api/cases/{cid}/claims", headers=analyst).json()
    assert rec["totals"]["unallocated_held_minor"] is None  # never computed: allocation is human
    distinct = sum(t["amount_minor"] for t in debits[:3])
    assert rec["totals"]["traced_distinct_minor"] == distinct  # transaction shared by two claims counted once
    assert any(c["competing"] for c in rec["claims"]) and rec["competing_transactions"]
    for c in rec["claims"]:
        assert c["unresolved_minor"] == max(0, c["claimed_minor"] - c["traced_minor"])
    # hold needs a documented source: statement rows are refused, the hold notice is accepted
    cands = client.get(f"/api/cases/{cid}/claims/evidence-candidates", headers=analyst).json()
    notice = next(c for c in cands if c["file"] == "bank_hold_notice.txt")
    acct = rec["accounts"][0]["account"]
    stmt_ev = debits[0]["evidence_item_id"]
    r = client.post(f"/api/cases/{cid}/claims/funds", json={"kind": "held", "account_ref": acct, "amount_minor": 100, "source_evidence_item_id": stmt_ev, "source_kind": "bank_notice"}, headers=analyst)
    assert r.status_code == 400
    r = client.post(f"/api/cases/{cid}/claims/funds", json={"kind": "held", "account_ref": acct, "amount_minor": rec["accounts"][0]["traced_inflow_minor"] // 2,
                                                            "source_evidence_item_id": notice["evidence_item_id"], "source_kind": "synthetic_simulated", "reference": "HOLD-SYN-31"}, headers=analyst)
    assert r.status_code == 201 and r.json()["is_simulated"] is True
    rec = client.get(f"/api/cases/{cid}/claims", headers=analyst).json()
    a = next(x for x in rec["accounts"] if x["account"] == acct)
    assert a["held_is_simulated"] and a["documented_held_minor"] > 0
    assert a["oversubscribed"] is True and a["shortfall_minor"] > 0  # claims exceed documented hold: flagged, not allocated
    # approval states: analyst -> investigator_checked; supervisor needed beyond
    assert client.post(f"/api/cases/{cid}/claims/{ids[0]}/advance", headers=analyst).json()["status"] == "investigator_checked"
    assert client.post(f"/api/cases/{cid}/claims/{ids[0]}/advance", headers=analyst).status_code == 403
    client.post(f"/api/crosscase/cases/{cid}/members", json={"email": "supervisor@demo.local", "role_in_case": "supervisor"}, headers=analyst)
    assert client.post(f"/api/cases/{cid}/claims/{ids[0]}/advance", headers=supervisor).json()["status"] == "supervisor_checked"
    assert client.post(f"/api/cases/{cid}/claims/{ids[0]}/advance", headers=supervisor).json()["status"] == "export_ready"
    assert client.post(f"/api/cases/{cid}/claims/{ids[0]}/advance", headers=supervisor).status_code == 400
    # duplicate claim detection
    client.post(f"/api/cases/{cid}/claims", json={"victim_label": "Victim 1 again", "complaint_ack_no": "ACK-1", "fir_reference": "FIR 12/2026", "claimed_loss_minor": debits[0]["amount_minor"] + 50000}, headers=analyst)
    rec = client.get(f"/api/cases/{cid}/claims", headers=analyst).json()
    assert rec["duplicate_claims"]
    # exports + audit
    pj = client.get(f"/api/cases/{cid}/claims/pack.json", headers=analyst).json()
    assert "allocation" in pj["disclaimer"].lower() and pj["sources"] and pj["manual_review_checklist"]
    pdf = client.get(f"/api/cases/{cid}/claims/pack.pdf", headers=analyst)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    actions = {a["action"] for a in client.get(f"/api/cases/{cid}/audit", headers=analyst).json()}
    assert {"claim.created", "claim.transaction_linked", "funds.recorded", "claim.status_advanced", "claims.pack_exported"} <= actions


def test_claims_idor(client, other_analyst, mv_case):
    assert client.get(f"/api/cases/{mv_case}/claims", headers=other_analyst).status_code == 404


def test_cooperation_pack_validation_endorsement_and_export(client, analyst, supervisor, mv_case):
    cid = mv_case
    files = client.get(f"/api/cases/{cid}/files", headers=analyst).json()
    pdf_file = next(f for f in files if f["detected_kind"] == "pdf")
    r = client.post(f"/api/cases/{cid}/cooperation", json={"fields": {"officer_name": "Insp. Test", "fir_gist": "too short"}}, headers=analyst)
    assert r.status_code == 201
    p = r.json()
    v = p["validation"]
    assert not v["complete"] and "officer_rank" in v["missing_fields"] and "fir_gist" in v["out_of_bounds"] and "fir_pdf" in v["missing_attachments"]
    # endorsement refused while incomplete
    client.post(f"/api/crosscase/cases/{cid}/members", json={"email": "supervisor@demo.local", "role_in_case": "supervisor"}, headers=analyst)
    assert client.post(f"/api/cases/{cid}/cooperation/{p['id']}/endorse", headers=supervisor).status_code == 400
    full = {k: "x" for k in ["officer_name", "officer_rank", "department", "officer_contact", "state", "district", "police_station", "fir_number",
                              "supervising_officer_name", "supervising_officer_designation", "supervising_officer_contact"]}
    full.update({"fir_year": "2026", "fir_gist": "Victim paid a fake KYC portal; funds moved through two accounts in Rajasthan.", "assistance_details": "Request account holder KYC and CCTV of withdrawal from the beneficiary bank branch."})
    r = client.post(f"/api/cases/{cid}/cooperation?pack_id={p['id']}", json={"fields": full, "fir_file_id": pdf_file["id"], "endorsement_file_id": pdf_file["id"], "attachment_file_ids": [files[0]["id"]]}, headers=analyst)
    assert r.status_code == 201 and r.json()["validation"]["complete"]
    assert client.get(f"/api/cases/{cid}/cooperation/{p['id']}/export.zip", headers=analyst).status_code == 400  # not endorsed yet
    assert client.post(f"/api/cases/{cid}/cooperation/{p['id']}/endorse", headers=analyst).status_code == 403
    e = client.post(f"/api/cases/{cid}/cooperation/{p['id']}/endorse", headers=supervisor)
    assert e.status_code == 200 and e.json()["status"] == "export_ready"
    z = client.get(f"/api/cases/{cid}/cooperation/{p['id']}/export.zip", headers=analyst)
    assert z.status_code == 200
    with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
        names = zf.namelist()
        assert "manifest.json" in names and "cooperation_request_summary.pdf" in names and any(n.startswith("fir/") for n in names)
        import json
        m = json.loads(zf.read("manifest.json"))
        assert all(len(a["sha256"]) == 64 for a in m["attachments"]) and m["fields"]["fir_year"] == "2026" and "nothing is transmitted" in m["note"].lower()
    actions = {a["action"] for a in client.get(f"/api/cases/{cid}/audit", headers=analyst).json()}
    assert {"cooperation.created", "cooperation.endorsed", "cooperation.exported"} <= actions
