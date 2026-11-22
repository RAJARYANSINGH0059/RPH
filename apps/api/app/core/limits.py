"""Rate-limit policy: which action is limited, how much, and over what window.

Limits protect the free-plan instance and the demo from abuse. They are deliberately generous for ordinary
investigative work and tight only on the endpoints that create principals, mint credentials or cost real compute.
Reads are not limited.
"""
from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Request, status

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.services.ratelimit import RateLimited, allow, client_key

# action -> (limit, window seconds, whether the bucket is the caller's address rather than their user id)
POLICY: dict[str, tuple[int, int, bool]] = {
    "demo-session":     (10, 600, True),    # creating isolated demo principals
    "login":            (10, 300, True),    # password attempts
    "short-token":      (60, 600, False),   # minting transfer credentials
    "synthetic":        (12, 600, False),   # generating a case costs real compute
    "case-create":      (30, 600, False),
    "upload":           (60, 600, False),
    "report":           (30, 600, False),   # PDF/CSV/ZIP generation
    "simulation":       (60, 600, False),   # counterfactual lab, resilience, rule compiler
    "crosscase":        (30, 600, False),
}


def enabled() -> bool:
    """Limits are on by default. A test run that is not exercising them sets RATE_LIMIT_ENABLED=0, so a limit cannot
    silently fail unrelated tests; the limiter itself is covered by tests/test_rate_limiting.py."""
    return os.environ.get("RATE_LIMIT_ENABLED", "1") not in {"0", "false", "False"}


def _raise(exc: RateLimited):
    raise HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Too many requests: {exc.limit} per {exc.window_seconds // 60} minutes for this action. Retry in {exc.retry_after}s.",
        headers={"Retry-After": str(exc.retry_after)},
    )


def limit_anonymous(action: str):
    """For endpoints reached before there is a principal: the bucket is the caller's address."""
    limit, window, _ = POLICY[action]

    def _dep(request: Request, db=Depends(get_db)) -> None:
        if not enabled():
            return
        try:
            allow(db, f"{action}:{client_key(request)}", limit=limit, window_seconds=window)
        except RateLimited as exc:
            _raise(exc)

    return _dep


def limit_user(action: str):
    """For authenticated endpoints: the bucket is the principal, so one caller cannot exhaust another's allowance."""
    limit, window, by_address = POLICY[action]

    def _dep(request: Request, user: User = Depends(get_current_user), db=Depends(get_db)) -> User:
        if not enabled():
            return user
        subject = client_key(request) if by_address else user.id
        try:
            allow(db, f"{action}:{subject}", limit=limit, window_seconds=window)
        except RateLimited as exc:
            _raise(exc)
        return user

    return _dep
