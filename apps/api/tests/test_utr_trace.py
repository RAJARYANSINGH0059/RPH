"""Starting a money trail from the victim's own transaction reference.

An investigator starts with one complaint carrying one UTR, not with a whole case. These tests pin that entry point,
and the two rules that make it trustworthy: an ambiguous reference is never resolved for the investigator, and the
trail stops where the records stop rather than guessing at the next hop.
"""
import pytest


@pytest.fixture(scope="module")
def case_id(client, analyst):
    r = client.post("/api/synthetic/generate", json={"scenario_type": "desert_mirage", "difficulty": "messy", "size": "small", "seed": 7601}, headers=analyst)
    assert r.status_code == 201
    return r.json()["case"]["id"]


@pytest.fixture(scope="module")
def a_victim_transfer(client, analyst, case_id):
    """A debit from an account that a reconstructed path starts at: the shape of a victim's own payment."""
    paths = client.get(f"/api/cases/{case_id}/paths", headers=analyst).json()["paths"]
    victims = {p["accounts"][0] for p in paths}
    txs = client.get(f"/api/cases/{case_id}/transactions", headers=analyst).json()
    tx = next((t for t in txs if t["account_ref"] in victims and t["direction"] == "debit" and t["external_reference"]), None)
    if tx is None:
        pytest.skip("no victim-side debit with a reference in this generated case")
    return tx


def test_search_finds_the_transaction_by_its_reference(client, analyst, case_id, a_victim_transfer):
    r = client.post(f"/api/cases/{case_id}/utr/search", json={"reference": a_victim_transfer["external_reference"]}, headers=analyst)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"exact_single", "ambiguous"}
    assert any(m["transaction_id"] == a_victim_transfer["id"] for m in body["exact_matches"])
    hit = next(m for m in body["exact_matches"] if m["transaction_id"] == a_victim_transfer["id"])
    assert hit["source_file"] and hit["source_file"]["sha256"], "a match must carry the file it came from"
    assert hit["source_locator"], "a match must carry its locator"


def test_search_tolerates_how_a_reference_is_written(client, analyst, case_id, a_victim_transfer):
    """Complaints quote references with spaces, slashes and mixed case."""
    ref = a_victim_transfer["external_reference"]
    messy = f" {ref[:4].lower()}-{ref[4:]} "
    body = client.post(f"/api/cases/{case_id}/utr/search", json={"reference": messy}, headers=analyst).json()
    assert any(m["transaction_id"] == a_victim_transfer["id"] for m in body["exact_matches"]), body["status"]


def test_an_unknown_reference_is_reported_as_not_found_with_what_would_establish_it(client, analyst, case_id):
    body = client.post(f"/api/cases/{case_id}/utr/search", json={"reference": "SYNNOSUCHREF999"}, headers=analyst).json()
    assert body["status"] == "not_found"
    assert not body["exact_matches"]
    assert "statement" in body["next_step"].lower(), body["next_step"]


def test_an_ambiguous_reference_is_never_resolved_automatically(client, analyst, case_id):
    """The rule that matters most here: where several rows carry the reference, the investigator chooses."""
    txs = client.get(f"/api/cases/{case_id}/transactions", headers=analyst).json()
    refs = {}
    for t in txs:
        if t["external_reference"]:
            refs.setdefault(t["external_reference"], []).append(t)
    duplicated = next((r for r, group in refs.items() if len(group) > 1), None)
    if duplicated is None:
        pytest.skip("this generated case has no reference appearing on more than one row")
    body = client.post(f"/api/cases/{case_id}/utr/search", json={"reference": duplicated}, headers=analyst).json()
    assert body["status"] == "ambiguous"
    assert len(body["exact_matches"]) > 1
    assert "will not choose for you" in body["next_step"]


def test_search_requires_something_to_search_on(client, analyst, case_id):
    assert client.post(f"/api/cases/{case_id}/utr/search", json={}, headers=analyst).status_code == 422


def test_trace_follows_the_money_and_carries_evidence_on_every_hop(client, analyst, case_id, a_victim_transfer):
    r = client.get(f"/api/cases/{case_id}/utr/trace/{a_victim_transfer['id']}", headers=analyst)
    assert r.status_code == 200
    body = r.json()
    assert body["root"]["transaction_id"] == a_victim_transfer["id"]
    assert body["hops"], "the victim's own transfer should at least appear as the first hop"
    assert body["hops"][0]["hop"] == 1
    for h in body["hops"]:
        assert h["amount_minor"] is not None and h["from_account"] and h["to_account"]
        assert h["transaction_id"] and h["evidence_item_id"], "a hop with no evidence reference is unauditable"
        assert "source_locator" in h
    refs = [h["transaction_id"] for h in body["hops"]]
    assert len(refs) == len(set(refs)), "a transaction must not be followed twice"


def test_the_trail_stops_where_the_records_stop_and_says_what_is_needed(client, analyst, case_id, a_victim_transfer):
    body = client.get(f"/api/cases/{case_id}/utr/trace/{a_victim_transfer['id']}", headers=analyst).json()
    assert body["unresolved"], "a case without every downstream statement must report unresolved ends"
    for u in body["unresolved"]:
        assert u["reason"] and u["needed"], "an unresolved end must say why and what would continue it"
    stopped = [u for u in body["unresolved"] if "no statement for this account" in u["reason"]]
    if stopped:
        assert all("statement of" in u["needed"] for u in stopped)


def test_trace_never_claims_the_whole_transfer_was_the_victims_money(client, analyst, case_id, a_victim_transfer):
    body = client.get(f"/api/cases/{case_id}/utr/trace/{a_victim_transfer['id']}", headers=analyst).json()
    joined = " ".join(body["limitations"]).lower()
    assert "does not establish that every rupee came from the victim" in joined
    assert "bounded fund provenance" in body["next"].lower()


def test_accounts_on_the_trail_are_masked_and_say_whether_a_statement_exists(client, analyst, case_id, a_victim_transfer):
    body = client.get(f"/api/cases/{case_id}/utr/trace/{a_victim_transfer['id']}", headers=analyst).json()
    assert body["accounts"]
    for a in body["accounts"]:
        assert "has_own_statement" in a
        if a["account_ref"] and len(a["account_ref"]) > 6:
            assert "*" in a["masked"] and a["masked"].endswith(a["account_ref"][-4:])


def test_trace_of_an_unknown_transaction_is_a_404(client, analyst, case_id):
    assert client.get(f"/api/cases/{case_id}/utr/trace/00000000-0000-0000-0000-00000000dead", headers=analyst).status_code == 404


def test_another_case_cannot_be_traced_through_this_one(client, analyst, supervisor, case_id, a_victim_transfer):
    """Case isolation holds on the new routes as it does everywhere else."""
    assert client.get(f"/api/cases/{case_id}/utr/trace/{a_victim_transfer['id']}", headers=supervisor).status_code == 404
    assert client.post(f"/api/cases/{case_id}/utr/search", json={"reference": "x"}, headers=supervisor).status_code == 404
