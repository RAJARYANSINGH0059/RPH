"""Standard analytical response contract shared by the digital-twin services (blueprint §2.4)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.models import Case


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def result(case: Case | None, analysis_type: str, version: str, *, findings: list[dict], status: str = "completed",
           input_evidence_ids: list[str] | None = None, uncertainties: list | None = None, counter_evidence: list | None = None,
           limitations: list | None = None, warnings: list | None = None, human_review_required: bool = True,
           provenance: list | None = None, **extra) -> dict:
    body = {"analysis_type": analysis_type, "algorithm_version": version, "status": status, "generated_at": _now(),
            "case_id": case.id if case else None, "synthetic": bool(case.is_synthetic) if case else None,
            "input_evidence_ids": sorted(set(input_evidence_ids or [])), "findings": findings,
            "uncertainties": uncertainties or [], "counter_evidence": counter_evidence or [], "limitations": limitations or [],
            "warnings": warnings or [], "human_review_required": human_review_required, "provenance": provenance or []}
    body.update(extra)
    digest = hashlib.sha256(json.dumps({k: v for k, v in body.items() if k != "generated_at"}, sort_keys=True, default=str).encode()).hexdigest()
    body["result_id"] = f"{analysis_type}:{digest[:20]}"
    return body


def finding(kind: str, statement: str, *, evidence_class: str, evidence_refs: list[str] | None = None, **attrs) -> dict:
    """evidence_class: observed|reported|extracted|corroborated|derived|candidate|model_suggestion|contradicted|stale|unresolved"""
    return {"kind": kind, "statement": statement, "evidence_class": evidence_class, "evidence_refs": evidence_refs or [], **attrs}
