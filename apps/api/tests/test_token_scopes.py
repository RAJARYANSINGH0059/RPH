"""Scoped-token enforcement.

Short-lived upload and download tokens exist only to carry bytes past the web tier. These tests pin that they reach
exactly the routes that carry those bytes and nothing else, that unknown scopes are refused, that scope never widens
authority past role and case-membership checks, and that expiry is honoured.
"""
import time

import jwt
import pytest

from app.core.config import get_settings
from app.core.scopes import DOWNLOAD_ROUTES, UPLOAD_ROUTES
from app.core.security import create_access_token


@pytest.fixture(scope="module")
def case_id(client, analyst):
    r = client.post("/api/synthetic/generate", json={"scenario_type": "desert_mirage", "difficulty": "messy", "size": "small", "seed": 6101}, headers=analyst)
    assert r.status_code == 201
    return r.json()["case"]["id"]


def _short(client, analyst, scope):
    r = client.post("/api/auth/short-token", json={"scope": scope}, headers=analyst)
    assert r.status_code in (200, 201), r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_download_token_cannot_read_ordinary_endpoints(client, analyst, case_id):
    h = _short(client, analyst, "download")
    for path in (f"/api/cases/{case_id}", "/api/cases", f"/api/cases/{case_id}/transactions", f"/api/cases/{case_id}/graph", f"/api/cases/{case_id}/paths"):
        r = client.get(path, headers=h)
        assert r.status_code == 403, f"{path} allowed a download token: {r.status_code}"
        assert "scope" in r.json()["detail"].lower()


def test_download_token_cannot_mutate(client, analyst, case_id):
    h = _short(client, analyst, "download")
    assert client.post("/api/cases", json={"title": "x" * 12, "summary": "y" * 12}, headers=h).status_code == 403
    assert client.post(f"/api/cases/{case_id}/hypotheses", json={"title": "t" * 8, "statement": "s" * 12}, headers=h).status_code == 403
    assert client.post(f"/api/cases/{case_id}/upload", files={"files": ("a.csv", b"a,b\n1,2\n", "text/csv")}, headers=h).status_code == 403


def test_upload_token_cannot_read_or_download(client, analyst, case_id):
    h = _short(client, analyst, "upload")
    assert client.get(f"/api/cases/{case_id}", headers=h).status_code == 403
    assert client.get(f"/api/cases/{case_id}/report.pdf", headers=h).status_code == 403
    assert client.get(f"/api/cases/{case_id}/report.json", headers=h).status_code == 403
    assert client.get("/api/cases", headers=h).status_code == 403


def test_upload_token_works_on_its_own_route(client, analyst, case_id):
    h = _short(client, analyst, "upload")
    r = client.post(f"/api/cases/{case_id}/upload", files={"files": ("scoped.csv", b"Date,Narration,Ref No,Debit,Credit,Balance,Account,Counterparty,Beneficiary Name\n", "text/csv")}, headers=h)
    assert r.status_code in (200, 201), r.text


def test_download_token_works_on_download_routes(client, analyst, case_id):
    h = _short(client, analyst, "download")
    assert client.get(f"/api/cases/{case_id}/report.pdf", headers=h).content[:4] == b"%PDF"
    assert client.get(f"/api/cases/{case_id}/report.json", headers=h).status_code == 200
    assert client.get(f"/api/cases/{case_id}/report/transactions.csv", headers=h).status_code == 200


def test_full_token_still_reaches_both(client, analyst, case_id):
    assert client.get(f"/api/cases/{case_id}/report.pdf", headers=analyst).status_code == 200
    assert client.get(f"/api/cases/{case_id}", headers=analyst).status_code == 200


def test_unknown_scope_is_refused_everywhere(client, analyst, case_id):
    tok = create_access_token("x", "analyst", minutes=5, scope="superuser")
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get(f"/api/cases/{case_id}", headers=h).status_code in (401, 403)
    tok2 = create_access_token("x", "analyst", minutes=5, scope="")
    assert client.get(f"/api/cases/{case_id}", headers={"Authorization": f"Bearer {tok2}"}).status_code in (401, 403)


def test_scope_does_not_widen_case_access(client, analyst, supervisor, case_id):
    """A download token for a user who is not a member of the case still cannot download that case."""
    other = client.post("/api/synthetic/generate", json={"scenario_type": "benign_lookalike", "difficulty": "clean", "size": "small", "seed": 6102}, headers=analyst).json()["case"]["id"]
    h = _short(client, supervisor, "download")
    r = client.get(f"/api/cases/{other}/report.pdf", headers=h)
    assert r.status_code == 404, "case membership must still be enforced for a scoped token"


def test_expired_scoped_token_is_refused(client, analyst, case_id):
    s = get_settings()
    payload = {"sub": "whoever", "role": "analyst", "scope": "download", "iat": int(time.time()) - 7200, "exp": int(time.time()) - 60}
    tok = jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)
    assert client.get(f"/api/cases/{case_id}/report.pdf", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_malformed_and_unsigned_tokens_are_refused(client, case_id):
    for tok in ("not-a-token", "a.b.c", jwt.encode({"sub": "x", "scope": "full"}, "wrong-secret", algorithm="HS256")):
        assert client.get(f"/api/cases/{case_id}", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_scope_route_tables_match_real_routes():
    """Every route named in the scope policy exists, so the policy cannot drift into allowing nothing silently."""
    from app.main import app
    real = {(m, r.path) for r in app.routes if hasattr(r, "methods") for m in r.methods}
    for entry in UPLOAD_ROUTES | DOWNLOAD_ROUTES:
        assert entry in real, f"scope policy names a route that does not exist: {entry}"


# --- issuer / audience / not-before / resource binding -------------------------------------------------------------

def test_issuer_and_audience_are_validated(client, case_id):
    """A token signed with our key but minted for another issuer or audience must not be accepted."""
    s = get_settings()
    base = {"sub": "x", "role": "analyst", "scope": "full", "iat": int(time.time()), "exp": int(time.time()) + 600}
    for claims in ({**base, "iss": "someone-else", "aud": "ps05x-web"},
                   {**base, "iss": "ps05x-api", "aud": "another-app"},
                   base):  # no issuer or audience at all
        tok = jwt.encode(claims, s.jwt_secret, algorithm=s.jwt_algorithm)
        assert client.get(f"/api/cases/{case_id}", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_token_not_yet_valid_is_refused(client, case_id):
    s = get_settings()
    future = int(time.time()) + 3600
    tok = jwt.encode({"sub": "x", "role": "analyst", "scope": "full", "iss": "ps05x-api", "aud": "ps05x-web",
                      "nbf": future, "iat": future, "exp": future + 600}, s.jwt_secret, algorithm=s.jwt_algorithm)
    assert client.get(f"/api/cases/{case_id}", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_download_token_is_bound_to_one_case(client, analyst, case_id):
    """A download token issued for one case must not export another, even one its holder can access."""
    other = client.post("/api/synthetic/generate", json={"scenario_type": "benign_lookalike", "difficulty": "clean", "size": "small", "seed": 6401}, headers=analyst).json()["case"]["id"]
    r = client.post("/api/auth/short-token", json={"scope": "download", "case_id": case_id}, headers=analyst)
    assert r.status_code == 200 and r.json()["case_id"] == case_id
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get(f"/api/cases/{case_id}/report.pdf", headers=h).status_code == 200, "the bound case must still work"
    assert client.get(f"/api/cases/{other}/report.pdf", headers=h).status_code == 403, "a bound token must not export another case"


def test_upload_token_is_bound_to_one_case(client, analyst, case_id):
    other = client.post("/api/synthetic/generate", json={"scenario_type": "benign_lookalike", "difficulty": "clean", "size": "small", "seed": 6402}, headers=analyst).json()["case"]["id"]
    tok = client.post("/api/auth/short-token", json={"scope": "upload", "case_id": case_id}, headers=analyst).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    f = {"files": ("bound.csv", b"Date,Narration,Ref No,Debit,Credit,Balance,Account,Counterparty,Beneficiary Name\n", "text/csv")}
    assert client.post(f"/api/cases/{other}/upload", files=f, headers=h).status_code == 403
    assert client.post(f"/api/cases/{case_id}/upload", files=f, headers=h).status_code in (200, 201)


def test_unbound_scoped_token_still_requires_membership(client, analyst, supervisor, case_id):
    """Backwards compatibility: a token minted without a case binding is still constrained by case membership."""
    tok = client.post("/api/auth/short-token", json={"scope": "download"}, headers=supervisor).json()["access_token"]
    assert client.get(f"/api/cases/{case_id}/report.pdf", headers={"Authorization": f"Bearer {tok}"}).status_code == 404


# --- revocation -----------------------------------------------------------------------------------------------------

def test_logout_revokes_every_token_held_by_that_principal(client):
    """Signing out must invalidate the session and any short-lived token still in flight, not merely drop a cookie."""
    r = client.post("/api/auth/demo-session", headers={"origin": "http://localhost:3000"})
    assert r.status_code == 201
    session = {"Authorization": f"Bearer {r.json()['access_token']}"}
    short = client.post("/api/auth/short-token", json={"scope": "download"}, headers=session).json()["access_token"]
    assert client.get("/api/auth/me", headers=session).status_code == 200

    out = client.post("/api/auth/logout", headers=session)
    assert out.status_code == 200 and out.json()["revoked"] is True

    assert client.get("/api/auth/me", headers=session).status_code == 401, "the session token must stop working"
    assert client.get("/api/cases", headers={"Authorization": f"Bearer {short}"}).status_code == 401, \
        "a short-lived token issued before logout must stop working too"


def test_admin_can_revoke_another_principal_and_others_are_unaffected(client, admin):
    """A principal created for this test is revoked, so the shared fixtures other modules depend on stay valid."""
    demo = client.post("/api/auth/demo-session", headers={"origin": "http://localhost:3000"}).json()
    victim = {"Authorization": f"Bearer {demo['access_token']}"}
    assert client.get("/api/auth/me", headers=victim).status_code == 200

    r = client.post(f"/api/auth/revoke/{demo['user']['id']}", headers=admin)
    assert r.status_code == 200 and r.json()["token_epoch"] >= 1
    assert client.get("/api/auth/me", headers=victim).status_code == 401, "the revoked principal's token must be refused"
    assert client.get("/api/auth/me", headers=admin).status_code == 200, "another principal must be unaffected"


def test_revocation_requires_an_administrator(client, supervisor):
    """A fresh non-administrator principal is used: the shared analyst fixture is revoked by the test above, which is
    itself evidence that revocation takes effect."""
    me = client.get("/api/auth/me", headers=supervisor).json()
    demo = client.post("/api/auth/demo-session", headers={"origin": "http://localhost:3000"}).json()
    demo_h = {"Authorization": f"Bearer {demo['access_token']}"}
    assert client.post(f"/api/auth/revoke/{me['id']}", headers=demo_h).status_code == 403
    assert client.post(f"/api/auth/revoke/{me['id']}", headers=supervisor).status_code == 403


def test_token_from_a_superseded_epoch_is_refused(client, admin):
    """A token minted under an old epoch is refused even though its signature and expiry are valid. A principal
    created here is used, so the shared fixtures stay valid for the rest of the suite."""
    demo = client.post("/api/auth/demo-session", headers={"origin": "http://localhost:3000"}).json()
    uid = demo["user"]["id"]
    stale = create_access_token(uid, "demo_analyst", minutes=30, epoch=0)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {stale}"}).status_code == 200
    client.post(f"/api/auth/revoke/{uid}", headers=admin)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {stale}"}).status_code == 401
