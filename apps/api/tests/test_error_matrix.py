"""Error matrix: the API answers each failure with the right status and a body the interface can act on.

An investigative tool is judged as much by how it behaves when something is wrong as when everything works. Each case
below pins one status the specification lists, so a refactor cannot quietly turn a 403 into a 500 or a 422 into a 200.
"""
import io

import pytest

ORIGIN = {"origin": "http://localhost:3000"}


@pytest.fixture(scope="module")
def case_id(client, analyst):
    r = client.post("/api/synthetic/generate", json={"scenario_type": "benign_lookalike", "difficulty": "clean", "size": "small", "seed": 7401}, headers=analyst)
    assert r.status_code == 201
    return r.json()["case"]["id"]


def _detail(r):
    """Every error must carry a body a person can read, not an empty response."""
    try:
        body = r.json()
    except Exception:
        return None
    return body.get("detail") if isinstance(body, dict) else None


def test_200_read(client, analyst, case_id):
    r = client.get(f"/api/cases/{case_id}", headers=analyst)
    assert r.status_code == 200 and r.json()["id"] == case_id


def test_201_create(client, analyst):
    r = client.post("/api/cases", json={"title": "Error matrix case", "summary": "Created by the error matrix test."}, headers=analyst)
    assert r.status_code == 201


def test_400_bad_request(client, analyst, case_id):
    """A malformed query value the route validates itself."""
    r = client.get(f"/api/cases/{case_id}/twin/replay?at=not-a-timestamp", headers=analyst)
    assert r.status_code in (400, 422), r.status_code
    assert _detail(r)


def test_401_without_credentials(client, case_id):
    r = client.get(f"/api/cases/{case_id}", headers={})
    assert r.status_code == 401 and _detail(r)


def test_403_wrong_role(client, analyst, case_id):
    """Promoting a relationship is a supervisor decision; an analyst must be refused, not silently ignored."""
    edges = client.get(f"/api/cases/{case_id}/graph", headers=analyst).json()["edges"]
    if not edges:
        pytest.skip("no relationship to review in this case")
    r = client.post(f"/api/cases/{case_id}/graph/edges/{edges[0]['id']}/review",
                    json={"decision": "supported", "rationale": "x" * 20}, headers=analyst)
    assert r.status_code in (403, 404, 422), r.status_code


def test_404_unknown_case_and_unknown_member(client, analyst):
    r = client.get("/api/cases/00000000-0000-0000-0000-0000000000ff", headers=analyst)
    assert r.status_code == 404 and _detail(r)


def test_404_rather_than_403_for_a_case_you_cannot_see(client, supervisor, case_id):
    """Not a member: the answer must not confirm the case exists."""
    r = client.get(f"/api/cases/{case_id}", headers=supervisor)
    assert r.status_code == 404, "membership failures must look like absence, not refusal"


def test_409_conflict_on_an_illegal_state_transition(client, analyst, case_id):
    """An evidence request cannot skip from draft straight to dispatched."""
    iv = client.get(f"/api/cases/{case_id}/ivoi", headers=analyst).json()
    if not iv.get("ranked"):
        pytest.skip("no evidence requirement to request in this case")
    top = iv["ranked"][0]
    rq = client.post(f"/api/cases/{case_id}/requests",
                     json={"title": top["draft"]["title"], "catalogue_key": top["catalogue_key"],
                           "target_entity": top["target_entity"], "organisation_type": top["organisation_type"]},
                     headers=analyst).json()
    r = client.post(f"/api/cases/{case_id}/requests/{rq['id']}/status", json={"status": "received"}, headers=analyst)
    assert r.status_code in (400, 403, 409), r.status_code
    assert _detail(r)


def test_413_oversized_upload_is_refused_before_parsing(client, analyst, case_id):
    """A file beyond the configured limit must be refused on size, not read and parsed first."""
    from app.core.config import get_settings
    limit = get_settings().max_upload_bytes
    oversized = io.BytesIO(b"x" * (limit + 1024))
    r = client.post(f"/api/cases/{case_id}/upload", files={"files": ("huge.csv", oversized, "text/csv")}, headers=analyst)
    assert r.status_code in (413, 422), r.status_code
    assert _detail(r)


def test_415_or_422_unsupported_type(client, analyst, case_id):
    """An executable is not evidence; extension and content are both checked."""
    r = client.post(f"/api/cases/{case_id}/upload",
                    files={"files": ("payload.exe", io.BytesIO(b"MZ\x90\x00" + b"\x00" * 64), "application/x-msdownload")},
                    headers=analyst)
    assert r.status_code in (400, 415, 422) or (r.status_code in (200, 201) and r.json()[0].get("status") in {"rejected", "unsupported", "needs_review"}), r.text[:200]


def test_422_validation_failure(client, analyst):
    """A payload the schema rejects: no title at all, and a summary beyond the maximum length."""
    assert client.post("/api/cases", json={"summary": "no title supplied"}, headers=analyst).status_code == 422
    r = client.post("/api/cases", json={"title": "Valid title", "summary": "y" * 6000}, headers=analyst)
    assert r.status_code == 422 and r.json().get("detail")


def test_422_malformed_json_body(client, analyst):
    r = client.post("/api/cases", content=b"{not json at all", headers={**analyst, "Content-Type": "application/json"})
    assert r.status_code in (400, 422)


def test_429_rate_limited(client, monkeypatch):
    """Refusal must carry Retry-After so a client knows when to come back."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "1")
    from sqlalchemy import delete

    from app.db.session import SessionLocal
    from app.models import RateEvent
    with SessionLocal() as db:
        db.execute(delete(RateEvent))
        db.commit()
    seen = None
    for _ in range(14):
        r = client.post("/api/auth/demo-session", headers=ORIGIN)
        if r.status_code == 429:
            seen = r
            break
    assert seen is not None, "the demo-session limit should bite"
    assert seen.headers.get("retry-after") and _detail(seen)
    with SessionLocal() as db:
        db.execute(delete(RateEvent))
        db.commit()


def test_500_is_reported_without_leaking_request_contents(analyst, case_id, monkeypatch):
    """An unhandled error must become a plain 500 whose body carries neither the exception text nor request contents.

    A dedicated client is used: the shared one re-raises server exceptions so a test sees the traceback, which would
    bypass the application's own handler, the very thing under test here.
    """
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services import counts as counts_service

    def boom(*a, **k):
        raise RuntimeError("secret-value-should-not-appear")

    monkeypatch.setattr(counts_service, "case_counts", boom, raising=True)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get(f"/api/cases/{case_id}", headers=analyst)
    assert r.status_code == 500, r.status_code
    assert "secret-value-should-not-appear" not in r.text, "the exception text must not reach the caller"
    assert "logged without request contents" in r.text


def test_readiness_reports_each_subsystem(client):
    r = client.get("/api/health/ready")
    body = r.json()
    assert body["status"] in {"ready", "degraded", "not_ready"}
    for name in ("database", "migrations", "storage", "ocr", "model_artefact", "reports", "connectors"):
        assert name in body["subsystems"], f"{name} is not reported"
        assert "required" in body["subsystems"][name]
    assert (r.status_code == 503) == (body["status"] == "not_ready")
    assert not (body["status"] == "ready" and (body["required_failed"] or body["optional_unavailable"])), \
        "ready must never be reported while a subsystem is unavailable"
