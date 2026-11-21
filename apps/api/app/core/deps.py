"""FastAPI dependencies: current user, role checks, case-level authorisation."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models import Case, CaseMembership, Role, User

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    try:
        payload = decode_token(creds.credentials)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def require_roles(*roles: Role):
    def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return _dep


def user_can_access_case(db: Session, user: User, case: Case) -> bool:
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
