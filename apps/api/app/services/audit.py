from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditEvent


def record(
    db: Session,
    action: str,
    *,
    actor_id: str | None = None,
    case_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict | None = None,
) -> AuditEvent:
    ev = AuditEvent(
        action=action,
        actor_id=actor_id,
        case_id=case_id,
        target_type=target_type,
        target_id=target_id,
        detail=detail or {},
    )
    db.add(ev)
    return ev
