from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_case_or_404, get_current_user
from app.db.session import get_db
from app.graph import engine
from app.models import (AnalystReview, Case, CounterEvidence, Entity, EvidenceItem, Relationship, RelationshipEvidence, ReviewStatus, Role, User)
from app.schemas import EdgeDetail, EvidenceItemOut, GraphEdge, GraphNode, GraphResponse, ReviewRequest
from app.services import audit

router = APIRouter(prefix="/cases/{case_id}", tags=["graph"])


def _node(e: Entity) -> GraphNode:
    return GraphNode(id=e.id, type=e.entity_type, label=e.label, attributes={**(e.attributes or {}), "key": e.key})


def _edge(r: Relationship) -> GraphEdge:
    return GraphEdge(id=r.id, source=r.source_entity_id, target=r.target_entity_id, type=r.relationship_type, evidence_level=r.evidence_level.value,
                     review_status=r.review_status.value, valid_from=r.valid_from, valid_to=r.valid_to, observed_at=r.observed_at,
                     heuristic_score=r.heuristic_score, limitations=r.limitations or [], attributes=r.attributes or {})


def _ev_out(e: EvidenceItem) -> EvidenceItemOut:
    return EvidenceItemOut(**{k: (getattr(e, k).value if k == "review_status" else getattr(e, k)) for k in EvidenceItemOut.model_fields})


@router.get("/graph", response_model=GraphResponse)
def get_graph(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db), entity_types: str | None = None, levels: str | None = None,
              review: str | None = None, date_from: datetime | None = None, date_to: datetime | None = None, evidence_backed_only: bool = False):
    g = engine.load_graph(db, case, entity_types=set(entity_types.split(",")) if entity_types else None, levels=set(levels.split(",")) if levels else None,
                          review=set(review.split(",")) if review else None, date_from=date_from, date_to=date_to)
    payload = engine.graph_payload(g)
    if evidence_backed_only:
        payload["edges"] = [e for e in payload["edges"] if e["evidence_level"] in {"directly_observed", "corroborated", "derived"}]
        keep = {e["source"] for e in payload["edges"]} | {e["target"] for e in payload["edges"]}
        payload["nodes"] = [n for n in payload["nodes"] if n["id"] in keep]
    return payload


@router.get("/entities/{entity_id}")
def entity_360(entity_id: str, case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    e = db.get(Entity, entity_id)
    if e is None or e.case_id != case.id:
        raise HTTPException(404, "Entity not found")
    rels = db.execute(select(Relationship).where(Relationship.case_id == case.id, (Relationship.source_entity_id == e.id) | (Relationship.target_entity_id == e.id))).scalars().all()
    feats = engine.account_features(db, case).get(e.key) if e.entity_type == "account" else None
    return {"entity": _node(e), "edges": [_edge(r) for r in rels], "features": feats, "triage": engine.rules_triage(feats) if feats else None,
            "first_seen": e.first_seen, "last_seen": e.last_seen}


@router.get("/edges/{edge_id}", response_model=EdgeDetail)
def edge_detail(edge_id: str, case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    r = db.get(Relationship, edge_id)
    if r is None or r.case_id != case.id:
        raise HTTPException(404, "Edge not found")
    ev_ids = [x.evidence_item_id for x in db.execute(select(RelationshipEvidence).where(RelationshipEvidence.relationship_id == r.id)).scalars()]
    evs = db.execute(select(EvidenceItem).where(EvidenceItem.id.in_(ev_ids))).scalars().all() if ev_ids else []
    counters = db.execute(select(CounterEvidence).where(CounterEvidence.relationship_id == r.id)).scalars().all()
    reviews = db.execute(select(AnalystReview).where(AnalystReview.relationship_id == r.id).order_by(AnalystReview.created_at)).scalars().all()
    return EdgeDetail(edge=_edge(r), source_entity=_node(db.get(Entity, r.source_entity_id)), target_entity=_node(db.get(Entity, r.target_entity_id)),
                      method={"name": r.method_name, "version": r.method_version, "score_semantics": "heuristic ranking score 0-100; not a calibrated probability",
                              "limitations": r.limitations or []},
                      supporting_evidence=[_ev_out(e) for e in evs],
                      counter_evidence=[{"id": c.id, "kind": c.kind, "severity": c.severity, "description": c.description, "evidence_item_id": c.evidence_item_id} for c in counters],
                      reviews=[{"id": x.id, "reviewer_id": x.reviewer_id, "decision": x.decision.value, "reason": x.reason, "created_at": x.created_at} for x in reviews])


@router.post("/edges/{edge_id}/review")
def review_edge(edge_id: str, body: ReviewRequest, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.get(Relationship, edge_id)
    if r is None or r.case_id != case.id:
        raise HTTPException(404, "Edge not found")
    if body.decision == "supported" and r.evidence_level.value in {"candidate", "stale", "contradicted"} and user.role not in {Role.supervisor, Role.admin}:
        raise HTTPException(403, "Promoting a candidate/stale/contradicted relationship requires supervisor review")
    rv = AnalystReview(case_id=case.id, relationship_id=r.id, reviewer_id=user.id, decision=ReviewStatus(body.decision), reason=body.reason)
    db.add(rv)
    r.review_status = ReviewStatus(body.decision)
    audit.record(db, "edge.reviewed", actor_id=user.id, case_id=case.id, target_type="relationship", target_id=r.id, detail={"decision": body.decision, "reason": body.reason})
    db.commit()
    return {"ok": True, "review_status": r.review_status.value}


@router.get("/evidence/{evidence_id}", response_model=EvidenceItemOut)
def evidence_item(evidence_id: str, case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    e = db.get(EvidenceItem, evidence_id)
    if e is None or e.case_id != case.id:
        raise HTTPException(404, "Evidence not found")
    return _ev_out(e)
