"""FastAPI dependencies: current user, role checks, case-level authorisation."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.scopes import KNOWN_SCOPES, describe, scope_permits
from app.core.security import decode_token
from app.db.session import get_db
from app.models import Case, CaseMembership, Role, User

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """Authenticate the bearer token and enforce its scope against the route being called.

    Default-deny: a token whose scope is not `full` reaches only the routes listed in `app.core.scopes`, so a new
    endpoint is closed to scoped upload/download tokens until someone adds it there deliberately."""
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    try:
        payload = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    if user.expires_at is not None:
        from datetime import datetime, timezone
        if user.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Demo session expired")
    if int(payload.get("epoch", 0)) != int(getattr(user, "token_epoch", 0) or 0):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session has been revoked; sign in again")
    scope = payload.get("scope") or "full"
    if scope not in KNOWN_SCOPES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Unknown token scope")
    route = request.scope.get("route")
    template = getattr(route, "path", None)
    if not scope_permits(scope, request.method, template):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Token scope '{scope}' is not valid on this endpoint. {describe(scope)}")
    request.state.token_scope = scope
    request.state.token_case = payload.get("case")
    # A scoped token bound to one case must not be replayed against another, even one its holder may access.
    bound = payload.get("case")
    if bound and scope != "full":
        asked = request.path_params.get("case_id")
        if asked and asked != bound:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This token was issued for a different case")
    return user


def require_token_scope(*scopes: str):
    """Explicit per-route scope requirement, for routes that must only ever be reached by a particular token kind."""
    def _dep(request: Request, user: User = Depends(get_current_user)) -> User:
        if getattr(request.state, "token_scope", "full") not in scopes:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This endpoint requires a token of scope: " + ", ".join(sorted(scopes)))
        return user

    return _dep


def require_roles(*roles: Role):
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return _dep


def user_can_access_case(db: Session, user: User, case: Case) -> bool:
    if user.role == Role.demo_analyst and not case.is_synthetic:
        return False  # demo visitors never see non-synthetic cases, even if someone added them as a member
    if user.role == Role.admin:
        return True
    if case.created_by == user.id:
        return True
    m = db.execute(
        select(CaseMembership).where(CaseMembership.case_id == case.id, CaseMembership.user_id == user.id)
    ).scalar_one_or_none()
    return m is not None


def get_case_or_404(case_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Case:
    case = db.get(Case, case_id)
    if case is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    if not user_can_access_case(db, user, case):
        # 404 rather than 403 so a non-member cannot confirm that a case exists
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Case not found")
    return case
