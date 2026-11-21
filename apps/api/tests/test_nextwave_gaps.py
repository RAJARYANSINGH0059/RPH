"""Next-wave acceptance gaps: reversal handling (gross vs net), evidence-request responses with a preserved remainder, the
proof-carrying investigation package, graph-only baseline comparison in the blind challenge, adversary alternatives on cross-case links."""
import hashlib
import io
import json
import zipfile

import pytest


@pytest.fixture(scope="module")
def commingled(client, analyst):
    r = client.post("/api/synthetic/generate", json={"scenario_type": "commingled_funds", "difficulty": "messy", "size": "small", "seed": 4404}, headers=analyst)
    assert r.status_code == 201
    cid = r.json()["case"]["id"]
    assert client.post(f"/api/crosscase/cases/{cid}/members", json={"email": "supervisor@demo.local", "role_in_case": "supervisor"}, headers=analyst).status_code == 201
    return cid


def test_reversal_is_reported_gross_vs_net_not_netted(client, analyst, commingled):
    bf = client.get(f"/api/cases/{commingled}/bounded-flow", headers=analyst).json()
    assert bf["attribution_status"] != "INFEASIBLE", bf.get("inconsistencies")
    assert bf["reversals"], "the planted reversal pair must be detected from the rows"
    rv = bf["reversals"][0]
    assert rv["amount_minor"] == 7_000_00 and rv["debit_transaction_id"] != rv["credit_transaction_id"] and "not netted" in rv["handling"]
    gn = bf["gross_net"]
    assert gn["gross_onward_minor"] == sum(h["observed_transfer_minor"] for h in bf["hops"]) and gn["net_onward_minor"] == gn["gross_onward_minor"] - gn["reversed_onward_minor"]
    assert gn["reversals_detected"] >= 1 and "gross" in gn["definitions"]
    origin = bf["origin"]["amount_minor"]
    for h in bf["hops"]:
        assert 0 <= h["minimum_attributable_minor"] <= h["maximum_attributable_minor"] <= min(h["observed_transfer_minor"], origin)
    assert any("never netted silently" in lim for lim in bf["limitations"])
    txs = client.get(f"/api/cases/{commingled}/transactions", headers=analyst).json()
    assert not any(t["duplicate_of"] for t in txs if t["id"] in {rv["debit_transaction_id"], rv["credit_transaction_id"]})


def test_request_response_preserves_unresolved_remainder(client, analyst, supervisor, commingled):
    base = f"/api/cases/{commingled}/requests"
    iv = client.get(f"/api/cases/{commingled}/ivoi", headers=analyst).json()
    top = iv["ranked"][0]
    rq = client.post(base, json={"title": top["draft"]["title"], "catalogue_key": top["catalogue_key"], "target_entity": top["target_entity"], "organisation_type": top["organisation_type"]}, headers=analyst).json()
    rid = rq["id"]
    st = lambda body, h: client.post(f"{base}/{rid}/status", json=body, headers=h)  # noqa: E731
    files = client.get(f"/api/cases/{commingled}/files", headers=analyst).json()
    assert files
    # a response cannot be attached to a draft: nothing was sent
    r = client.post(f"{base}/{rid}/response", json={"source_file_id": files[0]["id"], "remaining": "x"}, headers=analyst)
    assert r.status_code == 400 and "cannot move" in r.json()["detail"]
    assert st({"status": "under_review"}, analyst).status_code == 200
    assert st({"status": "authorised", "legal_authority": "Section X (to be validated)", "requesting_officer": "SI Demo"}, supervisor).status_code == 200
    assert st({"status": "sent_manual", "actual_dispatch_details": "hand-delivered 22-11-2026 ref D/2"}, supervisor).status_code == 200
    # file from another case is refused
    other = client.post("/api/synthetic/generate", json={"scenario_type": "benign_lookalike", "difficulty": "clean", "size": "small", "seed": 4405}, headers=analyst).json()["case"]["id"]
    foreign = client.get(f"/api/cases/{other}/files", headers=analyst).json()[0]["id"]
    assert client.post(f"{base}/{rid}/response", json={"source_file_id": foreign}, headers=analyst).status_code == 404
    # partial response keeps the remainder visible everywhere
    r = client.post(f"{base}/{rid}/response", json={"source_file_id": files[0]["id"], "covers": ["first statement period"], "remaining": "second period and channel/session log still outstanding"}, headers=analyst)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "partial_response" and body["unresolved_remainder"].startswith("second period")
    assert body["responses"][0]["sha256"] == files[0]["sha256"] and body["responses"][0]["covers"] == ["first statement period"]
    assert body["status_history"][-1]["response"]["source_file_id"] == files[0]["id"]
    dm = client.get(f"/api/cases/{commingled}/dependencies", headers=analyst).json()
    assert any(p["remaining"] and p["remaining"].startswith("second period") for p in dm["partial"])
    req = next(x for x in dm["requirements"] if x["request_id"] == rid)
    assert req["status"] == "partial_response" and req["responses"] and req["unresolved_remainder"]
    # full response closes the remainder; history keeps both responses
    r = client.post(f"{base}/{rid}/response", json={"source_file_id": files[-1]["id"], "covers": ["second period"]}, headers=analyst).json()
    assert r["status"] == "received" and r["unresolved_remainder"] is None and len(r["responses"]) == 2
    mine = client.get("/api/audit/mine", headers=analyst).json()
    assert any(e["action"] == "evidence_request.response_attached" for e in (mine["events"] if isinstance(mine, dict) else mine))


def test_investigation_package_is_hashed_and_contains_no_sealed_truth(client, analyst, commingled):
    r = client.get(f"/api/cases/{commingled}/package.zip", headers=analyst)
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(z.namelist())
    for required in ("manifest.json", "report.json", "proof/path_0.json", "analysis/bounded_flow.json", "analysis/coverage.json", "analysis/lifecycle.json", "analysis/dependencies.json",
                     "analysis/adversary.json", "reasoning/hypotheses.json", "evidence_requests/requests.json", "reasoning/role_reviews.json", "audit/audit_history.json", "LIMITATIONS.md"):
        assert required in names, required
    manifest = json.loads(z.read("manifest.json"))
    assert manifest["package_sha256"] == r.headers["x-package-sha256"]
    for e in manifest["entries"]:
        assert hashlib.sha256(z.read(e["path"])).hexdigest() == e["sha256"]
    joined = "\n".join(f"{e['path']}:{e['sha256']}" for e in manifest["entries"])
    assert hashlib.sha256(joined.encode()).hexdigest() == manifest["package_sha256"]
    blob = b"".join(z.read(n) for n in names)
    for forbidden in (b'"sealed_truth"', b'"false_edges"', b'"mule_accounts"', b'"simulated_allocation"'):
        assert forbidden not in blob
    assert "sealed ground truth" in manifest["excluded"][0] and manifest["case"]["data_status"] == "SYNTHETIC DATA"
    bfj = json.loads(z.read("analysis/bounded_flow.json"))
    assert "assumptions" in bfj and "limitations" in bfj
    audit_rows = json.loads(z.read("audit/audit_history.json"))
    assert any(a["action"] == "evidence_request.response_attached" for a in audit_rows)


def test_challenge_reveal_includes_graph_only_baseline(client, analyst, commingled):
    assert client.get(f"/api/synthetic/cases/{commingled}/challenge/reveal", headers=analyst).status_code in {403, 409}
    paths = client.get(f"/api/cases/{commingled}/paths", headers=analyst).json()["paths"]
    guess = sorted({p["accounts"][1] for p in paths if len(p["accounts"]) > 1})
    assert client.post(f"/api/synthetic/cases/{commingled}/challenge/submit", json={"mule_pattern_accounts": guess, "common_operator_domains": []}, headers=analyst).status_code == 201
    rev = client.get(f"/api/synthetic/cases/{commingled}/challenge/reveal", headers=analyst).json()
    cmp_ = rev["baseline_comparison"]
    assert "unsafeguarded" in cmp_["baseline_definition"]
    b, s = cmp_["graph_only_baseline"], cmp_["ps05x"]
    assert b["flagged_accounts"] >= 1 and b["mule_recall"] is not None
    assert s["common_operator_pairs_asserted"] == 0 and s["innocent_or_victim_accounts_flagged"] <= b["innocent_or_victim_accounts_flagged"] + 1
    assert "SYNTHETIC" in cmp_["label"]


def test_crosscase_shared_ip_links_carry_alternatives(client, analyst):
    a = client.post("/api/synthetic/generate", json={"scenario_type": "desert_mirage", "difficulty": "messy", "size": "small", "seed": 4406}, headers=analyst).json()["case"]["id"]
    b = client.post("/api/synthetic/generate", json={"scenario_type": "desert_mirage", "difficulty": "messy", "size": "small", "seed": 4406}, headers=analyst).json()["case"]["id"]
    res = client.post("/api/crosscase/correlate", json={"case_ids": [a, b]}, headers=analyst)
    assert res.status_code == 200
    infra = [l for l in res.json()["links"] if l.get("kind") == "shared_infrastructure"] or res.json().get("infrastructure", [])
    if not infra:
        pytest.skip("no shared IP between the two generated cases")
    for l in infra:
        assert l["challenge_state"] in {"candidate", "corroborated", "stale"}
        assert l["alternatives"] and all({"hypothesis", "why_relevant", "discriminating_evidence"} <= set(x) for x in l["alternatives"])
        assert any("hosting" in x["hypothesis"].lower() or "cdn" in x["hypothesis"].lower() for x in l["alternatives"])
