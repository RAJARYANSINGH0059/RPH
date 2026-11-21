"""Auth, RBAC and case-level authorisation (IDOR) tests."""


def test_health(client):
    assert client.get("/api/health/live").json()["status"] == "ok"
    assert client.get("/api/health/ready").json()["status"] == "ready"


def test_login_rejects_bad_password(client):
    r = client.post("/api/auth/login", json={"email": "analyst@demo.local", "password": "wrong"})
    assert r.status_code == 401


def test_unauthenticated_access_denied(client):
    assert client.get("/api/cases").status_code == 401
    assert client.get("/api/connectors/status").status_code == 401


def test_me(client, analyst):
    assert client.get("/api/auth/me", headers=analyst).json()["role"] == "analyst"


def test_case_isolation_idor(client, analyst, other_analyst, admin):
    r = client.post("/api/cases", json={"title": "Private case"}, headers=analyst)
    cid = r.json()["id"]
    assert client.get(f"/api/cases/{cid}", headers=analyst).status_code == 200
    # another analyst cannot see, upload to, read graph of, or export the case
    assert client.get(f"/api/cases/{cid}", headers=other_analyst).status_code == 404
    assert client.get(f"/api/cases/{cid}/graph", headers=other_analyst).status_code == 404
    assert client.get(f"/api/cases/{cid}/report.json", headers=other_analyst).status_code == 404
    assert client.post(f"/api/cases/{cid}/upload", files=[("files", ("a.csv", b"Date,Amount\n2026-01-01,1\n", "text/csv"))], headers=other_analyst).status_code == 404
    assert cid not in [c["id"] for c in client.get("/api/cases", headers=other_analyst).json()]
    # admin can
    assert client.get(f"/api/cases/{cid}", headers=admin).status_code == 200


def test_role_gate_on_connector_healthcheck(client, analyst, admin):
    assert client.post("/api/connectors/healthcheck", headers=analyst).status_code == 403
    r = client.post("/api/connectors/healthcheck", headers=admin)
    assert r.status_code == 200
    statuses = {c["name"]: c["status"] for c in r.json()}
    # nothing is configured in tests: no connector may claim to be live
    assert "live" not in statuses.values()
    assert statuses["synthetic_mock"] == "mock"


def test_tampered_token_rejected(client, analyst):
    bad = {"Authorization": analyst["Authorization"][:-3] + "abc"}
    assert client.get("/api/auth/me", headers=bad).status_code == 401
