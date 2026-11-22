"""Token scope policy.

The API issues three kinds of bearer token:

* ``full``      - an ordinary session token from sign-in or a demo session.
* ``upload``    - a ten-minute token minted so the browser can post a large file straight to the API, bypassing the
                  serverless body limit on the web tier.
* ``download``  - a ten-minute token minted so the browser can stream an export straight from the API.

The scoped tokens exist only to carry bytes past the web tier. They must therefore be accepted on exactly the routes
that carry those bytes and nowhere else: a download token must not be able to create a case, promote a relationship or
read a report body, and an upload token must not be able to read anything back.

The policy is central and keyed by the route's own path template, so a new route is denied to scoped tokens until it is
listed here. That is deliberate: forgetting to add a route fails closed. Scope never widens authority — role and
case-membership checks run exactly as they do for a full token.
"""
from __future__ import annotations

KNOWN_SCOPES = frozenset({"full", "upload", "download"})

# (method, route path template) pairs a scoped token may reach.
UPLOAD_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("POST", "/api/cases/{case_id}/upload"),
    ("POST", "/api/cases/{case_id}/payment-instructions/decode-image"),
})

DOWNLOAD_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("GET", "/api/cases/{case_id}/report.pdf"),
    ("GET", "/api/cases/{case_id}/report.json"),
    ("GET", "/api/cases/{case_id}/report/transactions.csv"),
    ("GET", "/api/cases/{case_id}/package.zip"),
    ("GET", "/api/cases/{case_id}/claims/pack.pdf"),
    ("GET", "/api/cases/{case_id}/claims/pack.json"),
    ("GET", "/api/cases/{case_id}/cooperation/{pack_id}/export.zip"),
    ("GET", "/api/cases/{case_id}/files/{file_id}/download"),
    ("GET", "/api/cases/{case_id}/paths/{path_index}/proof.json"),
    ("GET", "/api/cases/{case_id}/paths/{path_index}/proof.pdf"),
    ("GET", "/api/cases/{case_id}/payment-instructions/report.pdf"),
    ("GET", "/api/cases/{case_id}/requests/{request_id}/draft.pdf"),
})

_ALLOWED: dict[str, frozenset[tuple[str, str]]] = {"upload": UPLOAD_ROUTES, "download": DOWNLOAD_ROUTES}


def scope_permits(scope: str, method: str, route_template: str | None) -> bool:
    """True when a token of this scope may be used on this route. Unknown scopes are always refused."""
    if scope == "full":
        return True
    allowed = _ALLOWED.get(scope)
    if allowed is None or route_template is None:
        return False
    return (method.upper(), route_template) in allowed


def describe(scope: str) -> str:
    if scope == "upload":
        return "This upload token may only be used to post a file to the case it was issued for."
    if scope == "download":
        return "This download token may only be used to fetch an export from the case it was issued for."
    return "Unknown token scope."
