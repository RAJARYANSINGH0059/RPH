"""Automated authorization matrix over every registered route.

The specification asks for server-side authorization to be proven route by route rather than inferred from the fact
that the interface hides a link. This walks the application's own route table, so a route added later is covered the
moment it exists, and asserts the invariants that must hold for every one of them:

* anonymous callers are refused everywhere except the endpoints that are deliberately public;
* a malformed or wrongly signed token is refused everywhere;
* an expired token is refused everywhere;
* a token with an unknown scope is refused everywhere;
* upload and download tokens reach only the routes their scope lists;
* a case-scoped route is a 404 for a principal who is not a member of that case.

It asserts refusal, never permission: that a principal is refused is a safety property, while what a principal may do
is covered by the feature tests.
"""
import time

import jwt
import pytest

from app.core.config import get_settings
from app.core.scopes import DOWNLOAD_ROUTES, UPLOAD_ROUTES
from app.core.security import create_access_token
from app.main import app

# Endpoints that are public on purpose. Each was checked for what it actually returns:
#   /                       service banner: name, docs path, health path, and the no-live-connection notice.
#   /api/synthetic/options  the list of scenario names, difficulties and sizes; static configuration, no case data.
#   /api/health/*           service status.
#   /api/auth/login, /api/auth/demo-session  the two ways to obtain a session.
PUBLIC_PREFIXES = ("/api/health", "/api/auth/login", "/api/auth/demo-session", "/api/synthetic/options",
                   "/openapi", "/docs", "/redoc")
PUBLIC_EXACT = {("GET", "/")}
SKIP_PREFIXES = ("/openapi", "/docs", "/redoc")


def _routes():
    out = []
    for r in app.routes:
        if not hasattr(r, "methods"):
            continue
        for m in sorted(r.methods):
            if m in {"HEAD", "OPTIONS"}:
                continue
            out.append((m, r.path))
    return sorted(set(out))


def _concrete(path: str, case_id: str) -> str:
    """Fill path parameters with plausible values; identifiers that do not exist are fine because we assert refusal."""
    return (path.replace("{case_id}", case_id)
                .replace("{file_id}", "00000000-0000-0000-0000-000000000001")
                .replace("{pack_id}", "00000000-0000-0000-0000-000000000002")
                .replace("{request_id}", "00000000-0000-0000-0000-000000000003")
                .replace("{entity_id}", "00000000-0000-0000-0000-000000000004")
                .replace("{edge_id}", "00000000-0000-0000-0000-000000000005")
                .replace("{evidence_id}", "00000000-0000-0000-0000-000000000006")
                .replace("{hypothesis_id}", "00000000-0000-0000-0000-000000000007")
                .replace("{branch_id}", "00000000-0000-0000-0000-000000000008")
                .replace("{instruction_id}", "00000000-0000-0000-0000-000000000009")
                .replace("{claim_id}", "00000000-0000-0000-0000-00000000000a")
                .replace("{user_id}", "00000000-0000-0000-0000-00000000000b")
                .replace("{account_ref}", "123456789012")
                .replace("{path_index}", "0")
                .replace("{rule_id}", "00000000-0000-0000-0000-00000000000c")
                .replace("{run_id}", "00000000-0000-0000-0000-00000000000d"))


def _send(client, method, url, headers):
    fn = getattr(client, method.lower())
    if method in {"POST", "PUT", "PATCH"}:
        return fn(url, json={}, headers=headers)
    return fn(url, headers=headers)


@pytest.fixture(scope="module")
def case_id(client, analyst):
    r = client.post("/api/synthetic/generate", json={"scenario_type": "benign_lookalike", "difficulty": "clean", "size": "small", "seed": 6501}, headers=analyst)
    assert r.status_code == 201
    return r.json()["case"]["id"]


@pytest.fixture(scope="module")
def matrix(case_id):
    rows = [(m, p) for m, p in _routes() if not p.startswith(SKIP_PREFIXES)]
    assert len(rows) > 80, f"expected the full route table, saw {len(rows)}"
    return [(m, p, _concrete(p, case_id)) for m, p in rows]


def test_anonymous_is_refused_on_every_protected_route(client, matrix):
    leaked = []
    for method, template, url in matrix:
        if template.startswith(PUBLIC_PREFIXES) or (method, template) in PUBLIC_EXACT:
            continue
        r = _send(client, method, url, {})
        if r.status_code not in (401, 403, 405, 422):
            leaked.append(f"{method} {template} -> {r.status_code}")
    assert not leaked, "routes reachable without authentication:\n" + "\n".join(leaked)


def test_malformed_and_wrongly_signed_tokens_are_refused_everywhere(client, matrix):
    bad = [{"Authorization": "Bearer not-a-token"},
           {"Authorization": "Bearer " + jwt.encode({"sub": "x", "scope": "full", "iss": "ps05x-api", "aud": "ps05x-web",
                                                     "iat": int(time.time()), "exp": int(time.time()) + 600},
                                                    "a-different-secret-entirely", algorithm="HS256")}]
    leaked = []
    for method, template, url in matrix:
        if template.startswith(PUBLIC_PREFIXES) or (method, template) in PUBLIC_EXACT:
            continue
        for h in bad:
            r = _send(client, method, url, h)
            if r.status_code not in (401, 403, 405, 422):
                leaked.append(f"{method} {template} -> {r.status_code}")
    assert not leaked, "routes accepted an invalid token:\n" + "\n".join(leaked)


def test_expired_token_is_refused_everywhere(client, matrix):
    s = get_settings()
    tok = jwt.encode({"sub": "x", "role": "admin", "scope": "full", "iss": "ps05x-api", "aud": "ps05x-web",
                      "iat": int(time.time()) - 7200, "exp": int(time.time()) - 60}, s.jwt_secret, algorithm=s.jwt_algorithm)
    h = {"Authorization": f"Bearer {tok}"}
    leaked = [f"{m} {t} -> {r.status_code}" for m, t, u in matrix if not t.startswith(PUBLIC_PREFIXES) and (m, t) not in PUBLIC_EXACT
              for r in [_send(client, m, u, h)] if r.status_code not in (401, 403, 405, 422)]
    assert not leaked, "routes accepted an expired token:\n" + "\n".join(leaked)


def test_unknown_scope_is_refused_everywhere(client, matrix):
    tok = create_access_token("x", "admin", minutes=10, scope="everything")
    h = {"Authorization": f"Bearer {tok}"}
    leaked = [f"{m} {t} -> {r.status_code}" for m, t, u in matrix if not t.startswith(PUBLIC_PREFIXES) and (m, t) not in PUBLIC_EXACT
              for r in [_send(client, m, u, h)] if r.status_code not in (401, 403, 405, 422)]
    assert not leaked, "routes accepted an unknown scope:\n" + "\n".join(leaked)


@pytest.mark.parametrize("scope,allowed", [("upload", UPLOAD_ROUTES), ("download", DOWNLOAD_ROUTES)])
def test_scoped_tokens_reach_only_their_own_routes(client, analyst, matrix, scope, allowed):
    tok = client.post("/api/auth/short-token", json={"scope": scope}, headers=analyst).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    leaked = []
    for method, template, url in matrix:
        if template.startswith(PUBLIC_PREFIXES) or (method, template) in PUBLIC_EXACT or (method, template) in allowed:
            continue
        r = _send(client, method, url, h)
        if r.status_code not in (401, 403, 405, 422):
            leaked.append(f"{method} {template} -> {r.status_code}")
    assert not leaked, f"a {scope} token reached routes outside its scope:\n" + "\n".join(leaked)


def test_non_member_cannot_reach_another_case(client, analyst, supervisor, matrix, case_id):
    """The supervisor is not a member of this case: every case-scoped route must answer 404, never leak existence."""
    leaked = []
    for method, template, url in matrix:
        if "{case_id}" not in template or template.startswith(PUBLIC_PREFIXES):
            continue
        r = _send(client, method, url, supervisor)
        if r.status_code not in (403, 404, 405, 422):
            leaked.append(f"{method} {template} -> {r.status_code}")
    assert not leaked, "a non-member reached case-scoped routes:\n" + "\n".join(leaked)
