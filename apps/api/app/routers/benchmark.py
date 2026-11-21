"""Read-only benchmark artefacts (results JSON shipped in the repo) and the model card metrics; plus the caller's own audit trail."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import API_ROOT
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import AuditEvent, User

router = APIRouter(tags=["benchmark"])
REPO = API_ROOT.parents[1]


def _load(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except Exception:
        return None


def _commit() -> str | None:
    c = os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_COMMIT")
    if c:
        return c[:12]
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=str(REPO), timeout=3).stdout.strip() or None
    except Exception:
        return None


@router.get("/benchmark/results")
def benchmark_results(_: User = Depends(get_current_user)):
    res = REPO / "tests" / "benchmark" / "results"
    out = {"smoke": _load(res / "benchmark_summary.json"), "heldout": _load(res / "heldout_summary.json"), "v2": _load(res / "benchmark_v2_summary.json"), "commit": _commit(),
           "note": "Synthetic benchmark artefacts committed with the repository; regenerate with tests/benchmark/run_benchmark.py."}
    for k in ("smoke", "heldout"):
        if out[k] and "rows" in out[k]:
            out[k] = {**out[k], "rows": f"{len(out[k]['rows'])} per-case rows omitted here (see repository JSON)"}
    return out


@router.get("/benchmark/model-card")
def model_card(_: User = Depends(get_current_user)):
    return {"metrics": _load(REPO / "ml" / "evaluation" / "metrics.json"), "feature_schema": _load(REPO / "ml" / "artifacts" / "feature_schema.json"),
            "card": "docs/MODEL_CARD.md", "scope": "triage cue only; synthetic-only training and evaluation; not a probability of guilt"}


@router.get("/audit/mine")
def my_audit(user: User = Depends(get_current_user), db: Session = Depends(get_db), limit: int = 150):
    rows = db.execute(select(AuditEvent).where(AuditEvent.actor_id == user.id).order_by(AuditEvent.created_at.desc()).limit(max(1, min(limit, 500)))).scalars().all()
    return [{"id": a.id, "action": a.action, "case_id": a.case_id, "target_type": a.target_type, "target_id": a.target_id, "detail": a.detail, "created_at": a.created_at} for a in rows]
