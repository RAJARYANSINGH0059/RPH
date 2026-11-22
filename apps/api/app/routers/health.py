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
    """Readiness, subsystem by subsystem.

    Overall status is `ready` only when nothing required is failing, `degraded` when an optional subsystem is
    unavailable but investigation can continue, and `not_ready` when a required one is down. Saying "ready" while a
    required subsystem is unavailable would be the one answer that misleads.

    Optional here means: the application still does its work without it, and says so where it matters. OCR being
    unavailable is visible on every affected file; ephemeral storage is declared on the storage panel.
    """
    subsystems: dict[str, dict] = {}
    required_failed, optional_failed = [], []

    # --- database and migrations (required)
    try:
        db.execute(text("SELECT 1"))
        tables_ok = db.execute(text("SELECT COUNT(*) FROM users")).scalar() is not None
        subsystems["database"] = {"status": "ok", "required": True}
        subsystems["migrations"] = {"status": "applied" if tables_ok else "unknown", "required": True}
        if not tables_ok:
            required_failed.append("migrations")
    except Exception as exc:
        subsystems["database"] = {"status": "error", "required": True, "detail": type(exc).__name__}
        subsystems["migrations"] = {"status": "unknown", "required": True}
        required_failed.append("database")

    # --- evidence storage (required: evidence must be storable and readable)
    try:
        from app.services.storage import storage_status
        st = storage_status()
        durable = bool(st.get("durable"))
        subsystems["storage"] = {"status": "ok" if st.get("backend") else "unavailable", "required": True,
                                 "backend": st.get("backend"), "durable": durable,
                                 "note": None if durable else "Ephemeral: objects do not survive a redeploy. Not durable storage."}
        if not st.get("backend"):
            required_failed.append("storage")
    except Exception as exc:
        subsystems["storage"] = {"status": "error", "required": True, "detail": type(exc).__name__}
        required_failed.append("storage")

    # --- OCR (optional: scanned pages are stored, hashed and flagged for manual review when it is off)
    try:
        from app.parsers import ocr
        o = ocr.status()
        active = o.get("active_engine")
        subsystems["ocr"] = {"status": "ok" if active else "unavailable", "required": False,
                             "engine": active, "mode": o.get("mode"),
                             "note": None if active else "Scanned pages and images are stored and flagged for manual review; no text is extracted."}
        if not active:
            optional_failed.append("ocr")
    except Exception as exc:
        subsystems["ocr"] = {"status": "error", "required": False, "detail": type(exc).__name__}
        optional_failed.append("ocr")

    # --- triage model (optional: rules triage works without it)
    try:
        from app.services import ml_triage
        m = ml_triage.status()
        subsystems["model_artefact"] = {"status": "ok" if m.get("available") else "unavailable", "required": False,
                                        "model": m.get("model")}
        if not m.get("available"):
            optional_failed.append("model_artefact")
    except Exception as exc:
        subsystems["model_artefact"] = {"status": "error", "required": False, "detail": type(exc).__name__}
        optional_failed.append("model_artefact")

    # --- export and report generation (required: a report that cannot be produced is a broken promise)
    try:
        from app.reports.builder import simple_table_pdf
        simple_table_pdf("readiness", [], [])
        subsystems["reports"] = {"status": "ok", "required": True}
    except Exception as exc:
        subsystems["reports"] = {"status": "error", "required": True, "detail": type(exc).__name__}
        required_failed.append("reports")

    # --- external connectors (optional and, in this build, deliberately unconfigured)
    try:
        from app.connectors import registry
        statuses = registry.status_all() if hasattr(registry, "status_all") else {}
        subsystems["connectors"] = {"status": "not_configured" if not statuses else "configured",
                                    "required": False, "providers": statuses or {}}
    except Exception:
        subsystems["connectors"] = {"status": "not_configured", "required": False, "providers": {}}

    if required_failed:
        status_text = "not_ready"
        response.status_code = 503
    elif optional_failed:
        status_text = "degraded"
    else:
        status_text = "ready"

    return {"status": status_text,
            # kept for callers that read the flat fields
            "database": subsystems["database"]["status"],
            "migrations": subsystems["migrations"]["status"],
            "subsystems": subsystems,
            "required_failed": required_failed,
            "optional_unavailable": optional_failed,
            "note": "degraded means investigation continues with a named subsystem unavailable; it is never reported as ready."}
