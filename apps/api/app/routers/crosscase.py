from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_case_or_404, get_current_user
from app.db.session import get_db
from app.models import Case, CaseMembership, Role, User
from app.services import audit
from app.services.crosscase import correlate, related_cases

router = APIRouter(prefix="/crosscase", tags=["crosscase"])


class CorrelateRequest(BaseModel):
    case_ids: list[str] = Field(min_length=2, max_length=12)


@router.post("/correlate")
def correlate_cases(body: CorrelateRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = correlate(db, user, body.case_ids)
    if result is None:
        # one or more cases do not exist or are not accessible: do not reveal which
        raise HTTPException(404, "One or more cases not found")
    audit.record(db, "crosscase.correlated", actor_id=user.id, detail={"case_ids": body.case_ids, "fingerprint": result["fingerprint"], "links": len(result["links"])})
    db.commit()
    return result


@router.get("/cases/{case_id}/related")
def related(case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"case_id": case.id, "related": related_cases(db, user, case), "note": "Only cases you are authorised to access are searched."}


# ---- case membership management (needed for revocation tests and supervisor access) -------------------------------

class MemberRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    role_in_case: str = Field(default="analyst", pattern="^(analyst|supervisor|viewer)$")


def _can_manage(db: Session, user: User, case: Case) -> bool:
    return user.role == Role.admin or case.created_by == user.id


@router.get("/cases/{case_id}/members")
def list_members(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    rows = db.execute(select(CaseMembership, User).join(User, User.id == CaseMembership.user_id).where(CaseMembership.case_id == case.id)).all()
    return [{"user_id": u.id, "email": u.email, "display_name": u.display_name, "role": u.role.value, "role_in_case": m.role_in_case} for m, u in rows]


@router.post("/cases/{case_id}/members", status_code=201)
def add_member(body: MemberRequest, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _can_manage(db, user, case):
        raise HTTPException(403, "Only the case owner or an admin can manage membership")
    target = db.execute(select(User).where(User.email == body.email.lower())).scalar_one_or_none()
    if target is None:
        raise HTTPException(404, "User not found")
    if target.is_demo and not case.is_synthetic:
        raise HTTPException(403, "Demo visitors can only be members of synthetic cases")
    existing = db.execute(select(CaseMembership).where(CaseMembership.case_id == case.id, CaseMembership.user_id == target.id)).scalar_one_or_none()
    if existing is None:
        db.add(CaseMembership(case_id=case.id, user_id=target.id, role_in_case=body.role_in_case))
    else:
        existing.role_in_case = body.role_in_case
    audit.record(db, "case.member_added", actor_id=user.id, case_id=case.id, target_type="user", target_id=target.id, detail={"role_in_case": body.role_in_case})
    db.commit()
    return {"ok": True}


@router.delete("/cases/{case_id}/members/{user_id}")
def remove_member(user_id: str, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not _can_manage(db, user, case):
        raise HTTPException(403, "Only the case owner or an admin can manage membership")
    if user_id == case.created_by:
        raise HTTPException(400, "The case owner cannot be removed")
    m = db.execute(select(CaseMembership).where(CaseMembership.case_id == case.id, CaseMembership.user_id == user_id)).scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Membership not found")
    db.delete(m)
    audit.record(db, "case.member_removed", actor_id=user.id, case_id=case.id, target_type="user", target_id=user_id)
    db.commit()
    return {"ok": True}
