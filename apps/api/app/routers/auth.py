from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import Case, Role, User
from app.schemas import LoginRequest, TokenResponse, UserOut
from app.services import audit

DEMO_SESSION_MINUTES = 240
DEMO_RETENTION_HOURS = 24  # expired demo workspaces (users + their synthetic cases) are removed on the next demo-session request
_RATE: dict[str, deque] = defaultdict(deque)  # in-process per-IP limiter (single worker); documented limitation
RATE_LIMIT, RATE_WINDOW_S = 10, 600

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(u: User) -> UserOut:
    return UserOut(id=u.id, email=u.email, display_name=u.display_name, role=u.role.value)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    audit.record(db, "auth.login", actor_id=user.id)
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id, user.role.value), user=_user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


def _rate_limited(key: str) -> bool:
    now = time.time()
    q = _RATE[key]
    while q and now - q[0] > RATE_WINDOW_S:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return True
    q.append(now)
    return False


def _cleanup_expired_demo(db: Session, limit: int = 20) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=DEMO_RETENTION_HOURS)
    stale = db.execute(select(User).where(User.is_demo.is_(True), User.expires_at.is_not(None), User.expires_at < cutoff).limit(limit)).scalars().all()
    n = 0
    for u in stale:
        for c in db.execute(select(Case).where(Case.created_by == u.id)).scalars():
            db.delete(c)  # cascades to files/evidence/relationships (storage objects stay on disk until the periodic sweep)
        db.delete(u)
        n += 1
    return n


class DemoSessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut
    workspace: Literal["synthetic_demo"] = "synthetic_demo"
    notice: str = "SYNTHETIC DEMO — NOT REAL CASE DATA. Isolated visitor workspace; expires automatically."


@router.post("/demo-session", response_model=DemoSessionOut, status_code=201)
def demo_session(request: Request, db: Session = Depends(get_db)):
    """One-click public demo: creates an isolated, least-privilege demo_analyst principal with an absolute expiry.
    Origin is checked against the configured CORS origins (the BFF forwards the browser Origin); rate limited per IP."""
    s = get_settings()
    origin = request.headers.get("origin") or request.headers.get("x-forwarded-origin") or ""
    import re as _re
    allowed = origin in s.cors_origin_list or (bool(s.cors_origin_regex) and _re.match(s.cors_origin_regex, origin) is not None) or origin == ""
    if not allowed:
        raise HTTPException(403, "Origin not allowed for demo sessions")
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()
    if _rate_limited(ip):
        raise HTTPException(429, "Too many demo sessions from this address; try again later")
    _cleanup_expired_demo(db)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=DEMO_SESSION_MINUTES)
    tag = secrets.token_hex(6)
    user = User(email=f"visitor-{tag}@demo.synthetic", display_name=f"Demo visitor {tag[:4]}", password_hash=hash_password(secrets.token_urlsafe(32)), role=Role.demo_analyst,
                is_demo=True, expires_at=expires)
    db.add(user)
    db.flush()
    audit.record(db, "auth.demo_session", actor_id=user.id, detail={"expires_at": expires.isoformat()})
    db.commit()
    token = create_access_token(user.id, user.role.value, minutes=DEMO_SESSION_MINUTES)
    return DemoSessionOut(access_token=token, expires_at=expires, user=_user_out(user))


class ShortTokenIn(BaseModel):
    scope: Literal["upload", "download"]
    # Binding the token to one case stops it being replayed against another case the holder may also access.
    case_id: str | None = Field(default=None, max_length=36)


@router.post("/short-token")
def short_token(body: ShortTokenIn, user: User = Depends(get_current_user)):
    """Short-lived (10 min) scoped token used by the browser for direct file upload/download to the API (the BFF proxy has body limits).
    It carries the same principal and expiry rules; the main session stays in the HttpOnly cookie."""
    minutes = 10
    if user.expires_at is not None:
        minutes = max(1, min(minutes, int((user.expires_at - datetime.now(timezone.utc)).total_seconds() // 60) or 1))
    case_id = getattr(body, "case_id", None)
    token = create_access_token(user.id, user.role.value, minutes=minutes, scope=body.scope, case_id=case_id)
    return {"access_token": token, "expires_in_seconds": minutes * 60, "scope": body.scope, "case_id": case_id,
            "note": "Bound to this case when case_id is supplied; a bound token is refused on any other case."}


@router.post("/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    audit.record(db, "auth.logout", actor_id=user.id)
    db.commit()
    return {"ok": True, "note": "Tokens are stateless; the BFF clears the session cookie. Demo principals expire automatically."}
