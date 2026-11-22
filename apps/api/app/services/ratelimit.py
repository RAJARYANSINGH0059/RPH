"""Rate limiting that holds across workers and instances.

The previous limiter counted requests in a per-process dictionary, so two workers allowed twice the intended rate and
a restart forgot everything. Limits are a safety property, so they are kept in the database every instance already
shares.

The window is sliding and implemented as one row per counted request: inserts never conflict, so concurrent workers
cannot race each other into allowing more than the limit, and expiring a window is a delete by time. The cost is one
delete, one count and one insert on the handful of expensive or abusable endpoints that are limited; ordinary reads
are not limited at all.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import RateEvent


class RateLimited(Exception):
    def __init__(self, retry_after: int, limit: int, window_seconds: int):
        self.retry_after = max(1, int(retry_after))
        self.limit = limit
        self.window_seconds = window_seconds
        super().__init__(f"Rate limit of {limit} per {window_seconds}s reached; retry in {self.retry_after}s")


def allow(db: Session, bucket: str, *, limit: int, window_seconds: int, commit: bool = True) -> None:
    """Count this request against `bucket`, or raise RateLimited. The bucket is the subject plus the action, for
    example "demo-session:203.0.113.9" or "report:<user id>"."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=window_seconds)
    db.execute(delete(RateEvent).where(RateEvent.bucket == bucket, RateEvent.at < cutoff))
    used = int(db.execute(select(func.count()).select_from(RateEvent).where(RateEvent.bucket == bucket)).scalar_one())
    if used >= limit:
        oldest = db.execute(select(func.min(RateEvent.at)).where(RateEvent.bucket == bucket)).scalar_one()
        if oldest is not None and oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=timezone.utc)
        retry = window_seconds if oldest is None else int((oldest + timedelta(seconds=window_seconds) - now).total_seconds()) + 1
        if commit:
            db.commit()  # keep the expiry delete even when refusing
        raise RateLimited(retry, limit, window_seconds)
    db.add(RateEvent(bucket=bucket, at=now))
    if commit:
        db.commit()


def used(db: Session, bucket: str, *, window_seconds: int) -> int:
    """How many requests the bucket has used inside the window. For tests and for an administrative view."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
    return int(db.execute(select(func.count()).select_from(RateEvent)
                          .where(RateEvent.bucket == bucket, RateEvent.at >= cutoff)).scalar_one())


def client_key(request) -> str:
    """The caller's address as the deployment reports it. Behind the web tier this is the forwarded address; it is a
    best-effort identifier, not an identity, and is never stored anywhere else."""
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return fwd or (request.client.host if request.client else "unknown")
