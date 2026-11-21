"""Evidence Adversary: adversarial testing of a proposed relationship (attribution challenge).

For a relationship edge: typed claim, type-specific alternative hypotheses, supporting / contradicting / missing evidence,
temporal compatibility and source reliability kept separate, a challenge state, and an Attribution Challenge Report.
Investigator actions (accept, reject, retain as candidate, add competing hypothesis, record dissent) go through the
existing review + hypothesis tables and the audit log; nothing is rewritten.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AnalystReview, Case, CounterEvidence, Entity, EvidenceItem, Hypothesis, Relationship, RelationshipEvidence, SourceFile, Transaction
from app.services.contract import finding, result

ADVERSARY_VERSION = "1.0.0"
STATES = ["supported", "corroborated", "contested", "candidate", "contradicted", "unresolved", "stale"]
ALTERNATIVES = {
    "SHARED_INFRASTRUCTURE": [("Shared commercial hosting / CDN", "Unrelated sites commonly share an IP; multi-tenant hosting is the default explanation.", "Hosting customer records; an identifier bridge (payment VPA, account, phone, email) between the domains."),
                              ("Reverse proxy / CDN edge", "A proxy or CDN address fronts many unrelated origins.", "Origin-server records from the provider."),
                              ("Same provider, different customers", "Matching ASN/provider indicates a common provider, not a common controller.", "Provider account records per domain."),
                              ("IP reassigned between observations", "The address may have served one site earlier and another later.", "Dated passive-DNS observations covering both periods.")],
    "RESOLVES_TO": [("Current lookup, not historical", "A present-day resolution may not reflect the mapping at the time of the events.", "Historical DNS observation dated within the transaction window."),
                    ("CDN edge address", "A CDN address fronts many domains.", "Origin-server records from the CDN provider.")],
    "HOSTED_ON": [("Shared provider", "Hosting on a provider is use of a service, not control of it.", "Provider customer and payment records.")],
    "SIMILAR_NAME": [("Different people with similar names", "Name similarity is common; identifiers differ.", "An independent identifier bridge (same account, phone, email)."),
                     ("Transliteration / OCR variant of one name", "Spelling variants arise from transliteration or OCR errors.", "The original document image and bank KYC name.")],
    "SAME_IDENTIFIER": [("Victim copied the identifier from the scam page", "Shows the payment was made as instructed, not who controls the account.", "Account holder/control records."),
                        ("Recycled or re-assigned identifier", "VPAs and numbers can be re-assigned over time.", "Provider assignment history for the identifier.")],
    "SAME_ACCOUNT_IDENTIFIER": [("Coincidental reference + amount", "Two different transfers sharing a reference and amount would be an error; check with the bank.", "Bank confirmation of the UTR.")],
    "TRANSFERRED_TO": [("Legitimate payment unrelated to the fraud", "A debit from a mule-pattern account may be rent, salary or a refund.", "Narration, counterparty records and timing relative to the victim credit."),
                       ("Duplicate statement row", "Two rows may describe one transfer.", "Reference uniqueness and bank confirmation."),
                       ("Reversed or failed transaction", "Statements can show reversals that cancel a transfer.", "Subsequent credit with the same reference."),
                       ("Account holder is not the initiator", "The person who initiated the transfer may differ from the registered holder (recruited, deceived or compromised account).", "Channel/session/device records for the transaction (authorised request).")],
    "MENTIONS": [("Mention is not involvement", "A document naming an identifier does not make its holder a participant.", "Transaction records linking the identifier to the money trail.")],
    "PAYMENT_INSTRUCTION_MATCHES_TRANSACTION": [("Instruction and payment coincide without control", "A match shows the victim paid where instructed; it does not show who operates the payee account or runs the website.", "Account-control and website-ownership records.")],
    "INSTRUCTS_PAYMENT_TO": [("Payee named without consent", "A QR/UPI payee can be any account whose VPA the fraudster knows.", "Account holder statement and control records.")],
    "COMMON_OPERATOR": [("Not a safe inference", "Shared infrastructure never establishes a common operator.", "Independent identifier bridge.")],
}
RELIABILITY = {"bank_statement": ("bank digital export supplied by the user", "medium-high: machine-readable rows; authenticity not independently verified"),
               "complaint": ("complainant document", "reported: single-party account, may contain errors"), "document": ("investigator-provided document", "medium: depends on origin"),
               "technical_observation": ("technical report / fixture", "depends on the named source; current lookups are not historical"),
               "connector": ("live connector", "current-only observation"), "payment_instruction": ("decoded payload", "high for the payload bytes; says nothing about intent")}


def _ev_summary(e: EvidenceItem, files: dict) -> dict:
    f = files.get(e.source_file_id)
    return {"evidence_id": e.id, "source_type": e.source_type, "file": f.original_name if f else None, "sha256": f.sha256 if f else None, "locator": e.source_locator,
            "method": e.extraction_method, "observed_at": e.observed_at.isoformat() if e.observed_at else None, "event_time": e.event_time_start.isoformat() if e.event_time_start else None,
            "time_precision": e.time_precision, "timezone": e.source_timezone, "quality_flags": e.quality_flags or [], "reliability": RELIABILITY.get(e.source_type, ("unknown source", "unknown"))}


def challenge(db: Session, case: Case, rel: Relationship) -> dict:
    files = {f.id: f for f in db.execute(select(SourceFile).where(SourceFile.case_id == case.id)).scalars()}
    ev_ids = [x.evidence_item_id for x in db.execute(select(RelationshipEvidence).where(RelationshipEvidence.relationship_id == rel.id)).scalars()]
    evs = db.execute(select(EvidenceItem).where(EvidenceItem.id.in_(ev_ids))).scalars().all() if ev_ids else []
    counters = db.execute(select(CounterEvidence).where(CounterEvidence.relationship_id == rel.id)).scalars().all()
    reviews = db.execute(select(AnalystReview).where(AnalystReview.relationship_id == rel.id).order_by(AnalystReview.created_at)).scalars().all()
    competing = [h for h in db.execute(select(Hypothesis).where(Hypothesis.case_id == case.id)).scalars() if rel.id in ((h.subject_refs or {}).get("relationship_ids") or [])]
    src, tgt = db.get(Entity, rel.source_entity_id), db.get(Entity, rel.target_entity_id)
    supporting = [_ev_summary(e, files) for e in evs]
    source_types = {e.source_type for e in evs}
    txs = db.execute(select(Transaction).where(Transaction.case_id == case.id, Transaction.datetime_utc.is_not(None))).scalars().all()
    window = (min(t.datetime_utc for t in txs), max(t.datetime_utc for t in txs)) if txs else None
    temporal = {"observed_at": rel.observed_at.isoformat() if rel.observed_at else None, "valid_from": rel.valid_from.isoformat() if rel.valid_from else None,
                "valid_to": rel.valid_to.isoformat() if rel.valid_to else None, "transaction_window": [window[0].isoformat(), window[1].isoformat()] if window else None, "tolerance_days": 30}
    if rel.observed_at and window:
        inside = window[0] - timedelta(days=30) <= rel.observed_at <= window[1] + timedelta(days=30)
        temporal["compatible_with_events"] = inside
        temporal["note"] = "Observation falls within ±30 days of the transactions." if inside else "Observation is outside the event window: the relationship may not have held during the events."
    else:
        temporal["compatible_with_events"] = None
        temporal["note"] = "No dated observation or no transaction window: temporal compatibility cannot be assessed."
    uncertain_times = [e.id for e in evs if e.time_precision in {"ambiguous", "unknown"}]
    alts = [{"hypothesis": h, "why_relevant": w, "would_distinguish": d} for (h, w, d) in ALTERNATIVES.get(rel.relationship_type, [("Coincidence or data error", "Any single association can arise by coincidence or extraction error.", "An independent second source.")])]
    missing = [a["would_distinguish"] for a in alts]
    attrs = rel.attributes or {}
    if rel.relationship_type == "SHARED_INFRASTRUCTURE":
        strength = "weak" if attrs.get("multi_tenant") else "weak-to-moderate"
        why = f"IP {attrs.get('shared_ip')} hosts {attrs.get('domain_count_on_ip')} domain(s) in this case" + ("; observed as multi-tenant/CDN" if attrs.get("multi_tenant") else "") + ". Shared-provider context, not direct evidence."
        kind = "shared-provider context"
    elif rel.evidence_level.value == "corroborated":
        strength, why, kind = "strong", f"{len(source_types)} independent source type(s) agree ({', '.join(sorted(source_types))}).", "corroborated inference"
    elif rel.evidence_level.value == "directly_observed":
        strength, why, kind = "moderate", "Single source record; not yet corroborated by an independent source.", "direct evidence (single source)"
    elif rel.evidence_level.value == "derived":
        strength, why, kind = "moderate", f"Deterministic rule {rel.method_name}@{rel.method_version}; depends on the inputs cited.", "derived association"
    else:
        strength, why, kind = "weak", "Candidate / stale / contradicted association.", "association"
    high_counters = [c for c in counters if c.severity == "high"]
    last_review = reviews[-1].decision.value if reviews else None
    if rel.evidence_level.value == "stale":
        state = "stale"
    elif rel.evidence_level.value == "contradicted":
        state = "contradicted"
    elif high_counters and rel.relationship_type != "SHARED_INFRASTRUCTURE" and last_review != "supported":
        state = "contested"
    elif competing and any(h.status in {"open", "under_review", "disputed"} for h in competing):
        state = "contested"
    elif rel.evidence_level.value == "corroborated":
        state = "corroborated"
    elif rel.evidence_level.value in {"directly_observed", "derived"}:
        state = "supported"
    elif rel.evidence_level.value == "candidate":
        state = "candidate"
    else:
        state = "unresolved"
    if last_review == "rejected":
        state = "contradicted"
    conclusion = {"supported": "Supported by a source record; no counter-evidence outweighs it. A record-level fact about the relationship, not about intent or control.",
                  "corroborated": "Independently corroborated. Remains a relationship between records; attribution to a person requires further evidence.",
                  "contested": "Competing explanation or high-severity counter-evidence is on file; do not report as established.",
                  "candidate": "Association only. Must not be presented as a finding without an independent bridge.",
                  "contradicted": "Counter-evidence or a reviewer rejection outweighs the association.", "unresolved": "Insufficient evidence either way.",
                  "stale": "Observation outside the validity window; cannot support conclusions about the event period."}[state]
    report = {"alleged_relationship": {"id": rel.id, "type": rel.relationship_type, "from": {"id": src.id, "type": src.entity_type, "label": src.label, "key": src.key} if src else None,
                                       "to": {"id": tgt.id, "type": tgt.entity_type, "label": tgt.label, "key": tgt.key} if tgt else None, "evidence_level": rel.evidence_level.value,
                                       "review_status": rel.review_status.value, "method": f"{rel.method_name}@{rel.method_version}", "limitations": rel.limitations or [], "attributes": attrs},
              "what_records_establish": f"The cited records support a {rel.relationship_type.replace('_', ' ').lower()} relationship between the two records. They do not establish who controls either side, nor knowledge or intent.",
              "supporting_records": supporting, "independent_source_types": sorted(source_types),
              "counter_evidence": [{"kind": c.kind, "severity": c.severity, "description": c.description, "evidence_id": c.evidence_item_id} for c in counters],
              "missing_evidence": missing, "temporal_compatibility": temporal, "uncertain_time_evidence": uncertain_times,
              "source_reliability": sorted({" — ".join(RELIABILITY.get(e.source_type, ("unknown", "unknown"))) for e in evs}),
              "strength": {"label": strength, "why": why, "kind": kind}, "alternative_hypotheses": alts,
              "competing_hypotheses_on_file": [{"id": h.id, "title": h.title, "status": h.status, "version": h.version} for h in competing],
              "review_history": [{"decision": r.decision.value, "reason": r.reason, "reviewer_id": r.reviewer_id, "at": r.created_at.isoformat()} for r in reviews],
              "current_conclusion": {"state": state, "text": conclusion}, "recommended_next_evidence": missing[:3],
              "actions": ["accept (supervisor for candidate/stale/contradicted)", "reject", "retain_as_candidate", "add_competing_hypothesis", "record_dissent"]}
    return result(case, "attribution_challenge", ADVERSARY_VERSION, findings=[finding("challenge_state", f"{rel.relationship_type} {src.label if src else '?'} → {tgt.label if tgt else '?'}: {state}",
                  evidence_class={"supported": "observed", "corroborated": "corroborated", "contested": "candidate", "candidate": "candidate", "contradicted": "contradicted", "unresolved": "unresolved", "stale": "stale"}[state],
                  evidence_refs=ev_ids, state=state)], input_evidence_ids=ev_ids, counter_evidence=report["counter_evidence"], uncertainties=missing,
                  limitations=["A relationship between records is never a finding about a person's knowledge, intent or control.", "Human review is mandatory for material attribution decisions."],
                  report=report, states=STATES, state=state)


def challenge_all(db: Session, case: Case, *, limit: int = 60) -> dict:
    rels = db.execute(select(Relationship).where(Relationship.case_id == case.id, Relationship.relationship_type.not_in(["DOCUMENTS", "BELONGS_TO_DOMAIN"]))).scalars().all()
    material = sorted(rels, key=lambda r: ({"candidate": 0, "contradicted": 0, "stale": 1, "derived": 2, "corroborated": 3, "directly_observed": 4}.get(r.evidence_level.value, 5), r.relationship_type, r.id))[:limit]
    rows = []
    for r in material:
        c = challenge(db, case, r)
        rep = c["report"]
        rows.append({"relationship_id": r.id, "type": r.relationship_type, "from": rep["alleged_relationship"]["from"], "to": rep["alleged_relationship"]["to"], "state": c["state"],
                     "strength": rep["strength"]["label"], "counter_evidence": len(rep["counter_evidence"]), "alternatives": len(rep["alternative_hypotheses"]), "review_status": r.review_status.value})
    by_state: dict[str, int] = {}
    for r in rows:
        by_state[r["state"]] = by_state.get(r["state"], 0) + 1
    return result(case, "attribution_challenge_summary", ADVERSARY_VERSION, findings=[finding("summary", f"{len(rows)} relationships challenged", evidence_class="derived")], rows=rows, by_state=by_state, states=STATES)
