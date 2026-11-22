"""Canonical counts must agree everywhere.

The defect this pins: the overview counted every relationship row, the report tabled a filtered subset, and the results
page read a field the report never emitted, so one case reported 85, 80 and 0 for the same questions. A number on
screen is a claim about evidence; the same question must get the same answer on every surface.
"""
import pytest


@pytest.fixture(scope="module")
def case_id(client, analyst):
    r = client.post("/api/synthetic/generate", json={"scenario_type": "desert_mirage", "difficulty": "messy", "size": "small", "seed": 6201}, headers=analyst)
    assert r.status_code == 201
    return r.json()["case"]["id"]


def test_counts_endpoint_defines_what_it_counts(client, analyst, case_id):
    c = client.get(f"/api/cases/{case_id}/counts", headers=analyst).json()
    assert c["version"] and c["case_id"] == case_id
    for key in ("files.total", "transactions.total", "relationships.total", "relationships.in_graph",
                "relationships.in_report_tables", "relationships.awaiting_review", "paths.total", "paths.unresolved"):
        assert key in c["definitions"], f"{key} is counted but not defined"
    assert c["relationships"]["total"] >= c["relationships"]["in_report_tables"], "a presentation table cannot exceed the total"
    assert c["relationships"]["total"] >= c["relationships"]["in_graph"]
    assert sum(c["relationships"]["by_evidence_level"].values()) == c["relationships"]["total"]
    assert sum(c["relationships"]["by_review_status"].values()) == c["relationships"]["total"]
    assert c["transactions"]["excluding_duplicates"] + c["transactions"]["duplicates"] == c["transactions"]["total"]
    assert c["paths"]["resolved"] + c["paths"]["unresolved"] == c["paths"]["total"]


def test_overview_matches_the_canonical_counts(client, analyst, case_id):
    c = client.get(f"/api/cases/{case_id}/counts", headers=analyst).json()
    ov = client.get(f"/api/cases/{case_id}", headers=analyst).json()
    assert ov["relationships_count"] == c["relationships"]["total"]
    assert ov["transactions_count"] == c["transactions"]["total"]
    assert ov["files_count"] == c["files"]["total"]
    assert ov["entities_count"] == c["entities"]["total"]
    assert ov["indicators_count"] == c["indicators"]["total"]
    assert ov["findings_awaiting_review"] == c["relationships"]["awaiting_review"]


def test_graph_paths_and_report_agree_with_the_canonical_counts(client, analyst, case_id):
    c = client.get(f"/api/cases/{case_id}/counts", headers=analyst).json()
    paths = client.get(f"/api/cases/{case_id}/paths", headers=analyst).json()["paths"]
    assert len(paths) == c["paths"]["total"], "the paths endpoint and the canonical count disagree"
    assert sum(1 for p in paths if p["status"] == "unresolved") == c["paths"]["unresolved"]

    g = client.get(f"/api/cases/{case_id}/graph", headers=analyst).json()
    assert len(g["edges"]) == c["relationships"]["in_graph"], "the unfiltered graph and the canonical count disagree"

    rep = client.get(f"/api/cases/{case_id}/report.json", headers=analyst).json()
    assert rep["counts"]["relationships"]["total"] == c["relationships"]["total"]
    assert rep["counts"]["paths"]["total"] == c["paths"]["total"]
    assert len(rep["fund_paths"]) == c["paths"]["total"], "the report's path table and the canonical count disagree"
    assert len(rep["relationships"]) == c["relationships"]["in_report_tables"], "the report's relationship table must equal the documented subset"


def test_same_seed_produces_the_same_counts(client, analyst):
    a = client.post("/api/synthetic/generate", json={"scenario_type": "desert_mirage", "difficulty": "messy", "size": "small", "seed": 6202}, headers=analyst).json()["case"]["id"]
    b = client.post("/api/synthetic/generate", json={"scenario_type": "desert_mirage", "difficulty": "messy", "size": "small", "seed": 6202}, headers=analyst).json()["case"]["id"]
    ca = client.get(f"/api/cases/{a}/counts", headers=analyst).json()
    cb = client.get(f"/api/cases/{b}/counts", headers=analyst).json()
    for section in ("files", "transactions", "entities", "relationships", "indicators", "paths"):
        assert ca[section] == cb[section], f"{section} differs between two generations of the same seed"


def test_counts_include_candidates_rather_than_hiding_them(client, analyst, case_id):
    """A tidy total must not be achieved by dropping candidate or stale relationships."""
    c = client.get(f"/api/cases/{case_id}/counts", headers=analyst).json()
    levels = c["relationships"]["by_evidence_level"]
    assert set(levels) & {"candidate", "stale", "derived", "directly_observed", "corroborated"}
    assert c["relationships"]["total"] == sum(levels.values())
    assert "labelled, never dropped" in c["note"]
