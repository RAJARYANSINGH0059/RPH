from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import Base, SessionLocal, engine
from app.models import Role, User
from app.routers import auth, cases, claims, connectors, cooperation, crosscase, graph, health, intel, intel_global, reports, synthetic

log = logging.getLogger("ps05x")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def ensure_demo_users() -> None:
    """Create demo accounts from environment variables. Passwords are never defaulted; if unset, no account is created."""
    s = get_settings()
    specs = [(s.demo_analyst_email, s.demo_analyst_password, "Demo Analyst", Role.analyst),
             (s.demo_supervisor_email, s.demo_supervisor_password, "Demo Supervisor", Role.supervisor),
             (s.demo_admin_email, s.demo_admin_password, "Demo Admin", Role.admin)]
    with SessionLocal() as db:
        for email, pw, name, role in specs:
            if not pw:
                continue
            existing = db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()
            if existing is None:
                db.add(User(email=email.lower(), display_name=name, password_hash=hash_password(pw), role=role))
                log.info("created demo user %s (%s)", email, role.value)
        db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.is_sqlite:
        # local development convenience; production uses `alembic upgrade head` as the release command
        Base.metadata.create_all(bind=engine)
    try:
        ensure_demo_users()
    except Exception as exc:  # DB may not be migrated yet on first boot
        log.warning("demo user bootstrap skipped: %s", type(exc).__name__)
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title=s.app_name, version=s.app_version, lifespan=lifespan,
                  description="Evidence-centred financial-cybercrime investigation workbench (PS05-X). Investigative aid; human verification required.")
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origin_list, allow_origin_regex=s.cors_origin_regex or None,
                       allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
    for r in (health.router, auth.router, cases.router, graph.router, synthetic.router, connectors.router, reports.router, crosscase.router, claims.router, cooperation.router, intel.router, intel_global.router):
        app.include_router(r, prefix="/api")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal error. The event has been logged without request contents."})

    @app.get("/")
    def root():
        return {"service": s.app_name, "docs": "/docs", "health": "/api/health/live", "mode": "NO LIVE POLICE/BANK CONNECTION"}

    return app


app = create_app()
