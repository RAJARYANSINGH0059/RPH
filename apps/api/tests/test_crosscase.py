"""Cross-case correlation: true bridges found, decoys rejected, shared CDN candidate-only, stale respected, IDOR, revocation, reproducibility."""
import json

import pytest

from app.synthetic.artifacts import build_bundle
from app.synthetic.generator import Generator


def _gen(client, headers, **kw):
    body = {"scenario_type": "phishing_to_mule", "difficulty": "messy", "size": "small", "seed": 21}
    body.update(kw)
    r = client.post("/api/synthetic/generate", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["case"]["id"]


@pytest.fixture(scope="module")
def pair(client, analyst):
    """Case A: synthetic seed 21. Case B: a second complaint that received the same mule statement (true bridge).
    Case C: decoy, seed 22 (same name pool, different identifiers)."""
    a = _gen(client, analyst, seed=21)
    files, truth, _ = build_bundle(Generator("phishing_to_mule", "messy", "small", 21))
    mule_csv = next(n for n in files if "mule_l1" in n)
    b = client.post("/api/cases", json={"title": "Second complaint (related)"}, headers=analyst).json()["id"]
    # the mule statement plus a technical report naming a DIFFERENT domain on the SAME shared IP (decoy for shared hosting)
    shared_ip = truth.domains[0]["ip"]
    tech = json.dumps({"observations": [
        {"type": "dns", "domain": "unrelated-bakery-ajmer7.test", "ip": shared_ip, "ttl": 300, "observed_at": truth.params["t0"], "source": "test_fixture"},
        {"type": "cdn", "domain": "unrelated-bakery-ajmer7.test", "ip": shared_ip, "provider": "SampleCloud CDN", "asn": 64500, "observed_at": truth.params["t0"], "multi_tenant": True, "source": "test_fixture"},
        {"type": "dns", "domain": "old-news-kota3.test", "ip": shared_ip, "ttl": 300, "observed_at": "2024-01-01T00:00:00Z", "source": "test_fixture_stale"},
    ]}).encode()
    r = client.post(f"/api/cases/{b}/upload", files=[("files", (mule_csv, files[mule_csv], "text/csv")), ("files", ("tech.json", tech, "application/json"))], headers=analyst)
    assert r.status_code == 200, r.text
    c = _gen(client, analyst, seed=22)
    return a, b, c, truth


def test_true_bridge_found(client, analyst, pair):
    a, b, c, truth = pair
    r = client.post("/api/crosscase/correlate", json={"case_ids": [a, b]}, headers=analyst)
    assert r.status_code == 200, r.text
    res = r.json()
    classes = {l["match_class"] for l in res["links"]}
    assert "corroborated" in classes or "derived" in classes
    # the mule account (statement holder) is an exact/corroborated identifier match and a transaction bridge exists
    mule_accts = {a_.acct_no for a_ in truth.accounts if a_.role == "mule_l1"}
    ident = [l for l in res["links"] if l["kind"] == "identifier" and l.get("value") in mule_accts]
    assert ident and ident[0]["match_class"] in {"corroborated", "exact"}
    assert all(ev["sha256"] and ev["locator"] for lst in ident[0]["evidence"].values() for ev in lst)
    bridges = [l for l in res["links"] if l["kind"] == "transaction_bridge"]
    assert bridges and all(b_["time_consistent"] is not False for b_ in bridges[:3])
    assert res["summary"] and "probab" not in json.dumps(res["notes"]).lower().replace("not probabilities", "")


def test_decoy_not_asserted(client, analyst, pair):
    a, b, c, truth = pair
    res = client.post("/api/crosscase/correlate", json={"case_ids": [a, c]}, headers=analyst).json()
    strong = [l for l in res["links"] if l["kind"] == "identifier" and l["entity_type"] in {"account", "vpa", "phone"}]
    assert strong == [], strong  # different seeds share no identifiers
    assert not [l for l in res["links"] if l["kind"] == "transaction_bridge"]
    # similar names between the decoy and A may exist: they must be in `rejected`, never a link
    for rj in res["rejected"]:
        assert rj["kind"] == "similar_name_not_identity"


def test_shared_ip_candidate_only_and_stale(client, analyst, pair):
    a, b, c, truth = pair
    res = client.post("/api/crosscase/correlate", json={"case_ids": [a, b]}, headers=analyst).json()
    infra = [l for l in res["links"] if l["kind"] == "shared_infrastructure"]
    assert infra, "expected a shared-IP observation across the two cases"
    for x in infra:
        assert x["match_class"] in {"candidate", "stale", "exact"}
        if not x["same_domain_in_both"]:
            assert x["match_class"] in {"candidate", "stale"}
            assert x["counter_evidence"]
        assert "shared_ip_is_not_proof_of_common_control" in x["limitations"]
    assert "COMMON_OPERATOR" not in json.dumps(res)


def test_idor_non_member_cannot_correlate_or_discover(client, analyst, other_analyst, pair):
    a, b, c, _ = pair
    mine = client.post("/api/cases", json={"title": "other's case"}, headers=other_analyst).json()["id"]
    r = client.post("/api/crosscase/correlate", json={"case_ids": [mine, a]}, headers=other_analyst)
    assert r.status_code == 404
    r = client.get(f"/api/crosscase/cases/{mine}/related", headers=other_analyst)
    assert r.status_code == 200 and r.json()["related"] == []
    assert client.get(f"/api/crosscase/cases/{a}/related", headers=other_analyst).status_code == 404


def test_membership_grant_and_revoke(client, analyst, other_analyst, pair):
    a, b, c, _ = pair
    r = client.post(f"/api/crosscase/cases/{a}/members", json={"email": "other@demo.local", "role_in_case": "analyst"}, headers=analyst)
    assert r.status_code == 201
    r = client.post(f"/api/crosscase/cases/{b}/members", json={"email": "other@demo.local"}, headers=analyst)
    assert r.status_code == 201
    assert client.post("/api/crosscase/correlate", json={"case_ids": [a, b]}, headers=other_analyst).status_code == 200
    other_id = client.get("/api/auth/me", headers=other_analyst).json()["id"]
    assert client.delete(f"/api/crosscase/cases/{b}/members/{other_id}", headers=analyst).status_code == 200
    assert client.post("/api/crosscase/correlate", json={"case_ids": [a, b]}, headers=other_analyst).status_code == 404
    assert client.get(f"/api/cases/{b}", headers=other_analyst).status_code == 404
    # cannot manage membership of a case you merely belong to
    assert client.post(f"/api/crosscase/cases/{a}/members", json={"email": "analyst@demo.local"}, headers=other_analyst).status_code == 403


def test_reproducible(client, analyst, pair):
    a, b, c, _ = pair
    r1 = client.post("/api/crosscase/correlate", json={"case_ids": [a, b]}, headers=analyst).json()
    r2 = client.post("/api/crosscase/correlate", json={"case_ids": [b, a]}, headers=analyst).json()
    assert r1["fingerprint"] == r2["fingerprint"]
    assert r1["algorithm_version"] == r2["algorithm_version"]


def test_related_cases_panel(client, analyst, pair):
    a, b, c, _ = pair
    rel = client.get(f"/api/crosscase/cases/{a}/related", headers=analyst).json()["related"]
    ids = [x["case_id"] for x in rel]
    assert b in ids
    assert c not in ids or next(x for x in rel if x["case_id"] == c)["strong_identity_matches"] == 0
