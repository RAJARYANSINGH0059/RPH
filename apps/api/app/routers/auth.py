from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import get_current_user, require_roles
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models import Case, Role, User
from app.schemas import LoginRequest, TokenResponse, UserOut
from app.core.limits import POLICY, enabled as limits_enabled, limit_user
from app.services import audit, ratelimit

DEMO_SESSION_MINUTES = 240
DEMO_RETENTION_HOURS = 24  # expired demo workspaces (users + their synthetic cases) are removed on the next demo-session request
# Rate limiting lives in app/services/ratelimit.py and is shared through the database, so it holds across workers.

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
    return TokenResponse(access_token=create_access_token(user.id, user.role.value, epoch=user.token_epoch), user=_user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)



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
    ip = ratelimit.client_key(request)
    try:
        limit, window, _ = POLICY["demo-session"]
        if limits_enabled():
            ratelimit.allow(db, f"demo-session:{ip}", limit=limit, window_seconds=window, commit=False)
    except ratelimit.RateLimited as exc:
        raise HTTPException(429, f"Too many demo sessions from this address; retry in {exc.retry_after}s",
                            headers={"Retry-After": str(exc.retry_after)})
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
    token = create_access_token(user.id, user.role.value, minutes=DEMO_SESSION_MINUTES, epoch=user.token_epoch)
    return DemoSessionOut(access_token=token, expires_at=expires, user=_user_out(user))


class ShortTokenIn(BaseModel):
    scope: Literal["upload", "download"]
    # Binding the token to one case stops it being replayed against another case the holder may also access.
    case_id: str | None = Field(default=None, max_length=36)


@router.post("/short-token")
def short_token(body: ShortTokenIn, user: User = Depends(limit_user("short-token"))):
    """Short-lived (10 min) scoped token used by the browser for direct file upload/download to the API (the BFF proxy has body limits).
    It carries the same principal and expiry rules; the main session stays in the HttpOnly cookie."""
    minutes = 10
    if user.expires_at is not None:
        minutes = max(1, min(minutes, int((user.expires_at - datetime.now(timezone.utc)).total_seconds() // 60) or 1))
    case_id = getattr(body, "case_id", None)
    token = create_access_token(user.id, user.role.value, minutes=minutes, scope=body.scope, case_id=case_id, epoch=user.token_epoch)
    return {"access_token": token, "expires_in_seconds": minutes * 60, "scope": body.scope, "case_id": case_id,
            "note": "Bound to this case when case_id is supplied; a bound token is refused on any other case."}


@router.post("/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Signing out raises the principal's token epoch, which invalidates every token already issued to them,
    including any short-lived upload or download token still in flight."""
    user.token_epoch = (user.token_epoch or 0) + 1
    audit.record(db, "auth.logout", actor_id=user.id, detail={"token_epoch": user.token_epoch})
    db.commit()
    return {"ok": True, "revoked": True, "note": "Every token issued to this principal before now is no longer accepted."}


@router.post("/revoke/{user_id}")
def revoke_sessions(user_id: str, actor: User = Depends(require_roles(Role.admin)), db: Session = Depends(get_db)):
    """Emergency revocation: invalidate every token held by one principal. Administrators only."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    target.token_epoch = (target.token_epoch or 0) + 1
    audit.record(db, "auth.sessions_revoked", actor_id=actor.id, target_type="user", target_id=target.id,
                 detail={"token_epoch": target.token_epoch})
    db.commit()
    return {"ok": True, "user_id": target.id, "token_epoch": target.token_epoch,
            "note": "Every token issued to this principal before now is refused. They must sign in again."}
