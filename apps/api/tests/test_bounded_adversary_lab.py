"""Bounded fund provenance, evidence adversary, counterfactual lab, branches, resilience, intervention, integrity, campaign, privacy, rules."""
import json

import pytest

from app.db.session import SessionLocal
from app.models import Relationship, Transaction


@pytest.fixture(scope="module")
def case_id(client, analyst):
    r = client.post("/api/synthetic/generate", json={"scenario_type": "commingled_funds", "difficulty": "messy", "size": "small", "seed": 4004}, headers=analyst)
    assert r.status_code == 201
    cid = r.json()["case"]["id"]
    assert client.post(f"/api/crosscase/cases/{cid}/members", json={"email": "supervisor@demo.local", "role_in_case": "supervisor"}, headers=analyst).status_code == 201
    return cid


def test_bounded_flow_bounds_are_sound(client, analyst, case_id):
    bf = client.get(f"/api/cases/{case_id}/bounded-flow", headers=analyst).json()
    assert bf["attribution_status"] in {"BOUNDED_UNDER_CONSTRAINTS", "EXACT_UNDER_CONSTRAINTS"}, bf.get("warnings")
    origin = bf["origin"]["amount_minor"]
    for h in bf["hops"]:
        assert 0 <= h["minimum_attributable_minor"] <= h["maximum_attributable_minor"] <= min(h["observed_transfer_minor"], origin)
        assert h["not_attributable_from_evidence_minor"] == h["observed_transfer_minor"] - h["maximum_attributable_minor"]
        assert h["explanation"]
    assert sum(h["maximum_attributable_minor"] for h in bf["hops"]) <= origin * len(bf["hops"])  # no witness exceeds the origin
    assert bf["method"] == "time_expanded_two_commodity_lp" and bf["constraints"]["inequalities"] > 0
    assert any("fungible" in lim for lim in bf["limitations"])
    if any(not h["exact"] for h in bf["hops"]):
        assert bf["possible_not_invariant"]
    fifo = client.get(f"/api/cases/{case_id}/bounded-flow?scenario=fifo", headers=analyst).json()
    assert "fifo" in fifo["scenarios"] and "assumption" in fifo["scenarios"]["fifo"]["label"].lower()
    assert client.get(f"/api/cases/{case_id}/bounded-flow?scenario=prorata", headers=analyst).status_code == 400


def test_bounded_flow_undetermined_without_statement(client, analyst, case_id):
    paths = client.get(f"/api/cases/{case_id}/paths", headers=analyst).json()["paths"]
    holders = {t["account_ref"] for t in client.get(f"/api/cases/{case_id}/transactions", headers=analyst).json()}
    idx = next((i for i, p in enumerate(paths) if p["accounts"][1] not in holders), None)
    if idx is None:
        pytest.skip("no path starting at an account without a statement")
    bf = client.get(f"/api/cases/{case_id}/bounded-flow?path_index={idx}", headers=analyst).json()
    assert bf["attribution_status"] == "UNDETERMINED" and bf["missing_evidence"]


def test_adversary_states_actions_and_dissent(client, analyst, supervisor, case_id):
    summ = client.get(f"/api/cases/{case_id}/adversary", headers=analyst).json()
    assert summ["rows"] and set(summ["by_state"]) <= set(summ["states"])
    shared = next(r for r in summ["rows"] if r["type"] == "SHARED_INFRASTRUCTURE")
    ch = client.get(f"/api/cases/{case_id}/adversary/{shared['relationship_id']}", headers=analyst).json()
    rep = ch["report"]
    assert ch["state"] == "candidate" and rep["strength"]["kind"] == "shared-provider context"
    assert any("Shared commercial hosting" in a["hypothesis"] for a in rep["alternative_hypotheses"]) and rep["counter_evidence"]
    assert "do not establish who controls" in rep["what_records_establish"]
    # analyst cannot accept a candidate; supervisor can; dissent is preserved as a hypothesis
    r = client.post(f"/api/cases/{case_id}/adversary/{shared['relationship_id']}/action", json={"action": "accept", "reason": "looks connected to me"}, headers=analyst)
    assert r.status_code == 403
    r = client.post(f"/api/cases/{case_id}/adversary/{shared['relationship_id']}/action", json={"action": "record_dissent", "reason": "multi-tenant CDN; no identifier bridge"}, headers=analyst)
    assert r.status_code == 200 and r.json()["state"] in {"contested", "candidate"}
    hyps = client.get(f"/api/cases/{case_id}/hypotheses", headers=analyst).json()
    assert any(h["title"].startswith("Dissent") and h["status"] == "disputed" for h in hyps)
    r = client.post(f"/api/cases/{case_id}/adversary/{shared['relationship_id']}/action", json={"action": "retain_as_candidate", "reason": "await hosting records"}, headers=supervisor)
    assert r.status_code == 200 and r.json()["report"]["review_history"][-1]["decision"] == "needs_more_evidence"
    # contradictory timestamps remain visible on a stale observation
    stale = [r for r in summ["rows"] if r["state"] == "stale"]
    if stale:
        ch2 = client.get(f"/api/cases/{case_id}/adversary/{stale[0]['relationship_id']}", headers=analyst).json()
        assert ch2["report"]["temporal_compatibility"]["compatible_with_events"] is False


def test_hypothesis_versioning_and_independent_review(client, analyst, supervisor, case_id):
    h = client.post(f"/api/cases/{case_id}/hypotheses", json={"title": "Collection account knowingly operated", "statement": "v1", "kind": "role"}, headers=analyst).json()
    assert client.post(f"/api/cases/{case_id}/hypotheses/{h['id']}", json={"status": "supported", "reason": "gut feeling"}, headers=analyst).status_code == 400  # no evidence
    u = client.post(f"/api/cases/{case_id}/hypotheses/{h['id']}", json={"statement": "v2 wording", "reason": "clarified"}, headers=analyst).json()
    assert u["version"] == 2 and len(u["history"]) == 2 and u["history"][0]["statement"] == "v1"
    assert client.post(f"/api/cases/{case_id}/hypotheses/{h['id']}/reviews", json={"decision": "agree", "rationale": "I wrote it so I agree with it"}, headers=analyst).status_code == 403
    blind = client.get(f"/api/cases/{case_id}/hypotheses/{h['id']}/review-view?blind=true", headers=supervisor).json()
    assert blind["analyst_conclusion"] is None
    rv = client.post(f"/api/cases/{case_id}/hypotheses/{h['id']}/reviews", json={"decision": "disagree", "rationale": "possession evidence does not show knowledge", "mode": "blind"}, headers=supervisor).json()
    assert rv["dissent_on_file"] is True and rv["reviews"][0]["is_dissent"] and rv["status"] in {"under_review", "disputed"}


def test_counterfactual_lab_never_mutates_db(client, analyst, case_id):
    with SessionLocal() as db:
        before = (db.query(Relationship).filter(Relationship.case_id == case_id).count(), db.query(Transaction).filter(Transaction.case_id == case_id).count())
    out = {}
    for prof in ["shared_hosting", "stale_dns", "ocr_substitution", "missing_intermediary_statement", "duplicate_row", "compromised_account", "identifier_rotation"]:
        r = client.post(f"/api/cases/{case_id}/lab/run", json={"profile": prof, "seed": 7}, headers=analyst)
        assert r.status_code == 200, r.text
        out[prof] = r.json()
        assert out[prof]["safeguard_check"]["common_operator_asserted"] is False and out[prof]["scenario"]["source_evidence_immutable"] is True
    assert out["shared_hosting"]["robustness"] == "STABLE" and out["stale_dns"]["robustness"] == "STABLE" and out["compromised_account"]["robustness"] == "STABLE"
    assert out["missing_intermediary_statement"]["robustness"] == "CHANGED" and out["missing_intermediary_statement"]["findings_disappeared"]
    assert out["ocr_substitution"]["robustness"] in {"CHANGED", "FRAGILE"}
    assert out["duplicate_row"]["robustness"] == "STABLE"
    # determinism
    r1 = client.post(f"/api/cases/{case_id}/lab/run", json={"profile": "benign_lookalike_hop", "seed": 11}, headers=analyst).json()
    r2 = client.post(f"/api/cases/{case_id}/lab/run", json={"profile": "benign_lookalike_hop", "seed": 11}, headers=analyst).json()
    assert r1["revised_finding"] == r2["revised_finding"]
    with SessionLocal() as db:
        after = (db.query(Relationship).filter(Relationship.case_id == case_id).count(), db.query(Transaction).filter(Transaction.case_id == case_id).count())
    assert before == after
    assert client.post(f"/api/cases/{case_id}/lab/run", json={"profile": "nope"}, headers=analyst).status_code == 400
    assert len(client.get(f"/api/cases/{case_id}/lab/runs", headers=analyst).json()) >= 7


def test_branches_compare_invariants(client, analyst, case_id):
    assert client.post(f"/api/cases/{case_id}/branches", json={"name": "bad", "assumptions": {"delete_file": True}}, headers=analyst).status_code == 400
    b = client.post(f"/api/cases/{case_id}/branches", json={"name": "swap ambiguous dates", "hypothesis_statement": "dates are mm/dd", "assumptions": {"date_interpretation": "swap_ambiguous"}}, headers=analyst).json()
    cmp = client.get(f"/api/cases/{case_id}/branches/{b['id']}/compare", headers=analyst).json()
    assert cmp["source_immutable"] is True and cmp["evidence_changed_since_branch"] is False
    assert isinstance(cmp["comparison"]["invariant_paths"], list) and "amount_delta_minor" in cmp["comparison"]
    b2 = client.post(f"/api/cases/{case_id}/branches", json={"name": "empty", "assumptions": {}}, headers=analyst).json()
    cmp2 = client.get(f"/api/cases/{case_id}/branches/{b2['id']}/compare", headers=analyst).json()
    assert cmp2["comparison"]["base_only"] == [] and cmp2["comparison"]["branch_only"] == []


def test_resilience_and_chokepoints(client, analyst, case_id):
    ck = client.get(f"/api/cases/{case_id}/chokepoints", headers=analyst).json()
    assert ck["rows"] and "not proof of criminality" in ck["limitations"][0] and "candidate relationships" in ck["excluded_edges"][0]
    txs = client.get(f"/api/cases/{case_id}/transactions", headers=analyst).json()
    holders = {t["account_ref"] for t in txs}
    coll = max(holders, key=lambda h: sum(t["amount_minor"] or 0 for t in txs if t["account_ref"] == h and t["direction"] == "credit"))  # first-layer account
    assert any(r["account"] == coll for r in ck["rows"])
    paths_before = client.get(f"/api/cases/{case_id}/paths", headers=analyst).json()["paths"]
    sim = client.post(f"/api/cases/{case_id}/resilience/simulate", json={"remove_accounts": [coll]}, headers=analyst).json()
    assert sim["baseline_mutated"] is False and sim["diff"]["paths_disconnected"] >= 1 and sim["assumptions"]
    assert client.get(f"/api/cases/{case_id}/paths", headers=analyst).json()["paths"] == paths_before
    sub = client.post(f"/api/cases/{case_id}/resilience/simulate", json={"remove_accounts": [coll], "substitutions": {coll: "HYPOTHETICAL-NEW-ACCOUNT"}}, headers=analyst).json()
    assert "HYPOTHETICAL-NEW-ACCOUNT" in sub["diff"]["hypothetical_nodes"] and any("ASSUMPTION" in a for a in sub["assumptions"])
    assert sub["diff"]["paths_with_hypothetical_route_only"] >= 1
    assert len(client.get(f"/api/cases/{case_id}/resilience/scenarios", headers=analyst).json()) >= 2


def test_intervention_requires_acknowledgement_and_separates_amounts(client, analyst, case_id):
    # the first-layer account: a statement holder that receives credits from other holders (victims)
    txs = client.get(f"/api/cases/{case_id}/transactions", headers=analyst).json()
    holders = {t["account_ref"] for t in txs}
    inflow = {h: sum(t["amount_minor"] or 0 for t in txs if t["account_ref"] == h and t["direction"] == "credit") for h in holders}
    coll = max(inflow, key=inflow.get)
    r0 = client.get(f"/api/cases/{case_id}/intervention/{coll}", headers=analyst).json()
    assert r0["scenarios"] == [] and any("acknowledges" in w for w in r0["warnings"])
    r1 = client.get(f"/api/cases/{case_id}/intervention/{coll}?acknowledged=true", headers=analyst).json()
    led = r1["ledger"]
    assert led["observed_balance_minor"] != led["investigated_inflows_minor"]
    assert led["other_inflows_minor_not_labelled"] > 0  # commingled salary credit
    whole = next(s for s in r1["scenarios"] if s["scenario"] == "whole_account_restriction")
    scoped = next(s for s in r1["scenarios"] if s["scenario"] == "transaction_scoped_amount")
    assert all(s["hypothetical"] for s in r1["scenarios"]) and whole["unrelated_counterparties_potentially_affected"] >= scoped["unrelated_counterparties_potentially_affected"]
    assert "unknown" in r1["unrelated_activity"]["unknown_population"] and "not labelled" in r1["unrelated_activity"]["labelling"]
    assert "not inferred from name" in r1["account_type"]
    unknown = client.get(f"/api/cases/{case_id}/intervention/NO-SUCH-ACCOUNT?acknowledged=true", headers=analyst).json()
    assert unknown["status"] == "UNDETERMINED" and unknown["ledger"]["unknown"]


def test_integrity_row_level_and_provisional(client, analyst):
    case = client.post("/api/cases", json={"title": "integrity probe"}, headers=analyst).json()["id"]
    csv = ("Txn Date,Narration,Ref No,Debit,Credit,Balance,Account,Counterparty,Beneficiary Name\n"
           "01-03-2026 10:00:00,UPI/R1/x,R1,,1000.00,11000.00,111122223333,a@fictbank,A\n"
           "02-03-2026 10:00:00,IMPS/R2/y,R2,400.00,,10600.00,111122223333,444455556666,B\n"
           "03-03-2026 10:00:00,IMPS/R3/z,R3,100.00,,10600.00,111122223333,777788889999,C\n"   # break: expected 10500
           "03-03-2026 10:00:00,IMPS/R3/z,R3,100.00,,10600.00,111122223333,777788889999,C\n")  # duplicate row
    r = client.post(f"/api/cases/{case}/upload", files=[("files", ("stmt.csv", csv.encode(), "text/csv"))], headers=analyst)
    assert r.status_code == 200
    rep = client.get(f"/api/cases/{case}/integrity", headers=analyst).json()
    f = rep["files"][0]
    kinds = {(a["kind"], a["row"]) for a in f["statement_forensics"]["anomalies"]}
    assert any(k == "running_balance_break" for k, _ in kinds) and any(k == "duplicate_row" for k, _ in kinds)
    brk = next(a for a in f["statement_forensics"]["anomalies"] if a["kind"] == "running_balance_break")
    assert "difference 10000 paise" in brk["detail"] and brk["row"] is not None
    assert f["file_integrity"]["match"] is True and f["source_authenticity"]["verified"] is False and "bank_digital_export" in f["source_authenticity"]["provenance_class"]
    assert f["dimensions"]["arithmetic_consistency"] == "inconsistent" and rep["provisional_transaction_ids"]
    g = client.get(f"/api/cases/{case}/graph", headers=analyst).json()
    prov = [e for e in g["edges"] if e["type"] == "TRANSFERRED_TO" and "provisional_disputed_statement_row" in e["limitations"]]
    assert prov, "disputed rows must mark their edges provisional"
    assert client.get(f"/api/cases/{case}/transactions", headers=analyst).json().__len__() == 4  # originals preserved


def test_campaign_rotation_vs_benign(client, analyst):
    a = client.post("/api/synthetic/generate", json={"scenario_type": "desert_mirage", "difficulty": "messy", "size": "small", "seed": 5005}, headers=analyst).json()["case"]["id"]
    b = client.post("/api/synthetic/generate", json={"scenario_type": "identifier_rotation_campaign", "difficulty": "identifier_rotation", "size": "small", "seed": 5105}, headers=analyst).json()["case"]["id"]
    benign = client.post("/api/synthetic/generate", json={"scenario_type": "benign_lookalike", "difficulty": "messy", "size": "small", "seed": 5005}, headers=analyst).json()["case"]["id"]
    res = client.post("/api/campaign/compare", json={"case_ids": [a, b, benign]}, headers=analyst).json()
    pairs = {tuple(sorted((p["case_a"], p["case_b"]))): p for p in res["pairs"]}
    ab = pairs[tuple(sorted((a, b)))]
    assert ab["relationship_status"].startswith("CANDIDATE_PATTERN_SIMILARITY") and ab["identifier_rotation"]["rotation_candidate"] is True
    for other in (pairs[tuple(sorted((a, benign)))], pairs[tuple(sorted((b, benign)))]):
        assert other["relationship_status"] in {"LOW_PATTERN_SIMILARITY", "INSUFFICIENT_EVIDENCE"}, other["aggregate_score_not_probability"]
    assert all("does not establish common ownership" in p["limitations"][0] for p in res["pairs"])
    assert "probability" not in json.dumps(ab["dimension_results"]).lower()


def test_privacy_tokens_disabled_then_enabled(client, analyst, supervisor, monkeypatch, case_id):
    assert client.get("/api/privacy/status", headers=analyst).json()["enabled"] is False
    other = client.post("/api/synthetic/generate", json={"scenario_type": "commingled_funds", "difficulty": "messy", "size": "small", "seed": 4004, "title": "same seed twin"}, headers=analyst).json()["case"]["id"]
    assert client.post("/api/privacy/match", json={"case_ids": [case_id, other]}, headers=analyst).json()["status"] == "disabled"
    monkeypatch.setenv("CROSSCASE_TOKEN_KEY", "test-key-not-for-production")
    res = client.post("/api/privacy/match", json={"case_ids": [case_id, other]}, headers=analyst).json()
    assert res["matches"] and all(m["raw_value"] is None for m in res["matches"]) and "not anonymisation" in res["limitations"][0]
    eid = res["matches"][0]["entity_ids"][0]
    assert client.post("/api/privacy/reveal", json={"entity_id": eid, "purpose": "cross-case verification of bridge"}, headers=analyst).status_code == 403
    assert client.post("/api/privacy/reveal", json={"entity_id": eid, "purpose": "short"}, headers=supervisor).status_code in {400, 422}
    r = client.post("/api/privacy/reveal", json={"entity_id": eid, "purpose": "cross-case verification of bridge"}, headers=supervisor)
    assert r.status_code == 200 and r.json()["audited"] is True


def test_rule_compiler_gates(client, analyst, supervisor):
    r = client.post("/api/rules/compile", json={"name": "collect-and-forward", "typology": "collect_and_forward", "seeds": [9001, 9002]}, headers=analyst)
    assert r.status_code == 201
    rule = r.json()
    ev = rule["evaluation"]
    assert ev["cases"] == 2 * 11 and ev["precision"] is not None and ev["recall"] is not None and "Synthetic-only" in ev["limits"][0]
    assert rule["approval_status"] == "draft" and rule["deployment"].startswith("never")
    assert client.post(f"/api/rules/{rule['id']}/decision", json={"decision": "approved", "reason": "reviewed"}, headers=analyst).status_code == 403
    assert client.post(f"/api/rules/{rule['id']}/decision", json={"decision": "approved", "reason": "reviewed on held-out seeds"}, headers=supervisor).json()["approval_status"] == "approved"
    assert client.post("/api/rules/compile", json={"name": "bad rule", "typology": "custom", "conditions": [{"feature": "caste", "op": ">=", "value": 1}]}, headers=analyst).status_code == 400
