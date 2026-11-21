"""Fraud-operation digital twin: typed, time-aware event model assembled from persisted evidence.

Events are derived at query time from evidence items, transactions, observations, payment instructions, funds records,
evidence requests, hypotheses and reviews, plus analyst-entered InvestigationEvents (which stay `reported`).
Chronological order is never turned into causation: the only sequence edge is REPORTED_BEFORE and it is labelled as such.
`as_of` replays what was known at a point in time (by ingestion/creation time).
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import (AuditEvent, Case, Entity, EvidenceItem, EvidenceRequest, FundsRecord, Hypothesis, IndependentReview,
                        InvestigationEvent, PaymentInstruction, Relationship, SourceFile, Transaction)
from app.services.contract import finding, result

TWIN_VERSION = "1.0.0"
LAYERS = ["victim_journey", "artefact", "payment", "financial", "infrastructure", "investigation"]
LEGEND = {"reported": "Stated by the complainant or an analyst; not independently observed",
          "directly_observed": "Present in a supplied source record", "extracted": "Produced by a parser/OCR/decoder from a supplied file",
          "corroborated": "Two independent sources agree", "derived": "Computed by a documented deterministic rule",
          "candidate": "Possible association; requires review", "contradicted": "Counter-evidence weakens it",
          "stale": "Observation outside the relevant validity window", "unresolved": "Unknown; evidence not supplied"}
EVENT_TYPES = ["VICTIM_CONTACT_REPORTED", "MESSAGE_RECEIVED_OBSERVED", "URL_MENTIONED", "WEBSITE_CAPTURE_SUPPLIED", "PAYMENT_PAGE_OBSERVED",
               "QR_PAYLOAD_EXTRACTED", "PAYMENT_INSTRUCTION_EXTRACTED", "BANK_TRANSACTION_RECORDED", "ACCOUNT_CREDIT_RECORDED", "ONWARD_TRANSFER_RECORDED",
               "DOMAIN_OBSERVATION_RECORDED", "DNS_OBSERVATION_RECORDED", "INFRASTRUCTURE_RELATIONSHIP_CANDIDATE", "FUNDS_HELD_DOCUMENTED",
               "FUNDS_RESTORED_DOCUMENTED", "EVIDENCE_REQUEST_CREATED", "HYPOTHESIS_REVISED", "SUPERVISOR_REVIEW_RECORDED", "RECRUITMENT_CONTACT_REPORTED",
               "ACCOUNT_HANDOVER_REPORTED", "PRESERVATION_RESPONSE_RECORDED"]
_AMOUNT_RE = re.compile(r"(?:rs\.?|inr|₹)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", re.I)
_UTR_RE = re.compile(r"\bUTR\s*([A-Z0-9]{8,22})\b", re.I)
_VPA_RE = re.compile(r"\b([a-z0-9.\-_]{2,}@[a-z][a-z0-9.\-]{1,})\b", re.I)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _ev(id_: str, etype: str, layer: str, cls: str, *, event_time, precision, observed_at, ingested_at, label, evidence_ids, locator=None,
        source_file_id=None, attributes=None, reported_by=None) -> dict:
    return {"id": id_, "event_type": etype, "layer": layer, "evidence_class": cls, "event_time": _iso(event_time), "time_precision": precision,
            "observed_at": _iso(observed_at), "ingested_at": _iso(ingested_at), "label": label, "evidence_ids": evidence_ids, "source_locator": locator or {},
            "source_file_id": source_file_id, "attributes": attributes or {}, "reported_by": reported_by}


def assemble(db: Session, case: Case, *, as_of: datetime | None = None, layers: set[str] | None = None) -> dict:
    files = {f.id: f for f in db.execute(select(SourceFile).where(SourceFile.case_id == case.id)).scalars()}
    evs = db.execute(select(EvidenceItem).where(EvidenceItem.case_id == case.id)).scalars().all()
    txs = {t.evidence_item_id: t for t in db.execute(select(Transaction).where(Transaction.case_id == case.id)).scalars()}
    rels = db.execute(select(Relationship).where(Relationship.case_id == case.id)).scalars().all()
    ents = {e.id: e for e in db.execute(select(Entity).where(Entity.case_id == case.id)).scalars()}
    alias = engine.alias_map(db, case)
    holders = {alias.get(t.account_ref, t.account_ref) for t in txs.values()}
    victim_like = {alias.get(a, a) for a in holders}  # statement holders that only send in the first hop are the victims; refined below
    edges = engine.money_edges(db, case)
    inbound: dict[str, list] = defaultdict(list)
    for e in edges:
        inbound[e["dst"]].append(e)
    events: list[dict] = []
    links: list[dict] = []

    def keep(ingested: datetime | None) -> bool:
        return as_of is None or ingested is None or ingested <= as_of

    # --- evidence-derived events
    for it in evs:
        if not keep(it.ingested_at):
            continue
        f = files.get(it.source_file_id)
        nv = it.normalised_value or {}
        if it.source_type == "bank_statement" and it.id in txs:
            t = txs[it.id]
            acct = alias.get(t.account_ref, t.account_ref)
            cp = alias.get(t.counterparty_ref, t.counterparty_ref) if t.counterparty_ref else None
            if t.direction == "debit" and acct in holders and inbound.get(acct) and acct not in victim_like - {acct}:
                etype = "ONWARD_TRANSFER_RECORDED" if any(e["src"] in holders and e["src"] != acct for e in inbound[acct]) else "BANK_TRANSACTION_RECORDED"
            elif t.direction == "credit":
                etype = "ACCOUNT_CREDIT_RECORDED"
            else:
                etype = "BANK_TRANSACTION_RECORDED"
            rel = next((r for r in rels if (r.attributes or {}).get("transaction_id") == t.id), None)
            cls = "corroborated" if rel and rel.evidence_level.value == "corroborated" else "directly_observed"
            amt = f"₹{t.amount_minor / 100:,.2f}" if t.amount_minor is not None else "amount missing"
            events.append(_ev(it.id, etype, "financial", cls, event_time=t.datetime_utc, precision=t.time_precision, observed_at=it.observed_at, ingested_at=it.ingested_at,
                              label=f"{t.direction} {amt} {t.account_ref} → {t.counterparty_ref or 'unknown counterparty'}", evidence_ids=[it.id], locator=it.source_locator,
                              source_file_id=it.source_file_id, attributes={"transaction_id": t.id, "reference": t.external_reference, "amount_minor": t.amount_minor,
                                                                            "channel": t.channel, "duplicate_of": t.duplicate_of, "warnings": t.warnings or [], "file": f.original_name if f else None}))
            if cp:
                links.append({"type": "TRANSACTION_DEBITS_ACCOUNT" if t.direction == "debit" else "TRANSACTION_CREDITS_ACCOUNT", "from": it.id, "to": f"account:{acct if t.direction == 'debit' else cp}", "evidence_class": cls})
        elif it.source_type == "technical_observation":
            typ = nv.get("type")
            rel = next((r for r in rels if r.observed_at == it.observed_at and (ents.get(r.source_entity_id) or Entity()).key == str(nv.get("domain") or "").lower() and r.relationship_type in {"RESOLVES_TO", "HOSTED_ON"}), None)
            cls = rel.evidence_level.value if rel and rel.evidence_level.value in {"stale", "contradicted"} else "directly_observed"
            etype = "DNS_OBSERVATION_RECORDED" if typ == "dns" else ("URL_MENTIONED" if typ == "url" else "DOMAIN_OBSERVATION_RECORDED")
            lim = ["current_lookup_not_historical"] if it.extraction_method.startswith("connector") else []
            events.append(_ev(it.id, etype, "infrastructure", cls, event_time=it.event_time_start, precision=it.time_precision, observed_at=it.observed_at, ingested_at=it.ingested_at,
                              label=f"{typ} {nv.get('domain') or nv.get('url') or ''} {nv.get('ip') or ''} {nv.get('provider') or ''}".strip(), evidence_ids=[it.id], locator=it.source_locator,
                              source_file_id=it.source_file_id, attributes={"source": nv.get("source"), "valid_to": _iso(it.event_time_end), "limitations": lim, "file": f.original_name if f else None}))
            if nv.get("domain") and nv.get("ip"):
                links.append({"type": "DOMAIN_RESOLVED_TO_OBSERVATION", "from": f"domain:{str(nv['domain']).lower()}", "to": it.id, "evidence_class": cls})
        elif it.source_type in {"complaint", "document"} and it.extraction_method.startswith("regex_"):
            kind, val = nv.get("indicator_kind"), nv.get("value")
            etype = "URL_MENTIONED" if kind in {"url", "domain"} else "VICTIM_CONTACT_REPORTED" if kind == "phone" else "PAYMENT_INSTRUCTION_EXTRACTED" if kind in {"vpa", "utr"} else "MESSAGE_RECEIVED_OBSERVED"
            cls = "candidate" if "ocr_low_confidence" in (it.quality_flags or []) else ("extracted" if "ocr_review_required" in (it.quality_flags or []) else "reported")
            layer = "artefact" if kind in {"url", "domain"} else ("payment" if kind in {"vpa", "utr", "account"} else "victim_journey")
            events.append(_ev(it.id, etype, layer, cls, event_time=None, precision="unknown", observed_at=it.observed_at, ingested_at=it.ingested_at,
                              label=f"{kind} named in {f.original_name if f else 'document'}: {val}", evidence_ids=[it.id], locator=it.source_locator, source_file_id=it.source_file_id,
                              attributes={"indicator_kind": kind, "value": val, "note": "The document names this identifier. When the described event happened is unknown unless another source dates it.",
                                          "file": f.original_name if f else None}, reported_by="complainant (document)" if it.source_type == "complaint" else "document"))
            if kind in {"vpa", "account"}:
                links.append({"type": "PAYMENT_IDENTIFIER_NAMED", "from": it.id, "to": f"account:{alias.get(str(val).lower(), str(val).lower())}", "evidence_class": cls})
        elif it.source_type in {"complaint", "document"} and it.extraction_method == "ocr":
            ocr = nv.get("ocr") or {}
            etype = "PAYMENT_PAGE_OBSERVED" if re.search(r"pay|upi|qr|amount", it.raw_value or "", re.I) else "WEBSITE_CAPTURE_SUPPLIED"
            events.append(_ev(it.id, etype, "artefact", "candidate" if ocr.get("quality") != "ok" else "extracted", event_time=None, precision="unknown", observed_at=it.observed_at,
                              ingested_at=it.ingested_at, label=f"Screenshot/scan text extracted ({ocr.get('engine', 'ocr')}, conf {ocr.get('confidence')})", evidence_ids=[it.id],
                              locator=it.source_locator, source_file_id=it.source_file_id, attributes={"ocr": ocr, "excerpt": (it.raw_value or "")[:200], "file": f.original_name if f else None}))
        elif it.source_type == "payment_instruction":
            pass  # handled below with the PaymentInstruction row (richer fields)
    # --- payment instructions + matches
    for pi in db.execute(select(PaymentInstruction).where(PaymentInstruction.case_id == case.id)).scalars():
        if not keep(pi.created_at):
            continue
        matches = [r for r in rels if r.method_name == "payment_bridge" and (r.attributes or {}).get("instruction_id") == pi.id]
        etype = "QR_PAYLOAD_EXTRACTED" if pi.extraction_method == "qr_decoder" else "PAYMENT_INSTRUCTION_EXTRACTED"
        f = files.get(pi.source_file_id)
        events.append(_ev(f"pi:{pi.id}", etype, "payment", "extracted" if pi.extraction_method != "ocr_text" else "candidate", event_time=None, precision="unknown",
                          observed_at=pi.observed_at, ingested_at=pi.created_at, label=f"Payment instruction → {pi.payee_vpa or pi.payload_type}" + (f" ₹{pi.amount_minor / 100:,.2f}" if pi.amount_minor is not None else ""),
                          evidence_ids=[pi.source_evidence_item_id] if pi.source_evidence_item_id else [], locator=pi.source_locator, source_file_id=pi.source_file_id,
                          attributes={"instruction_id": pi.id, "payload_type": pi.payload_type, "reference": pi.reference, "warnings": pi.warnings or [], "file": f.original_name if f else None,
                                      "match_status": (matches[0].attributes or {}).get("match_status") if matches else "not_matched_yet",
                                      "note": "Extracted at the observation time; when the victim actually saw it is unknown unless another source establishes it."}))
        for m in matches:
            tid = (m.attributes or {}).get("transaction_id")
            t = next((t for t in txs.values() if t.id == tid), None)
            if t:
                links.append({"type": "PAYMENT_INSTRUCTION_MATCHES_TRANSACTION", "from": f"pi:{pi.id}", "to": t.evidence_item_id, "evidence_class": m.evidence_level.value,
                              "match_status": (m.attributes or {}).get("match_status"), "relationship_id": m.id})
    # --- candidate infrastructure relationships
    for r in rels:
        if r.relationship_type == "SHARED_INFRASTRUCTURE" and keep(r.ingested_at):
            a, b = ents.get(r.source_entity_id), ents.get(r.target_entity_id)
            events.append(_ev(f"rel:{r.id}", "INFRASTRUCTURE_RELATIONSHIP_CANDIDATE", "infrastructure", "candidate", event_time=r.valid_from, precision="unknown", observed_at=r.observed_at,
                              ingested_at=r.ingested_at, label=f"{a.key if a else '?'} and {b.key if b else '?'} share IP {(r.attributes or {}).get('shared_ip')}", evidence_ids=[],
                              attributes={"relationship_id": r.id, "multi_tenant": (r.attributes or {}).get("multi_tenant"), "limitations": r.limitations or [], "review_status": r.review_status.value}))
            links.append({"type": "POTENTIAL_PATTERN_SIMILARITY", "from": f"domain:{a.key if a else ''}", "to": f"domain:{b.key if b else ''}", "evidence_class": "candidate", "relationship_id": r.id})
    # --- funds records
    for fr in db.execute(select(FundsRecord).where(FundsRecord.case_id == case.id)).scalars():
        if not keep(fr.recorded_at):
            continue
        events.append(_ev(f"funds:{fr.id}", "FUNDS_HELD_DOCUMENTED" if fr.kind == "held" else "FUNDS_RESTORED_DOCUMENTED", "investigation", "directly_observed", event_time=fr.recorded_at,
                          precision="day", observed_at=fr.recorded_at, ingested_at=fr.recorded_at, label=f"{'SIMULATED ' if fr.is_simulated else ''}{fr.kind} ₹{fr.amount_minor / 100:,.2f} on {fr.account_ref} ({fr.source_kind})",
                          evidence_ids=[fr.source_evidence_item_id], attributes={"is_simulated": fr.is_simulated, "reference": fr.reference}))
    # --- evidence requests / hypotheses / reviews
    for rq in db.execute(select(EvidenceRequest).where(EvidenceRequest.case_id == case.id)).scalars():
        if keep(rq.created_at):
            events.append(_ev(f"req:{rq.id}", "EVIDENCE_REQUEST_CREATED", "investigation", "derived", event_time=rq.created_at, precision="second", observed_at=rq.created_at, ingested_at=rq.created_at,
                              label=f"{'SIMULATED ' if rq.is_simulated else ''}request draft: {rq.title} [{rq.status}]", evidence_ids=[], attributes={"status": rq.status, "organisation_type": rq.organisation_type}))
    for h in db.execute(select(Hypothesis).where(Hypothesis.case_id == case.id)).scalars():
        for v in (h.history or []) + [{"version": h.version, "status": h.status, "changed_at": _iso(h.updated_at), "statement": h.statement}]:
            ts = datetime.fromisoformat(v["changed_at"]) if v.get("changed_at") else h.created_at
            if keep(ts):
                events.append(_ev(f"hyp:{h.id}:v{v['version']}", "HYPOTHESIS_REVISED", "investigation", "reported", event_time=ts, precision="second", observed_at=ts, ingested_at=ts,
                                  label=f"Hypothesis v{v['version']} [{v.get('status')}]: {h.title}", evidence_ids=list(h.supporting_evidence_ids or []), attributes={"hypothesis_id": h.id}, reported_by="analyst"))
    for rv in db.execute(select(IndependentReview).where(IndependentReview.case_id == case.id)).scalars():
        if keep(rv.created_at):
            events.append(_ev(f"rev:{rv.id}", "SUPERVISOR_REVIEW_RECORDED", "investigation", "reported", event_time=rv.created_at, precision="second", observed_at=rv.created_at, ingested_at=rv.created_at,
                              label=f"Independent review: {rv.decision}{' (dissent)' if rv.is_dissent else ''}", evidence_ids=list(rv.evidence_reviewed or []), attributes={"hypothesis_id": rv.hypothesis_id, "mode": rv.mode}, reported_by="reviewer"))
    # --- analyst-entered events (always `reported` unless they cite a source item)
    for ie in db.execute(select(InvestigationEvent).where(InvestigationEvent.case_id == case.id)).scalars():
        if keep(ie.created_at):
            events.append(_ev(f"ie:{ie.id}", ie.event_type, ie.layer, ie.evidence_class, event_time=ie.event_time, precision=ie.time_precision, observed_at=ie.observed_at, ingested_at=ie.created_at,
                              label=ie.description[:160], evidence_ids=[ie.source_evidence_item_id] if ie.source_evidence_item_id else [], locator=ie.source_locator, source_file_id=ie.source_file_id,
                              attributes={**(ie.attributes or {}), "reported_at": _iso(ie.reported_at), "manual_entry": True}, reported_by=ie.reported_by))
    if layers:
        events = [e for e in events if e["layer"] in layers]
    events.sort(key=lambda e: (e["event_time"] is None, e["event_time"] or "", e["observed_at"] or "", e["id"]))
    # REPORTED_BEFORE: chronology among reported/observed events with known times (sequence, explicitly not causation)
    timed = [e for e in events if e["event_time"]]  # chronology across layers; sequence only, never causation
    for a, b in zip(timed, timed[1:]):
        links.append({"type": "REPORTED_BEFORE", "from": a["id"], "to": b["id"], "evidence_class": "derived", "note": "Chronological order only; not causation."})
    paths = engine.reconstruct_paths(db, case)
    unmatched = [e for e in events if e["event_type"] in {"QR_PAYLOAD_EXTRACTED", "PAYMENT_INSTRUCTION_EXTRACTED"} and e["attributes"].get("match_status") in {None, "not_matched_yet", "NO_MATCH", "UNRESOLVED"}]
    by_class = defaultdict(int)
    for e in events:
        by_class[e["evidence_class"]] += 1
    unresolved_q = [f"Onward movement from {p['accounts'][-1]} is unknown ({p['resolution_hint']})" for p in paths if p["status"] == "unresolved"][:10]
    unresolved_q += [f"Payment instruction {e['label']} has no matching recorded transaction yet" for e in unmatched][:5]
    unresolved_q += [f"{e['label']}: shared hosting is a candidate pivot only" for e in events if e["event_type"] == "INFRASTRUCTURE_RELATIONSHIP_CANDIDATE"][:5]
    unresolved_q = list(dict.fromkeys(unresolved_q))
    findings = [finding("event_count", f"{len(events)} events across {len({e['layer'] for e in events})} layers", evidence_class="derived")]
    return result(case, "fraud_operation_digital_twin", TWIN_VERSION, findings=findings, input_evidence_ids=[i for e in events for i in e["evidence_ids"] if i],
                  uncertainties=unresolved_q, limitations=["The twin is an analytical reconstruction of reported and observed events; unknown elements stay unknown.",
                                                           "REPORTED_BEFORE edges express chronology only. No causal edge is created from proximity in time."],
                  events=events, links=links, layers=LAYERS, legend=LEGEND, event_types=EVENT_TYPES, counts_by_class=dict(by_class), as_of=_iso(as_of),
                  supported_facts={"transactions_recorded": sum(1 for e in events if e["layer"] == "financial"), "instructions_extracted": sum(1 for e in events if e["layer"] == "payment"),
                                   "infrastructure_observations": sum(1 for e in events if e["layer"] == "infrastructure" and e["evidence_class"] == "directly_observed"),
                                   "paths_reconstructed": len(paths), "paths_unresolved": sum(1 for p in paths if p["status"] == "unresolved")})


def victim_journey(db: Session, case: Case) -> dict:
    """Reported journey per complaint with consistency checks against recorded transactions."""
    twin = assemble(db, case, layers={"victim_journey", "artefact", "payment", "financial"})
    files = {f.id: f for f in db.execute(select(SourceFile).where(SourceFile.case_id == case.id)).scalars()}
    complaints = db.execute(select(EvidenceItem).where(EvidenceItem.case_id == case.id, EvidenceItem.source_type == "complaint",
                                                       EvidenceItem.extraction_method.in_(["text_layer", "ocr", "paragraph", "line", "text", "plain", "docx_paragraph"]))).scalars().all()
    txs = db.execute(select(Transaction).where(Transaction.case_id == case.id)).scalars().all()
    journeys = []
    for ev in complaints:
        text = ev.raw_value or ""
        amounts = [int(round(float(m.replace(",", "")) * 100)) for m in _AMOUNT_RE.findall(text)]
        utrs = [u.upper() for u in _UTR_RE.findall(text)]
        vpas = [v.lower() for v in _VPA_RE.findall(text)]
        checks = []
        for amt in amounts[:3]:
            hits = [t for t in txs if t.amount_minor == amt]
            checks.append({"claim": f"amount ₹{amt / 100:,.2f}", "status": "corroborated_by_statement" if hits else "not_found_in_supplied_statements",
                           "transaction_ids": [t.id for t in hits][:5], "note": None if hits else "A reported amount with no matching row is not evidence that it was not paid; the relevant statement may be missing."})
        for u in utrs[:3]:
            hits = [t for t in txs if (t.external_reference or "").upper() == u]
            conflict = [t for t in hits if amounts and t.amount_minor not in amounts]
            checks.append({"claim": f"UTR {u}", "status": "conflicting_amount" if conflict else ("corroborated_by_statement" if hits else "not_found_in_supplied_statements"),
                           "transaction_ids": [t.id for t in hits][:5], "note": f"Statement shows ₹{conflict[0].amount_minor / 100:,.2f} for this UTR; complaint states a different amount." if conflict else None})
        for v in vpas[:3]:
            hits = [t for t in txs if (t.counterparty_ref or "").lower() == v]
            checks.append({"claim": f"payee {v}", "status": "corroborated_by_statement" if hits else "not_found_in_supplied_statements", "transaction_ids": [t.id for t in hits][:5]})
        f = files.get(ev.source_file_id)
        journeys.append({"complaint_evidence_id": ev.id, "file": f.original_name if f else None, "sha256": f.sha256 if f else None, "locator": ev.source_locator,
                         "extraction": ev.extraction_method, "excerpt": text[:600], "reported_amounts_minor": amounts, "reported_utrs": utrs, "reported_payees": vpas,
                         "consistency_checks": checks, "evidence_class": "reported", "note": "Everything in a complaint is what the complainant reports. Checks show where supplied statements corroborate or conflict."})
    inconsistencies = [c for j in journeys for c in j["consistency_checks"] if c["status"] in {"conflicting_amount"}]
    return result(case, "victim_journey", TWIN_VERSION, findings=[finding("journey", f"{len(journeys)} complaint narrative(s) reconstructed", evidence_class="reported")],
                  uncertainties=[c["claim"] + ": " + c["status"] for j in journeys for c in j["consistency_checks"] if c["status"] != "corroborated_by_statement"][:12],
                  counter_evidence=inconsistencies, limitations=["Manual and complaint-derived events are `reported`, never `directly_observed`.", "No URL in a complaint is visited; URLs are stored as strings."],
                  journeys=journeys, events=twin["events"], links=twin["links"], legend=LEGEND)


def replay(db: Session, case: Case, *, at: datetime | None, compare_to: datetime | None = None) -> dict:
    """What was known at `at` (and optionally the delta to `compare_to`), from append-only ingestion/creation timestamps and the audit log."""
    def snapshot(ts: datetime | None) -> dict:
        tw = assemble(db, case, as_of=ts)
        files = [f for f in db.execute(select(SourceFile).where(SourceFile.case_id == case.id)).scalars() if ts is None or f.uploaded_at <= ts]
        rels = [r for r in db.execute(select(Relationship).where(Relationship.case_id == case.id)).scalars() if ts is None or r.ingested_at <= ts]
        return {"as_of": _iso(ts), "files": len(files), "events": len(tw["events"]), "events_by_class": tw["counts_by_class"], "relationships": len(rels),
                "relationships_by_level": dict(_count(r.evidence_level.value for r in rels)), "uncertainties": tw["uncertainties"], "supported_facts": tw["supported_facts"]}
    audit_rows = db.execute(select(AuditEvent).where(AuditEvent.case_id == case.id).order_by(AuditEvent.created_at)).scalars().all()
    timeline = [{"id": a.id, "at": _iso(a.created_at), "action": a.action, "actor_id": a.actor_id, "target_type": a.target_type, "target_id": a.target_id, "detail": a.detail} for a in audit_rows]
    snap = snapshot(at)
    out = {"snapshot": snap, "audit_timeline": timeline, "first_event_at": timeline[0]["at"] if timeline else None, "last_event_at": timeline[-1]["at"] if timeline else None}
    if compare_to is not None:
        other = snapshot(compare_to)
        out["compare"] = {"as_of": other["as_of"], "snapshot": other, "changed": {k: [snap.get(k), other.get(k)] for k in ("files", "events", "relationships") if snap.get(k) != other.get(k)},
                          "uncertainties_resolved": sorted(set(snap["uncertainties"]) - set(other["uncertainties"])), "uncertainties_new": sorted(set(other["uncertainties"]) - set(snap["uncertainties"]))}
    return result(case, "investigation_replay", TWIN_VERSION, findings=[finding("replay", f"state as of {snap['as_of'] or 'now'}", evidence_class="derived")],
                  limitations=["Replay uses ingestion/creation timestamps and the append-only audit log; no timestamp is invented."], **out)


def _count(it):
    d: dict[str, int] = defaultdict(int)
    for x in it:
        d[x] += 1
    return d
