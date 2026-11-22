"""One-click demo sessions: isolation, least privilege, expiry, rate limit, sealed-truth separation and the blind challenge."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import User

ORIGIN = {"origin": "http://localhost:3000"}


def _demo(client):
    r = client.post("/api/auth/demo-session", headers=ORIGIN)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["role"] == "demo_analyst" and "SYNTHETIC DEMO" in body["notice"]
    return {"Authorization": f"Bearer {body['access_token']}"}, body


def test_demo_session_isolation(client, analyst):
    a, _ = _demo(client)
    b, _ = _demo(client)
    real = client.post("/api/cases", json={"title": "Staff case (not synthetic)"}, headers=analyst).json()["id"]
    assert client.get(f"/api/cases/{real}", headers=a).status_code == 404
    assert client.get(f"/api/cases/{real}/twin", headers=a).status_code == 404
    ca = client.post("/api/cases", json={"title": "visitor A case"}, headers=a).json()
    assert ca["is_synthetic"] is True
    assert client.get(f"/api/cases/{ca['id']}", headers=b).status_code == 404  # another visitor cannot see it
    assert [c["id"] for c in client.get("/api/cases", headers=b).json()] == []
    gen = client.post("/api/synthetic/generate", json={"scenario_type": "phishing_to_mule", "difficulty": "clean", "size": "small", "seed": 1}, headers=a).json()["case"]["id"]
    assert client.get(f"/api/cases/{gen}/report.json", headers=b).status_code == 404
    assert client.get(f"/api/cases/{gen}/files", headers=b).status_code == 404
    # staff cannot add a demo visitor to a real case
    me = client.get("/api/auth/me", headers=a).json()
    r = client.post(f"/api/crosscase/cases/{real}/members", json={"email": me["email"], "role_in_case": "analyst"}, headers=analyst)
    assert r.status_code == 403
    # privilege boundaries
    assert client.post("/api/connectors/healthcheck", headers=a).status_code == 403
    assert client.post(f"/api/cases/{gen}/roles/x/decision", json={"status": "HUMAN_REVIEWED", "rationale": "visitor tries to review"}, headers=a).status_code == 403
    assert client.get("/api/privacy/status", headers=a).status_code == 200


def test_demo_origin_rate_limit_and_expiry(client, monkeypatch):
    """Limits are off for the suite at large so they cannot mask unrelated failures; this test needs them, and turns
    them on for itself."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "1")
    assert client.post("/api/auth/demo-session", headers={"origin": "https://attacker.example"}).status_code == 403
    codes = [client.post("/api/auth/demo-session", headers={**ORIGIN, "x-forwarded-for": "198.51.100.77"}).status_code for _ in range(11)]
    assert codes.count(429) >= 1 and codes[0] == 201
    h, body = _demo(client)
    with SessionLocal() as db:
        u = db.execute(select(User).where(User.id == body["user"]["id"])).scalar_one()
        u.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert client.get("/api/auth/me", headers=h).status_code == 401
    # A short-lived scoped token is minted for its holder but reaches only the routes its scope allows. This previously
    # asserted that a download token could call an ordinary endpoint, which was the authorisation defect itself.
    h2, _ = _demo(client)
    tok = client.post("/api/auth/short-token", json={"scope": "download"}, headers=h2).json()
    assert tok["expires_in_seconds"] <= 600
    scoped = {"Authorization": f"Bearer {tok['access_token']}"}
    assert client.get("/api/auth/me", headers=scoped).status_code == 403, "a download token must not reach ordinary endpoints"
    case = client.post("/api/synthetic/generate", json={"scenario_type": "desert_mirage", "difficulty": "clean", "size": "small", "seed": 6301}, headers=h2).json()["case"]["id"]
    assert client.get(f"/api/cases/{case}/report.pdf", headers=scoped).status_code == 200, "a download token must still work on a download route"


def test_sealed_truth_never_served_and_challenge_reveal_only_after_lock(client, analyst):
    h, _ = _demo(client)
    gen = client.post("/api/synthetic/generate", json={"scenario_type": "desert_mirage", "difficulty": "messy", "size": "small", "seed": 6006}, headers=h).json()
    cid = gen["case"]["id"]
    assert "sealed_truth_ref" not in str(gen) and "mule_accounts" not in str(gen)
    for path in ("twin", "paths", "lifecycle", "coverage", "bounded-flow", "dependencies", "adversary", "report.json"):
        body = client.get(f"/api/cases/{cid}/{path}", headers=h).text
        assert "simulated_allocation" not in body and "false_edges" not in body and "mule_accounts" not in body, path
    assert client.get(f"/api/synthetic/cases/{cid}/manifest", headers=h).text.count("sealed_truth_ref") == 0
    st = client.get(f"/api/synthetic/cases/{cid}/challenge", headers=h).json()
    assert st["submitted"] is False
    assert client.get(f"/api/synthetic/cases/{cid}/challenge/reveal", headers=h).status_code == 409
    real = client.post("/api/cases", json={"title": "real"}, headers=analyst).json()["id"]
    assert client.post(f"/api/synthetic/cases/{real}/challenge/submit", json={"mule_pattern_accounts": []}, headers=analyst).status_code == 400
    paths = client.get(f"/api/cases/{cid}/paths", headers=h).json()["paths"]
    sub = client.post(f"/api/synthetic/cases/{cid}/challenge/submit", json={"mule_pattern_accounts": [paths[0]["accounts"][1]], "common_operator_domains": []}, headers=h)
    assert sub.status_code == 201
    rv = client.get(f"/api/synthetic/cases/{cid}/challenge/reveal", headers=h).json()
    assert rv["label"].startswith("SYNTHETIC EVALUATION") and "decoy_rejection" in rv["scores"] and rv["truth_summary"]["decoy_domains"]
    assert rv["scores"]["decoy_rejection"] == 1.0
    # the other visitor still cannot reveal (no submission and no access)
    h2, _ = _demo(client)
    assert client.get(f"/api/synthetic/cases/{cid}/challenge/reveal", headers=h2).status_code == 404
