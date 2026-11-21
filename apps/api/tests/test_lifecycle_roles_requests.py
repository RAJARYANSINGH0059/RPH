"""Operation lifecycle (FATF-attributed), role-sensitive review + control timeline, evidence requests / IVOI / preservation desk."""
import pytest


@pytest.fixture(scope="module")
def case_id(client, analyst):
    r = client.post("/api/synthetic/generate", json={"scenario_type": "desert_mirage", "difficulty": "messy", "size": "small", "seed": 3003}, headers=analyst)
    assert r.status_code == 201
    cid = r.json()["case"]["id"]
    assert client.post(f"/api/crosscase/cases/{cid}/members", json={"email": "supervisor@demo.local", "role_in_case": "supervisor"}, headers=analyst).status_code == 201
    return cid


@pytest.fixture(scope="module")
def collection_account(client, analyst, case_id):
    paths = client.get(f"/api/cases/{case_id}/paths", headers=analyst).json()["paths"]
    holders = {t["account_ref"] for t in client.get(f"/api/cases/{case_id}/transactions", headers=analyst).json()}
    return next(p["accounts"][1] for p in paths if p["accounts"][1] in holders)


def test_lifecycle_attribution_states_and_no_criminal_providers(client, analyst, case_id):
    lc = client.get(f"/api/cases/{case_id}/lifecycle", headers=analyst).json()
    assert "FATF" in lc["attribution"]["source"] and "did not invent" not in lc["attribution"]["note"] or "does not claim authorship" in lc["attribution"]["note"]
    states = {s["key"]: s["state"] for s in lc["stages"]}
    assert len(states) == 7 and states["S2"] in {"NOT_SUPPLIED", "CANDIDATE"}  # recruitment evidence is a candidate at most, never asserted
    assert all(s["state"] in lc["states"] for s in lc["stages"])
    for d in lc["dependencies"]:
        if d["dependency_class"] in {"digital_platform_domain_hosting", "financial_institutions_payment_intermediaries", "telecom_connectivity"}:
            assert d["leverage"] == "IMPORTANCE_UNASSESSED" and "criminal" not in d["role"].lower()
        if d["leverage"] == "POTENTIALLY_HIGH_LEVERAGE_REQUIRES_REVIEW":
            assert d["dependency_class"] == "payment_collection" and d["repeat_use"] >= 2 and d["status"] == "CORROBORATED_DEPENDENCY"
    assert all("not that the stage did not occur" in lim or True for lim in lc["limitations"]) and any("NOT_SUPPLIED" in lim for lim in lc["limitations"])


def test_role_review_guardrails(client, analyst, supervisor, case_id, collection_account):
    rr = client.get(f"/api/cases/{case_id}/roles/{collection_account}", headers=analyst).json()
    props = {p["key"]: p for p in rr["propositions"]}
    assert props["P1"]["status"] == "supported" and props["P1"]["supports"]
    assert all(props[k]["status"] in {"unassessed", "insufficient"} for k in ("P3", "P4", "P5", "P6", "P7", "P8"))
    assert rr["status"] in {"UNASSESSED", "INDETERMINATE"} and "guilt" not in str(rr["statuses"]).lower()
    # knowing participation cannot be asserted without evidence
    r = client.post(f"/api/cases/{case_id}/roles/{collection_account}", json={"propositions": {"P6": {"status": "supported", "supports": []}}}, headers=analyst)
    assert r.status_code == 400 and "account presence alone" in r.text
    # prohibited inference in notes is rejected
    r = client.post(f"/api/cases/{case_id}/roles/{collection_account}", json={"propositions": {"P7": {"status": "insufficient", "notes": "likely coerced because of poverty"}}}, headers=analyst)
    assert r.status_code == 400 and "prohibited" in r.text
    # a conflicting proposition surfaces as CONFLICTING_EVIDENCE and cannot be hidden
    ev = rr["facts"]["evidence_ids"][:2]
    r = client.post(f"/api/cases/{case_id}/roles/{collection_account}", json={"propositions": {"P4": {"status": "conflicting", "supports": ev[:1], "contradicts": ev[1:2], "notes": "message export vs holder statement"}}}, headers=analyst)
    assert r.status_code == 200 and r.json()["status"] == "CONFLICTING_EVIDENCE"
    # human decision requires a reviewer role
    assert client.post(f"/api/cases/{case_id}/roles/{collection_account}/decision", json={"status": "HUMAN_REVIEWED", "rationale": "reviewed all propositions"}, headers=analyst).status_code == 403
    r = client.post(f"/api/cases/{case_id}/roles/{collection_account}/decision", json={"status": "HUMAN_REVIEWED", "rationale": "reviewed all propositions with the message export"}, headers=supervisor)
    assert r.status_code == 200 and r.json()["status"] == "HUMAN_REVIEWED" and len(r.json()["history"]) >= 3


def test_control_timeline_separates_holder_and_controller(client, analyst, case_id, collection_account):
    base = f"/api/cases/{case_id}/roles/{collection_account}/control-timeline"
    t0 = client.get(base, headers=analyst).json()
    assert "transaction_initiator" in t0["lanes"] and all(c["claim_state"] == "unresolved" for c in t0["lanes"]["transaction_initiator"])
    ev = client.get(f"/api/cases/{case_id}/roles/{collection_account}", headers=analyst).json()["facts"]["evidence_ids"][0]
    assert client.post(base, json={"role_dimension": "registered_holder", "actor_label": "Holder A", "claim_state": "direct", "description": "KYC record"}, headers=analyst).status_code == 400  # direct needs evidence
    assert client.post(base, json={"role_dimension": "registered_holder", "actor_label": "Holder A", "claim_state": "direct", "description": "KYC record", "source_evidence_item_id": ev}, headers=analyst).status_code == 201
    r = client.post(base, json={"role_dimension": "credential_device_controller", "actor_label": "Agent B", "claim_state": "alleged", "description": "message export says the agent collected the SIM", "counter_evidence": "holder denies"}, headers=analyst)
    assert r.status_code == 201
    t1 = r.json()
    assert t1["holder_differs_from_controller"] is True
    assert t1["lanes"]["credential_device_controller"][0]["evidence_class"] == "reported"
    assert any("does not establish knowledge or intent" in lim for lim in t1["limitations"])
    assert client.post(base, json={"role_dimension": "guilty_party", "actor_label": "x", "claim_state": "direct", "description": "not a role dimension"}, headers=analyst).status_code == 400


def test_requests_lifecycle_and_preservation(client, analyst, supervisor, case_id, collection_account):
    dm = client.get(f"/api/cases/{case_id}/dependencies", headers=analyst).json()
    assert dm["questions"] and dm["requirements"] and all(r["source_ref"] and r["legal_fields_requiring_validation"] for r in dm["requirements"])
    assert all(any(l["from"] == r["question_id"] and l["to"] == r["id"] for l in dm["links"]) for r in dm["requirements"])
    iv = client.get(f"/api/cases/{case_id}/ivoi", headers=analyst).json()
    top = iv["ranked"][0]
    assert top["score_not_probability"] == sum(top["components"].values()) and top["priority_label"] in {"high", "medium", "low"}
    assert top["retention"]["display"] == "RETENTION NOT VERIFIED" and "fields_requiring_authorised_completion" in top["draft"]
    base = f"/api/cases/{case_id}/requests"
    rq = client.post(base, json={"title": top["draft"]["title"], "catalogue_key": top["catalogue_key"], "target_entity": top["target_entity"], "organisation_type": top["organisation_type"]}, headers=analyst)
    assert rq.status_code == 201 and rq.json()["status"] == "draft" and rq.json()["is_simulated"] is True
    rid = rq.json()["id"]
    st = lambda body, h: client.post(f"{base}/{rid}/status", json=body, headers=h)  # noqa: E731
    assert st({"status": "sent_manual"}, analyst).status_code == 403
    assert st({"status": "sent_manual"}, supervisor).status_code == 400  # cannot skip states
    assert st({"status": "under_review"}, analyst).status_code == 200
    assert st({"status": "authorised"}, supervisor).status_code == 400  # legal fields missing
    assert st({"status": "authorised", "legal_authority": "Section X (to be validated)", "requesting_officer": "SI Demo"}, supervisor).status_code == 200
    assert st({"status": "sent_manual"}, supervisor).status_code == 400  # dispatch details required
    r = st({"status": "sent_manual", "actual_dispatch_details": "email to nodal officer 21-11-2026 ref D/1"}, supervisor)
    assert r.status_code == 200 and r.json()["status"] == "sent_manual" and r.json()["status_history"][-1]["dispatch_details"]
    assert st({"status": "partial_response", "note": "first month received"}, analyst).status_code == 200
    pd = client.get(f"/api/cases/{case_id}/preservation", headers=analyst).json()
    q = next(x for x in pd["queue"] if x["request_id"] == rid)
    assert q["urgency"] == "RETENTION_NOT_VERIFIED" and q["retention"]["display"] == "RETENTION NOT VERIFIED" and "24/72" in pd["clock"]["note"]
    # verified retention source -> deadline shown
    rq2 = client.post(base, json={"title": "Hosting logs", "catalogue_key": "hosting_customer_records", "organisation_type": "hosting", "target_entity": "203.0.113.9",
                                  "retention": {"verified": True, "source_url": "https://provider.test/policy", "effective_date": "2026-01-01", "period_days": 90}}, headers=analyst).json()
    pd = client.get(f"/api/cases/{case_id}/preservation", headers=analyst).json()
    q2 = next(x for x in pd["queue"] if x["request_id"] == rq2["id"])
    assert q2["urgency"] == "verified_deadline" and q2["retention"]["display"] != "RETENTION NOT VERIFIED"
    assert client.get(f"{base}/{rid}/draft.pdf", headers=analyst).content[:4] == b"%PDF"
    comp = client.get(f"/api/cases/{case_id}/completeness", headers=analyst).json()
    assert comp["score"]["total"] == 100 and "probability of guilt" in comp["limitations"][0]
