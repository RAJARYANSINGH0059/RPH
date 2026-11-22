"""Shared rate limiting.

The previous limiter lived in a per-process dictionary, so two workers allowed twice the intended rate and a restart
forgot everything. These tests pin the behaviour of the database-backed limiter: the limit is enforced, the window
expires, a refusal carries Retry-After, one caller's allowance is their own, and the state survives a new session
(which is what "shared across workers" reduces to inside a test process).
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.models import RateEvent
from app.services.ratelimit import RateLimited, allow, used

ORIGIN = {"origin": "http://localhost:3000"}


@pytest.fixture(autouse=True)
def _clean(client, monkeypatch):
    """This module is the one that exercises limits, so it turns them on for itself and starts from a clean bucket."""
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "1")
    with SessionLocal() as db:
        db.execute(delete(RateEvent))
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(delete(RateEvent))
        db.commit()


def test_limit_is_enforced_and_the_window_expires():
    with SessionLocal() as db:
        for _ in range(3):
            allow(db, "unit:a", limit=3, window_seconds=60)
        with pytest.raises(RateLimited) as exc:
            allow(db, "unit:a", limit=3, window_seconds=60)
        assert exc.value.retry_after >= 1 and exc.value.limit == 3
        assert used(db, "unit:a", window_seconds=60) == 3

        # age the events past the window: the bucket frees up without any background job
        for ev in db.query(RateEvent).filter(RateEvent.bucket == "unit:a").all():
            ev.at = datetime.now(timezone.utc) - timedelta(seconds=120)
        db.commit()
        allow(db, "unit:a", limit=3, window_seconds=60)
        assert used(db, "unit:a", window_seconds=60) == 1


def test_buckets_are_independent():
    with SessionLocal() as db:
        for _ in range(3):
            allow(db, "unit:b", limit=3, window_seconds=60)
        allow(db, "unit:c", limit=3, window_seconds=60)  # a different caller is unaffected
        assert used(db, "unit:c", window_seconds=60) == 1


def test_state_is_shared_rather_than_per_process():
    """Counted in one session, seen in another: the limiter's state is in the database, not in a worker's memory."""
    with SessionLocal() as db:
        allow(db, "unit:shared", limit=5, window_seconds=60)
    with SessionLocal() as other:
        assert used(other, "unit:shared", window_seconds=60) == 1
        allow(other, "unit:shared", limit=5, window_seconds=60)
    with SessionLocal() as third:
        assert used(third, "unit:shared", window_seconds=60) == 2


def test_demo_session_creation_is_limited_and_says_when_to_retry(client):
    codes, retry_after = [], None
    for _ in range(12):
        r = client.post("/api/auth/demo-session", headers=ORIGIN)
        codes.append(r.status_code)
        if r.status_code == 429:
            retry_after = r.headers.get("retry-after")
            break
    assert 201 in codes and 429 in codes, f"expected the limit to bite: {codes}"
    assert retry_after and int(retry_after) >= 1, "a refusal must say when to retry"


def test_case_generation_is_limited_per_principal(client, analyst):
    """An expensive endpoint is limited by principal, so one caller cannot exhaust the instance for everyone."""
    seen429 = False
    for i in range(14):
        r = client.post("/api/synthetic/generate",
                        json={"scenario_type": "benign_lookalike", "difficulty": "clean", "size": "small", "seed": 7100 + i},
                        headers=analyst)
        if r.status_code == 429:
            seen429 = True
            assert r.headers.get("retry-after")
            assert "Retry in" in r.json()["detail"]
            break
    assert seen429, "generation should be limited well before fourteen cases"
