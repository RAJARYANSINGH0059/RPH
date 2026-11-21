from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings = get_settings()
    kwargs: dict = {"pool_pre_ping": True}
    if settings.is_sqlite:
        # local development / tests only (production is PostgreSQL): WAL + a generous busy timeout so concurrent dashboard
        # reads never fail a long synthetic-case write with "database is locked"
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(settings.sqlalchemy_url, **kwargs)
    if settings.is_sqlite:
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record):  # pragma: no cover
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
            dbapi_conn.execute("PRAGMA busy_timeout=30000")
            try:
                dbapi_conn.execute("PRAGMA journal_mode=WAL")
            except Exception:
                pass
    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
