from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live():
    s = get_settings()
    from app.parsers import ocr
    from app.services import ml_triage
    from app.services.storage import storage_status
    return {"status": "ok", "service": s.app_name, "version": s.app_version, "ml_triage_model": ml_triage.status(), "ocr": ocr.status(), "storage": storage_status()}


@router.get("/ready")
def ready(response: Response, db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        tables_ok = db.execute(text("SELECT COUNT(*) FROM users")).scalar() is not None
        return {"status": "ready", "database": "ok", "migrations": "applied" if tables_ok else "unknown"}
    except Exception as exc:
        response.status_code = 503
        return {"status": "not_ready", "database": f"error: {type(exc).__name__}"}
