"""Explainable account typologies.

Each typology must say what it observed, in which transactions, against which threshold, what would explain the same
records innocently, and what it cannot see. These tests pin that, and pin the two things the system must never do:
call a person a mule, or infer dormancy from an absence of records.
"""
import pytest

from app.services.typologies import THRESHOLDS, TYPOLOGY_VERSION

TYPES = {"rapid_in_out", "many_small_credits", "round_figure_layering", "dormant_reactivation",
         "repeated_counterparties", "split_and_merge", "pass_through"}


@pytest.fixture(scope="module")
def case_id(client, analyst):
    r = client.post("/api/synthetic/generate", json={"scenario_type": "desert_mirage", "difficulty": "messy", "size": "small", "seed": 7501}, headers=analyst)
    assert r.status_code == 201
    return r.json()["case"]["id"]


@pytest.fixture(scope="module")
def collection_account(client, analyst, case_id):
    paths = client.get(f"/api/cases/{case_id}/paths", headers=analyst).json()["paths"]
    holders = {t["account_ref"] for t in client.get(f"/api/cases/{case_id}/transactions", headers=analyst).json()}
    return next(p["accounts"][1] for p in paths if len(p["accounts"]) > 1 and p["accounts"][1] in holders)


def test_every_typology_is_reported_whether_or_not_it_triggered(client, analyst, case_id, collection_account):
    """A typology that did not trigger still has to appear: silence about a check is not an answer."""
    p = client.get(f"/api/cases/{case_id}/typologies/{collection_account}", headers=analyst).json()
    got = {t["type"] for t in p["typologies"]}
    assert got == TYPES, f"missing: {TYPES - got}"
    for t in p["typologies"]:
        assert t["status"] in {"observed", "not_observed", "not_enough_history", "not_enough_evidence"}
        assert t["thresholds"], f"{t['type']} does not carry the thresholds it was judged against"
        assert t["explanation"], f"{t['type']} has no explanation"


def test_a_triggered_typology_names_its_transactions_and_its_innocent_alternatives(client, analyst, case_id, collection_account):
    p = client.get(f"/api/cases/{case_id}/typologies/{collection_account}", headers=analyst).json()
    fired = [t for t in p["typologies"] if t["triggered"]]
    assert fired, "the collection account in this scenario should show at least one pattern"
    for t in fired:
        assert t["observed_values"], f"{t['type']} triggered without observed values"
        assert t["alternatives"], f"{t['type']} triggered without offering an ordinary explanation"
        assert t["limitations"], f"{t['type']} triggered without stating what it cannot see"
    assert any(t["supporting_transactions"] for t in fired), "no triggered pattern named a transaction"


def test_supporting_transactions_are_real_rows_in_this_case(client, analyst, case_id, collection_account):
    """An explanation that points at a transaction must point at one that exists."""
    p = client.get(f"/api/cases/{case_id}/typologies/{collection_account}", headers=analyst).json()
    ids = {t["id"] for t in client.get(f"/api/cases/{case_id}/transactions", headers=analyst).json()}
    for t in p["typologies"]:
        for tx in t["supporting_transactions"]:
            assert tx in ids, f"{t['type']} cites a transaction that is not in this case"


def test_no_guilt_language_and_no_person_is_labelled(client, analyst, case_id):
    body = client.get(f"/api/cases/{case_id}/typologies", headers=analyst).text.lower()
    # Assertive phrases only. The word "criminal" is allowed where it appears inside a disclaimer saying the output
    # is not one, which is the opposite of judgement language and is asserted separately below.
    for phrase in ("is a mule", "is a criminal", "is guilty", "guilty of", "known offender", "is a fraudster",
                   "probability of fraud", "risk of guilt", "confirmed mule"):
        assert phrase not in body, f"the output contains judgement language: {phrase}"
    assert "probability of criminal involvement" in body, "the output must state that no score expresses that"
    data = client.get(f"/api/cases/{case_id}/typologies", headers=analyst).json()
    for p in data["profiles"]:
        assert p["label"] in {"possible_mule_pattern_requires_review", "single_pattern_observed_requires_review", "no_pattern_observed"}
        assert any("not findings about any person" in lim for lim in p["limitations"])


def test_dormancy_is_never_inferred_from_a_short_statement_period(client, analyst, case_id, collection_account):
    """The rule the specification is most explicit about: an absence of records is not dormancy."""
    p = client.get(f"/api/cases/{case_id}/typologies/{collection_account}", headers=analyst).json()
    d = next(t for t in p["typologies"] if t["type"] == "dormant_reactivation")
    if d["status"] == "not_enough_history":
        assert not d["triggered"]
        assert any("absence of records" in lim or "earlier months" in lim or "shorter than" in str(d["explanation"])
                   for lim in d["limitations"] + [d["explanation"]])
    else:
        assert d["observed_values"].get("period_examined_days", 0) >= THRESHOLDS["dormant_reactivation"]["min_history_days"], \
            "dormancy was assessed over a period shorter than the declared minimum"


def test_thresholds_are_published_and_versioned(client, analyst, case_id):
    data = client.get(f"/api/cases/{case_id}/typologies", headers=analyst).json()
    assert data["typology_version"] == TYPOLOGY_VERSION
    assert set(data["thresholds"]) == TYPES
    for name, cfg in data["thresholds"].items():
        assert cfg.get("why"), f"{name} does not say why it is a pattern worth looking at"


def test_case_view_orders_by_patterns_observed_not_by_suspicion(client, analyst, case_id):
    data = client.get(f"/api/cases/{case_id}/typologies", headers=analyst).json()
    counts = [p["patterns_observed"] for p in data["profiles"]]
    assert counts == sorted(counts, reverse=True)
    assert data["accounts_examined"] >= 1
    assert "not by suspicion" in data["note"]


def test_an_account_with_no_movement_is_reported_honestly(client, analyst, case_id):
    p = client.get(f"/api/cases/{case_id}/typologies/000000000000", headers=analyst).json()
    assert p["patterns_observed"] == 0 and p["label"] == "no_pattern_observed"
    assert not p["review_required"]


def test_the_account_identifier_is_masked_for_display(client, analyst, case_id, collection_account):
    p = client.get(f"/api/cases/{case_id}/typologies/{collection_account}", headers=analyst).json()
    masked = p["masked_account_ref"]
    assert masked.endswith(collection_account[-4:]) and "*" in masked
    assert masked != collection_account
