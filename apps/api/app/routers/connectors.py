from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors import adapters
from app.connectors.adapters import get_registry
from app.core.deps import get_case_or_404, get_current_user, require_roles
from app.db.session import get_db
from app.graph.rules import rebuild_derived
from app.models import Case, Entity, EvidenceItem, Role, User
from app.parsers import indicators
from app.schemas import ConnectorStatus
from app.services import audit, infra_graph
from app.services.ingestion import get_or_create_entity

router = APIRouter(prefix="/connectors", tags=["connectors"])


@router.get("/status", response_model=list[ConnectorStatus])
def status(_: User = Depends(get_current_user)):
    out = []
    for name, c in get_registry().items():
        h = c.status()
        out.append(ConnectorStatus(name=name, status=h.status, provider=c.provider, detail=h.detail, last_checked=h.checked_at))
    return out


@router.post("/healthcheck", response_model=list[ConnectorStatus])
def healthcheck(_: User = Depends(require_roles(Role.admin, Role.supervisor))):
    out = []
    for name, c in get_registry().items():
        h = c.healthcheck()
        out.append(ConnectorStatus(name=name, status=h.status, provider=c.provider, detail=h.detail, last_checked=h.checked_at))
    return out


@router.post("/cases/{case_id}/enrich")
def enrich(case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Run configured connectors against the case's domains/IPs. Results are CURRENT observations, labelled as such.
    Synthetic .test domains are never looked up. Failure of a connector never fails the request."""
    ents = db.execute(select(Entity).where(Entity.case_id == case.id, Entity.entity_type.in_(["domain", "ip"]))).scalars().all()
    inds = [(e.entity_type, e.key) for e in ents if not adapters.is_reserved_name(e.key)]
    summary = {}
    for name, c in get_registry().items():
        if name == "synthetic_mock" or not c.enabled():
            summary[name] = "skipped_not_configured"
            continue
        obs = c.fetch(inds)
        edges = 0
        for o in obs:
            ev = EvidenceItem(case_id=case.id, source_type="connector", source_locator={"provider": o.provider, "url": o.source_url},
                              raw_value=str(o.fields), normalised_value={"type": o.obs_type, **o.fields}, extraction_method=f"connector_{name}",
                              parser_name=f"connector_{name}", parser_version="0.1.0", observed_at=o.observed_at, event_time_start=o.observed_at,
                              time_precision="second", source_timezone="UTC", quality_flags=o.limitations)
            db.add(ev)
            db.flush()
            # Each record type becomes the relationship it actually means, or none at all. An observation with no
            # relationship to express - a record type that returned nothing, an address classification, a
            # threat-intelligence hit - is still stored as evidence above.
            edges += len(infra_graph.record(db, case, o.obs_type, o.fields, evidence_ids=[ev.id],
                                            observed_at=o.observed_at, provider=o.provider, limitations=o.limitations))
            if o.obs_type == "network_classification" and o.fields.get("ip"):
                get_or_create_entity(db, case.id, "ip", o.fields["ip"], None,
                                     {"classification": indicators.ip_classification(o.fields["ip"]),
                                      "network_classification": o.fields.get("classification"),
                                      "tor_exit_node": o.fields.get("tor_exit_node"),
                                      "network_classification_read_at": o.fields.get("list_read_at")}, o.observed_at)
        summary[name] = f"{len(obs)} observations, {edges} relationships"
    audit.record(db, "connectors.enrich", actor_id=user.id, case_id=case.id, detail=summary)
    rebuild_derived(db, case)
    db.commit()
    return {"summary": summary, "note": "Connector results are current-time observations and are labelled as such; they are not historical evidence."}
