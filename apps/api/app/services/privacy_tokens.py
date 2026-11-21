"""Privacy-preserving cross-case identifier matching (keyed HMAC tokens).

Disabled unless CROSSCASE_TOKEN_KEY is configured server-side (never hard-coded). A token match means the same normalised
identifier was observed under the configured key scope; it does not prove the same human controls it, and deterministic
keyed hashing is not anonymisation (equality leakage is inherent). Reveal of raw values is role-checked and audited with a
purpose field.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Case, Entity, Role, User
from app.services import audit
from app.services.contract import finding, result
from app.services.crosscase import authorised_cases

TOKEN_VERSION = "1.0.0"
SUPPORTED = {"account", "vpa", "phone", "email"}


def status() -> dict:
    key = os.environ.get("CROSSCASE_TOKEN_KEY", "")
    return {"enabled": bool(key), "key_version": os.environ.get("CROSSCASE_TOKEN_KEY_VERSION", "v1") if key else None, "scope": "workspace", "construction": "HMAC-SHA256(key, type|normalised_identifier)",
            "limitations": ["deterministic keyed tokens leak equality; not anonymisation", "a match is identifier equality under the key scope, not identity of the human controlling it"],
            "reason": None if key else "CROSSCASE_TOKEN_KEY not configured: capability disabled by design (no hard-coded key)"}


def _norm(entity_type: str, key: str) -> str:
    k = key.strip().lower()
    if entity_type == "phone":
        k = "".join(ch for ch in k if ch.isdigit())[-10:]
    return f"{entity_type}|{k}"


def token(entity_type: str, key: str) -> str | None:
    secret = os.environ.get("CROSSCASE_TOKEN_KEY", "")
    return hmac.new(secret.encode(), _norm(entity_type, key).encode(), hashlib.sha256).hexdigest() if secret else None


def match(db: Session, user: User, case_ids: list[str]) -> dict:
    st = status()
    if not st["enabled"]:
        return result(None, "privacy_preserving_match", TOKEN_VERSION, findings=[], status="disabled", warnings=[st["reason"]], capability=st, matches=[])
    cases = authorised_cases(db, user, case_ids)
    by_token: dict[str, list[dict]] = defaultdict(list)
    for c in cases:
        for e in db.execute(select(Entity).where(Entity.case_id == c.id, Entity.entity_type.in_(sorted(SUPPORTED)))).scalars():
            by_token[token(e.entity_type, e.key)].append({"case_id": c.id, "entity_id": e.id, "entity_type": e.entity_type})
    matches = [{"token": t, "entity_type": rows[0]["entity_type"], "cases": sorted({r["case_id"] for r in rows}), "entity_ids": [r["entity_id"] for r in rows], "raw_value": None,
                "reveal": "POST /api/privacy/reveal with purpose (role-checked, audited)"} for t, rows in by_token.items() if len({r["case_id"] for r in rows}) > 1]
    matches.sort(key=lambda m: (m["entity_type"], m["token"]))
    return result(None, "privacy_preserving_match", TOKEN_VERSION, findings=[finding("token_matches", f"{len(matches)} identifier token(s) shared across permitted cases", evidence_class="derived")],
                  limitations=st["limitations"], capability=st, matches=matches, cases=[c.id for c in cases])


def reveal(db: Session, user: User, entity_id: str, purpose: str) -> dict:
    if user.role not in {Role.supervisor, Role.admin}:
        raise PermissionError("reveal requires supervisor or admin role")
    if len(purpose.strip()) < 10:
        raise ValueError("purpose/necessity statement of at least 10 characters required")
    e = db.get(Entity, entity_id)
    if e is None:
        raise LookupError("entity not found")
    case = db.get(Case, e.case_id)
    from app.core.deps import user_can_access_case
    if not user_can_access_case(db, user, case):
        raise LookupError("entity not found")
    audit.record(db, "privacy.identifier_revealed", actor_id=user.id, case_id=case.id, target_type="entity", target_id=e.id, detail={"purpose": purpose[:300], "entity_type": e.entity_type})
    return {"entity_id": e.id, "entity_type": e.entity_type, "raw_value": e.key, "case_id": case.id, "token": token(e.entity_type, e.key), "audited": True}
