"""Temporal evidence fusion: explicit intervals, declared tolerances, source-time vs normalised time, and compatibility checks.

Records are correlated only when their intervals are compatible under the declared rule; current-only DNS/RDAP data never
supports an earlier historical claim; ambiguous timestamps stay ambiguous and widen the interval. Chronology is not causality.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Case, Entity, EvidenceItem, Relationship, Transaction
from app.services.contract import finding, result

TEMPORAL_VERSION = "1.0.0"
PRECISION_WIDTH = {"second": timedelta(seconds=1), "minute": timedelta(minutes=1), "day": timedelta(days=1), "month": timedelta(days=31), "ambiguous": timedelta(days=31), "unknown": None}


def _iso(d):
    return d.isoformat() if d else None


def interval(ev: EvidenceItem) -> dict:
    """Explicit interval for an evidence item: [start, end] widened by precision; unknown when no time."""
    start, end = ev.event_time_start, ev.event_time_end or ev.event_time_start
    width = PRECISION_WIDTH.get(ev.time_precision)
    if start is None or width is None:
        return {"start": None, "end": None, "precision": ev.time_precision, "known": False}
    if ev.time_precision == "ambiguous" and start.day <= 12:
        # dd/mm vs mm/dd: the alternative reading is also inside the interval
        alt = start.replace(month=start.day, day=start.month)
        lo, hi = min(start, alt), max(start, alt)
        return {"start": _iso(lo), "end": _iso(hi + timedelta(days=1)), "precision": "ambiguous", "known": True, "alternative_reading": _iso(alt), "note": "two calendar readings; interval covers both"}
    return {"start": _iso(start), "end": _iso((end or start) + width), "precision": ev.time_precision, "known": True}


def compatible(a: dict, b: dict, tolerance: timedelta) -> dict:
    if not a["known"] or not b["known"]:
        return {"compatible": None, "reason": "one or both intervals unknown"}
    a0, a1 = datetime.fromisoformat(a["start"]), datetime.fromisoformat(a["end"])
    b0, b1 = datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"])
    lo, hi = max(a0, b0 - tolerance), min(a1, b1 + tolerance)
    ok = lo <= hi
    return {"compatible": ok, "overlap_start": _iso(lo) if ok else None, "overlap_end": _iso(hi) if ok else None, "gap_hours": round((lo - hi).total_seconds() / 3600, 1) if not ok else 0.0, "tolerance_hours": tolerance.total_seconds() / 3600}


def fusion(db: Session, case: Case, *, window_from: datetime | None = None, window_to: datetime | None = None, tolerance_hours: int = 72) -> dict:
    evs = db.execute(select(EvidenceItem).where(EvidenceItem.case_id == case.id)).scalars().all()
    txs = {t.evidence_item_id: t for t in db.execute(select(Transaction).where(Transaction.case_id == case.id)).scalars()}
    rels = db.execute(select(Relationship).where(Relationship.case_id == case.id)).scalars().all()
    ents = {e.id: e for e in db.execute(select(Entity).where(Entity.case_id == case.id)).scalars()}
    records = []
    for e in evs:
        iv = interval(e)
        t = txs.get(e.id)
        src_time = t.datetime_raw if t else (e.normalised_value or {}).get("observed_at")
        kind = "transaction" if t else e.source_type
        current_only = e.extraction_method.startswith("connector") or "current_lookup_not_historical" in (e.quality_flags or [])
        rec = {"evidence_id": e.id, "kind": kind, "source_time_raw": src_time, "source_timezone": e.source_timezone or ("unknown (not assumed)" if kind != "transaction" else "Asia/Kolkata (statement convention, declared)"),
               "normalised_utc": _iso(e.event_time_start), "observed_at": _iso(e.observed_at), "ingested_at": _iso(e.ingested_at), "interval": iv, "parser": f"{e.parser_name}@{e.parser_version}",
               "freshness": "CURRENT_ONLY" if current_only else ("historical_observation_as_supplied" if kind == "technical_observation" else "event_record"),
               "review_action": "resolve ambiguous date" if e.time_precision == "ambiguous" else ("resolve missing time" if not iv["known"] and kind == "transaction" else None),
               "label": (f"{t.direction} ₹{t.amount_minor / 100:,.2f} {t.account_ref}→{t.counterparty_ref}" if t and t.amount_minor is not None else f"{kind} {(e.normalised_value or {}).get('domain') or (e.normalised_value or {}).get('value') or ''}")}
        records.append(rec)
    # window filter: included / excluded / unknown
    included, excluded, unknown = [], [], []
    for r in records:
        iv = r["interval"]
        if not iv["known"]:
            unknown.append(r["evidence_id"])
            continue
        s, e_ = datetime.fromisoformat(iv["start"]), datetime.fromisoformat(iv["end"])
        if (window_from and e_ < window_from) or (window_to and s > window_to):
            excluded.append(r["evidence_id"])
        else:
            included.append(r["evidence_id"])
    # relationship compatibility: infrastructure observations vs transaction window
    tx_times = [t.datetime_utc for t in txs.values() if t.datetime_utc]
    tx_iv = {"start": _iso(min(tx_times)), "end": _iso(max(tx_times)), "known": True, "precision": "second"} if tx_times else {"known": False, "start": None, "end": None, "precision": "unknown"}
    claims = []
    for r in rels:
        if r.relationship_type not in {"RESOLVES_TO", "HOSTED_ON", "SHARED_INFRASTRUCTURE", "PAYMENT_INSTRUCTION_MATCHES_TRANSACTION", "SAME_ACCOUNT_IDENTIFIER"}:
            continue
        current_only = "current_lookup_not_historical" in (r.limitations or []) or r.method_name.startswith("connector")
        r_iv = {"start": _iso(r.valid_from or r.observed_at), "end": _iso(r.valid_to or r.observed_at), "known": bool(r.valid_from or r.observed_at), "precision": "second"}
        comp = compatible(r_iv, tx_iv, timedelta(days=30)) if r_iv["known"] and tx_iv["known"] else {"compatible": None, "reason": "undated relationship or no transactions"}
        if current_only:
            comp = {**comp, "compatible": False if comp.get("compatible") is None else comp["compatible"], "note": "CURRENT_ONLY observation: cannot support a claim about the earlier event period regardless of overlap."}
            verdict = "cannot_support_historical_claim"
        elif comp.get("compatible") is True:
            verdict = "temporally_compatible"
        elif comp.get("compatible") is False:
            verdict = "temporal_contradiction"
        else:
            verdict = "undetermined"
        a, b = ents.get(r.source_entity_id), ents.get(r.target_entity_id)
        in_window = True
        if window_from or window_to:
            if r_iv["known"]:
                s = datetime.fromisoformat(r_iv["start"])
                in_window = not ((window_from and s < window_from) or (window_to and s > window_to))
        claims.append({"relationship_id": r.id, "type": r.relationship_type, "from": a.key if a else None, "to": b.key if b else None, "evidence_level": r.evidence_level.value, "interval": r_iv,
                       "compared_to": "transaction window", "compatibility": comp, "verdict": verdict, "current_only": current_only, "included_in_window": in_window})
    contradictions = [c for c in claims if c["verdict"] == "temporal_contradiction"]
    return result(case, "temporal_fusion", TEMPORAL_VERSION, findings=[finding("temporal", f"{len(contradictions)} temporal contradiction(s); {len(unknown)} record(s) with unknown time; {sum(1 for c in claims if c['current_only'])} current-only observation(s)", evidence_class="derived")],
                  counter_evidence=[{"relationship_id": c["relationship_id"], "detail": "observation interval does not overlap the transaction window (±30 d)"} for c in contradictions],
                  limitations=["Chronological proximity is never treated as causation.", "Unknown timezones are not assumed; statement dates are converted using the declared Asia/Kolkata convention and flagged.",
                               "Current-only DNS/RDAP cannot support claims about an earlier period.", "IP geolocation is never used as a person's location."],
                  records=records, window={"from": _iso(window_from), "to": _iso(window_to), "tolerance_hours": tolerance_hours, "included": included, "excluded": excluded, "unknown_time": unknown},
                  transaction_window=tx_iv, claims=claims, rules={"transaction_vs_observation_tolerance_days": 30, "payment_instruction_tolerance_hours": tolerance_hours, "ambiguous_dates": "interval covers both dd/mm and mm/dd readings"})
