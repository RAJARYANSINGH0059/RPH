"""Role-sensitive account and human-context review.

Separates what the records show about an ACCOUNT from propositions about the HUMAN associated with it. Nine propositions
are tracked independently; none is a legal finding. There is no guilt/victim score and no protected attribute is an input.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import Case, EvidenceItem, InvestigationEvent, RoleReview, Transaction, User
from app.services import audit
from app.services.contract import finding, result

ROLE_VERSION = "1.0.0"
PROPOSITIONS = [
    {"key": "P1", "label": "The account received the transaction(s)", "auto": True},
    {"key": "P2", "label": "A named individual is recorded as the account holder", "auto": False},
    {"key": "P3", "label": "The named individual operated the account at the relevant time", "auto": False},
    {"key": "P4", "label": "Another person controlled or accessed the account", "auto": False},
    {"key": "P5", "label": "The named individual understood the transaction's purpose", "auto": False},
    {"key": "P6", "label": "The named individual knowingly assisted the operation", "auto": False},
    {"key": "P7", "label": "Indicators that the individual may have been deceived, recruited, coerced or trafficked (trained human review only)", "auto": False},
    {"key": "P8", "label": "The account or identity may have been compromised", "auto": False},
    {"key": "P9", "label": "Available information is insufficient or conflicting", "auto": False},
]
PROP_STATUSES = ["unassessed", "supported", "contradicted", "conflicting", "insufficient"]
REVIEW_STATUSES = ["UNASSESSED", "REVIEW_REQUIRED", "CONFLICTING_EVIDENCE", "INDETERMINATE", "HUMAN_REVIEWED"]
# Account-control role dimensions (Next-Wave §7 / §3): each claim is source-linked and dated; roles may belong to different people.
ROLE_DIMENSIONS = ["registered_holder", "kyc_supplier", "possessor_card_passbook_device", "credential_device_controller", "transaction_initiator", "recruiter_intermediary",
                   "cash_out_actor", "beneficiary", "suspected_organiser_controller", "unknown_disputed"]
CLAIM_STATES = ["direct", "corroborated", "derived", "alleged", "unresolved", "contradicted"]
HYPOTHESES = ["possible knowing provision", "possible recruited/deceived intermediary", "possible coercion/trafficking indicators requiring trained review",
              "possible account/device compromise", "possible legitimate third-party activity", "unresolved"]
PROHIBITED_INPUTS = ["poverty", "caste", "religion", "ethnicity", "sex", "gender", "age", "disability", "nationality", "geography", "model score", "centrality"]
QUESTIONS = ["Who is the recorded account holder (bank KYC record, lawfully obtained)?", "Were there logins/device sessions at the relevant times, and from where (authorised records only)?",
             "Is there any communication showing instructions received, commission paid or account handover?", "Did the holder report the account lost, compromised or opened in their name?",
             "Is there lawfully obtained evidence of a job offer, travel, document retention, threats or restriction of movement?", "Does the holder have an independent explanation for the credits and debits?"]


def account_facts(db: Session, case: Case, account_ref: str) -> dict:
    alias = engine.alias_map(db, case)
    canon = alias.get(account_ref, account_ref)
    feats = engine.account_features(db, case).get(canon) or {}
    txs = db.execute(select(Transaction).where(Transaction.case_id == case.id)).scalars().all()
    inbound = [t for t in txs if (t.direction == "credit" and alias.get(t.account_ref, t.account_ref) == canon) or (t.direction == "debit" and t.counterparty_ref and alias.get(t.counterparty_ref, t.counterparty_ref) == canon)]
    outbound = [t for t in txs if (t.direction == "debit" and alias.get(t.account_ref, t.account_ref) == canon) or (t.direction == "credit" and t.counterparty_ref and alias.get(t.counterparty_ref, t.counterparty_ref) == canon)]
    names = sorted({t.counterparty_name_raw for t in txs if t.counterparty_name_raw and t.counterparty_ref and alias.get(t.counterparty_ref, t.counterparty_ref) == canon})
    return {"account_ref": account_ref, "canonical": canon, "aliases": sorted(k for k, v in alias.items() if v == canon and k != canon), "own_statement_supplied": feats.get("has_own_statement", False),
            "credits_observed": len(inbound), "debits_observed": len(outbound), "total_in_minor": feats.get("total_in_minor", 0), "total_out_minor": feats.get("total_out_minor", 0),
            "names_shown_by_counterparties": names, "evidence_ids": sorted({t.evidence_item_id for t in inbound + outbound})[:50],
            "note": "These are facts about the account's records. They say nothing by themselves about who operated it or what they knew."}


def default_propositions(facts: dict) -> dict:
    props = {}
    for p in PROPOSITIONS:
        props[p["key"]] = {"status": "unassessed", "supports": [], "contradicts": [], "notes": ""}
    if facts["credits_observed"]:
        props["P1"] = {"status": "supported", "supports": facts["evidence_ids"][:20], "contradicts": [], "notes": "Credits recorded in supplied statements (automatic, record-level fact)."}
    if facts["names_shown_by_counterparties"]:
        props["P2"] = {"status": "insufficient", "supports": [], "contradicts": [], "notes": "A payee name shown in another party's statement is not a KYC record. Bank-supplied holder record needed."}
    return props


def derive_status(props: dict, reviewer_id: str | None) -> str:
    statuses = {v.get("status") for k, v in props.items() if k != "P1"}
    if reviewer_id:
        return "HUMAN_REVIEWED"
    if "conflicting" in statuses or any(v.get("supports") and v.get("contradicts") for v in props.values()):
        return "CONFLICTING_EVIDENCE"
    if statuses <= {"unassessed"}:
        return "UNASSESSED"
    if statuses <= {"unassessed", "insufficient"}:
        return "INDETERMINATE"
    return "REVIEW_REQUIRED"


def validate_update(props: dict, db: Session, case: Case) -> list[str]:
    """Guardrails: unknown keys, bad statuses, evidence ids outside the case, and 'supported' without evidence for human propositions."""
    errors = []
    keys = {p["key"] for p in PROPOSITIONS}
    ev_ids = {e for (e,) in db.execute(select(EvidenceItem.id).where(EvidenceItem.case_id == case.id)).all()}
    for k, v in props.items():
        if k not in keys:
            errors.append(f"unknown proposition {k}")
            continue
        if v.get("status") not in PROP_STATUSES:
            errors.append(f"{k}: status must be one of {PROP_STATUSES}")
        for side in ("supports", "contradicts"):
            for e in v.get(side) or []:
                if e not in ev_ids:
                    errors.append(f"{k}: evidence {e} is not in this case")
        if k in {"P3", "P4", "P5", "P6", "P7", "P8"} and v.get("status") == "supported" and not v.get("supports"):
            errors.append(f"{k}: 'supported' requires at least one supporting evidence item; account presence alone is not evidence of {k}")
        low = (v.get("notes") or "").lower()
        hits = [w for w in PROHIBITED_INPUTS if f"because of {w}" in low or f"due to {w}" in low or f"based on {w}" in low]
        if hits:
            errors.append(f"{k}: notes appear to infer from a prohibited attribute ({', '.join(hits)})")
    return errors


def get_or_create(db: Session, case: Case, user: User, account_ref: str) -> RoleReview:
    rr = db.execute(select(RoleReview).where(RoleReview.case_id == case.id, RoleReview.account_ref == account_ref)).scalar_one_or_none()
    if rr is None:
        facts = account_facts(db, case, account_ref)
        props = default_propositions(facts)
        rr = RoleReview(case_id=case.id, account_ref=account_ref, propositions=props, status=derive_status(props, None), open_questions=QUESTIONS, created_by=user.id,
                        history=[{"at": datetime.now(timezone.utc).isoformat(), "by": user.id, "change": "created with record-level facts only"}])
        db.add(rr)
        db.flush()
        audit.record(db, "role_review.created", actor_id=user.id, case_id=case.id, target_type="role_review", target_id=rr.id, detail={"account": account_ref})
    return rr


def review_out(db: Session, case: Case, rr: RoleReview) -> dict:
    return {"id": rr.id, "account_ref": rr.account_ref, "status": rr.status, "propositions": [{**p, **(rr.propositions or {}).get(p["key"], {})} for p in PROPOSITIONS],
            "hypotheses_non_exclusive": HYPOTHESES, "open_questions": rr.open_questions or [], "reviewer_id": rr.reviewer_id, "reviewer_rationale": rr.reviewer_rationale,
            "history": rr.history or [], "facts": account_facts(db, case, rr.account_ref), "prohibited_inputs": PROHIBITED_INPUTS, "statuses": REVIEW_STATUSES,
            "version": ROLE_VERSION, "disclaimer": "No proposition here is a legal finding. No person is labelled criminal, innocent, trafficked or coerced by the system."}


# ------------------------------------------------------------------ account control timeline (role claims)

def add_role_claim(db: Session, case: Case, user: User, *, account_ref: str, role_dimension: str, actor_label: str, claim_state: str, description: str,
                   event_time: datetime | None = None, time_precision: str = "unknown", source_evidence_item_id: str | None = None, counter_evidence: str = "") -> InvestigationEvent:
    if role_dimension not in ROLE_DIMENSIONS:
        raise ValueError(f"role_dimension must be one of {ROLE_DIMENSIONS}")
    if claim_state not in CLAIM_STATES:
        raise ValueError(f"claim_state must be one of {CLAIM_STATES}")
    if claim_state in {"direct", "corroborated"} and not source_evidence_item_id:
        raise ValueError("a direct/corroborated role claim requires a source evidence item; otherwise record it as alleged or unresolved")
    if source_evidence_item_id:
        ev = db.get(EvidenceItem, source_evidence_item_id)
        if ev is None or ev.case_id != case.id:
            raise ValueError("source evidence item not in this case")
    ie = InvestigationEvent(case_id=case.id, event_type="ACCOUNT_ROLE_CLAIM", layer="account_control", evidence_class={"direct": "directly_observed", "corroborated": "corroborated", "derived": "derived", "alleged": "reported", "unresolved": "unresolved", "contradicted": "contradicted"}[claim_state],
                            event_time=event_time, time_precision=time_precision, observed_at=datetime.now(timezone.utc), reported_by=user.display_name, reported_at=datetime.now(timezone.utc),
                            description=description, source_evidence_item_id=source_evidence_item_id,
                            attributes={"account_ref": account_ref, "role_dimension": role_dimension, "actor_label": actor_label, "claim_state": claim_state, "counter_evidence": counter_evidence}, created_by=user.id)
    db.add(ie)
    db.flush()
    audit.record(db, "role_claim.added", actor_id=user.id, case_id=case.id, target_type="investigation_event", target_id=ie.id, detail={"account": account_ref, "role": role_dimension, "state": claim_state})
    return ie


def control_timeline(db: Session, case: Case, account_ref: str) -> dict:
    """Dated, source-linked role claims per dimension, with gaps and contradictions. Registered holder and transaction controller may differ."""
    facts = account_facts(db, case, account_ref)
    claims = db.execute(select(InvestigationEvent).where(InvestigationEvent.case_id == case.id, InvestigationEvent.event_type == "ACCOUNT_ROLE_CLAIM")).scalars().all()
    claims = [c for c in claims if (c.attributes or {}).get("account_ref") in {account_ref, facts["canonical"]} | set(facts["aliases"])]
    lanes = {d: [] for d in ROLE_DIMENSIONS}
    for c in sorted(claims, key=lambda c: (c.event_time is None, c.event_time or datetime.min.replace(tzinfo=timezone.utc), c.created_at)):
        a = c.attributes or {}
        lanes[a.get("role_dimension", "unknown_disputed")].append({"id": c.id, "actor_label": a.get("actor_label"), "claim_state": a.get("claim_state"), "evidence_class": c.evidence_class, "description": c.description,
                                                                   "event_time": c.event_time.isoformat() if c.event_time else None, "time_precision": c.time_precision, "source_evidence_item_id": c.source_evidence_item_id,
                                                                   "counter_evidence": a.get("counter_evidence") or None, "recorded_by": c.reported_by, "recorded_at": c.created_at.isoformat()})
    # transaction initiation events from the records themselves: the record shows a debit happened; who initiated it is unknown unless a claim says so
    txs = db.execute(select(Transaction).where(Transaction.case_id == case.id, Transaction.direction == "debit")).scalars().all()
    alias = engine.alias_map(db, case)
    for t in txs:
        if alias.get(t.account_ref, t.account_ref) == facts["canonical"] and t.amount_minor:
            lanes["transaction_initiator"].append({"id": f"tx:{t.id}", "actor_label": "UNKNOWN (record shows the debit; the initiator is not recorded)", "claim_state": "unresolved", "evidence_class": "directly_observed_debit_initiator_unknown",
                                                   "description": f"debit ₹{t.amount_minor / 100:,.2f} → {t.counterparty_ref or '?'} ref {t.external_reference or '-'}", "event_time": t.datetime_utc.isoformat() if t.datetime_utc else None,
                                                   "time_precision": t.time_precision, "source_evidence_item_id": t.evidence_item_id, "counter_evidence": None, "recorded_by": "statement", "recorded_at": None})
    holders = {c["actor_label"] for c in lanes["registered_holder"] if c["claim_state"] in {"direct", "corroborated"}}
    controllers = {c["actor_label"] for c in lanes["credential_device_controller"] + lanes["transaction_initiator"] if c["claim_state"] in {"direct", "corroborated", "alleged"} and not str(c["actor_label"]).startswith("UNKNOWN")}
    contradictions = []
    for d, items in lanes.items():
        actors = {i["actor_label"] for i in items if i["claim_state"] in {"direct", "corroborated"}}
        if len(actors) > 1:
            contradictions.append({"dimension": d, "detail": f"different actors asserted with direct/corroborated evidence: {sorted(actors)}"})
    gaps = [d for d, items in lanes.items() if not items]
    return result(case, "account_control_timeline", ROLE_VERSION, findings=[finding("control", f"{account_ref}: {sum(len(v) for v in lanes.values())} role claim(s); holder {sorted(holders) or 'unknown'}; controller {sorted(controllers) or 'unknown'}", evidence_class="derived")],
                  counter_evidence=contradictions, uncertainties=[f"no evidence for dimension {d}" for d in gaps],
                  limitations=["Evidence of possession or control does not establish knowledge or intent.", "Registered holder, controller, initiator, recruiter, cash-out actor and beneficiary may be different people; they are never collapsed.",
                               "A debit record shows that a transaction happened; the initiator is unknown unless a source-linked claim says otherwise."],
                  account=facts, lanes=lanes, dimensions=ROLE_DIMENSIONS, claim_states=CLAIM_STATES, holder_differs_from_controller=bool(holders and controllers and not (holders & controllers)), gaps=gaps)
