"""Cross-case and workspace-level intelligence endpoints: campaign DNA, privacy-preserving matching, prevention-rule compiler."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import CandidateRule, Role, User
from app.services import audit, campaign, privacy_tokens, rulecompiler

router = APIRouter(tags=["intel-global"])


class CaseIds(BaseModel):
    case_ids: list[str] = Field(min_length=2, max_length=12)


@router.post("/campaign/compare")
def campaign_compare(body: CaseIds, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    res = campaign.compare_cases(db, user, body.case_ids)
    if not res["cases"]:
        raise HTTPException(404, "One or more cases not found")
    audit.record(db, "campaign.compared", actor_id=user.id, detail={"case_ids": body.case_ids})
    db.commit()
    return res


@router.get("/campaign/fingerprint/{case_id}")
def campaign_fingerprint(case_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.core.deps import get_case_or_404
    case = get_case_or_404(case_id, user, db)
    return campaign.fingerprint(db, case)


@router.get("/privacy/status")
def privacy_status(_: User = Depends(get_current_user)):
    return privacy_tokens.status()


@router.post("/privacy/match")
def privacy_match(body: CaseIds, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return privacy_tokens.match(db, user, body.case_ids)


class RevealIn(BaseModel):
    entity_id: str
    purpose: str = Field(min_length=10, max_length=500)


@router.post("/privacy/reveal")
def privacy_reveal(body: RevealIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        out = privacy_tokens.reveal(db, user, body.entity_id, body.purpose)
    except PermissionError as exc:
        raise HTTPException(403, str(exc))
    except LookupError:
        raise HTTPException(404, "entity not found")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    db.commit()
    return out


class RuleIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    typology: str = Field(min_length=3, max_length=60)
    conditions: list[dict] | None = None
    source_hypothesis_id: str | None = None
    seeds: list[int] = Field(default=[9001, 9002, 9003], max_length=12)


class RuleDecision(BaseModel):
    decision: Literal["approved", "rejected", "expired"]
    reason: str = Field(min_length=5, max_length=2000)


@router.get("/rules")
def list_rules(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(CandidateRule).order_by(CandidateRule.created_at.desc()).limit(100)).scalars().all()
    return {"rules": [rulecompiler.rule_out(r) for r in rows], "typologies": rulecompiler.TYPOLOGIES, "features": rulecompiler.FEATURES}


@router.post("/rules/compile", status_code=201)
def compile_rule(body: RuleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == Role.demo_analyst and len(body.seeds) > 4:
        body.seeds = body.seeds[:4]
    try:
        rule = rulecompiler.compile_rule(db, user, name=body.name, typology=body.typology, conditions=body.conditions, source_hypothesis_id=body.source_hypothesis_id, seeds=body.seeds)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    db.commit()
    return rulecompiler.rule_out(rule)


@router.post("/rules/{rule_id}/decision")
def decide_rule(rule_id: str, body: RuleDecision, user: User = Depends(require_roles(Role.supervisor, Role.admin)), db: Session = Depends(get_db)):
    rule = db.get(CandidateRule, rule_id)
    if rule is None:
        raise HTTPException(404, "rule not found")
    rule.approval_status = body.decision
    rule.approved_by = user.id if body.decision == "approved" else rule.approved_by
    audit.record(db, "candidate_rule.decision", actor_id=user.id, target_type="candidate_rule", target_id=rule.id, detail={"decision": body.decision, "reason": body.reason[:300]})
    db.commit()
    return rulecompiler.rule_out(rule)
