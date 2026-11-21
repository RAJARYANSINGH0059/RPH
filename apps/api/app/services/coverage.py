"""Evidence coverage and blind-spot intelligence.

Distinguishes OBSERVED_ZERO (complete, balance-continuous coverage with no transactions) from NOT_SUPPLIED, PARTIAL_COVERAGE,
PARSE_FAILED, OCR_UNRELIABLE, CURRENT_ONLY, HISTORICAL_UNKNOWN and UNKNOWN. "No record supplied" is never presented as
"no activity".
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import Case, Entity, EvidenceItem, ParseRun, Relationship, SourceFile, Transaction
from app.services.contract import finding, result

COVERAGE_VERSION = "1.0.0"
STATES = ["COMPLETE_COVERAGE", "PARTIAL_COVERAGE", "NOT_SUPPLIED", "PARSE_FAILED", "OCR_UNRELIABLE", "CURRENT_ONLY", "HISTORICAL_UNKNOWN",
          "OBSERVED_ZERO", "UNKNOWN", "NOT_APPLICABLE"]
GAP_DAYS = 20  # a balance discontinuity spanning more than this is reported as a coverage gap (period), not just a mismatch


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _months(a: datetime, b: datetime) -> list[tuple[int, int]]:
    out, y, m = [], a.year, a.month
    while (y, m) <= (b.year, b.month):
        out.append((y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def statement_coverage(db: Session, case: Case) -> list[dict]:
    files = {f.id: f for f in db.execute(select(SourceFile).where(SourceFile.case_id == case.id)).scalars()}
    runs = {r.source_file_id: r for r in db.execute(select(ParseRun).where(ParseRun.case_id == case.id)).scalars()}
    txs = db.execute(select(Transaction).join(EvidenceItem, Transaction.evidence_item_id == EvidenceItem.id).where(Transaction.case_id == case.id)
                     .add_columns(EvidenceItem.source_file_id, EvidenceItem.source_locator)).all()
    by_file_acct: dict[tuple[str, str], list] = defaultdict(list)
    for t, sfid, loc in txs:
        by_file_acct[(sfid, t.account_ref)].append((t, loc))
    rows = []
    for (sfid, acct), items in sorted(by_file_acct.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        f, run = files.get(sfid), runs.get(sfid)
        timed = sorted([(t, loc) for t, loc in items if t.datetime_utc], key=lambda x: (x[0].datetime_utc, (x[1] or {}).get("row", 0)))
        ambiguous = sum(1 for t, _ in items if t.time_precision in {"ambiguous", "unknown"})
        start = timed[0][0].datetime_utc if timed else None
        end = timed[-1][0].datetime_utc if timed else None
        gaps, mismatches = [], []
        prev = None
        for t, loc in timed:
            if t.duplicate_of:
                continue
            if prev is not None and t.balance_after_minor is not None and prev[0].balance_after_minor is not None and t.amount_minor is not None:
                expected = prev[0].balance_after_minor + (t.amount_minor if t.direction == "credit" else -t.amount_minor)
                delta = t.balance_after_minor - expected
                if delta != 0:
                    span_days = (t.datetime_utc - prev[0].datetime_utc).days
                    entry = {"between_rows": [(prev[1] or {}).get("row"), (loc or {}).get("row")], "from": _iso(prev[0].datetime_utc), "to": _iso(t.datetime_utc),
                             "unexplained_balance_change_minor": delta, "span_days": span_days}
                    (gaps if span_days > GAP_DAYS else mismatches).append(entry)
            prev = (t, loc)
        # calendar months inside the span with zero rows AND no balance discontinuity across them = observed zero
        observed_zero_months = []
        if start and end and not gaps:
            have = {(t.datetime_utc.year, t.datetime_utc.month) for t, _ in timed}
            observed_zero_months = [f"{y:04d}-{m:02d}" for (y, m) in _months(start, end) if (y, m) not in have]
        if run is None or run.status == "failed" or (f and f.status == "failed"):
            state = "PARSE_FAILED"
        elif not timed:
            state = "UNKNOWN"
        elif gaps:
            state = "PARTIAL_COVERAGE"
        else:
            state = "COMPLETE_COVERAGE"
        rows.append({"subject_type": "account", "subject": acct, "source_file_id": sfid, "source_file": f.original_name if f else None, "sha256": f.sha256 if f else None,
                     "source_kind": f.detected_kind if f else None, "parser_version": run.parser_version if run else None, "parse_status": run.status if run else None,
                     "state": state, "coverage_start": _iso(start), "coverage_end": _iso(end), "rows_received": len(items), "rows_timed": len(timed),
                     "ambiguous_or_unknown_times": ambiguous, "gaps": gaps, "balance_mismatches_within_period": mismatches[:20],
                     "observed_zero_months": observed_zero_months, "duplicates": sum(1 for t, _ in items if t.duplicate_of),
                     "note": "Coverage is the span of the rows supplied, not the lifetime of the account. Months listed as observed-zero have continuous balances across them."})
    return rows


def coverage_report(db: Session, case: Case) -> dict:
    stmt = statement_coverage(db, case)
    covered_accounts = {r["subject"] for r in stmt if r["state"] in {"COMPLETE_COVERAGE", "PARTIAL_COVERAGE"}}
    alias = engine.alias_map(db, case)
    covered_canon = {alias.get(a, a) for a in covered_accounts}
    # accounts referenced in paths / transfers without their own statement
    edges = engine.money_edges(db, case)
    referenced: dict[str, dict] = {}
    for e in edges:
        for side in ("src", "dst"):
            k = e[side]
            if k in covered_canon:
                continue
            r = referenced.setdefault(k, {"first": None, "last": None, "edges": 0})
            r["edges"] += 1
            if e["time"]:
                r["first"] = e["time"] if r["first"] is None or e["time"] < r["first"] else r["first"]
                r["last"] = e["time"] if r["last"] is None or e["time"] > r["last"] else r["last"]
    not_supplied = [{"subject_type": "account", "subject": k, "state": "NOT_SUPPLIED", "referenced_in_transfers": v["edges"],
                     "period_of_interest_from": _iso(v["first"] - timedelta(days=1) if v["first"] else None), "period_of_interest_to": _iso((v["last"] or v["first"]) + timedelta(days=30) if (v["last"] or v["first"]) else None),
                     "note": "Referenced as a counterparty only. Nothing is known about its onward activity; absence of records is not absence of activity."}
                    for k, v in sorted(referenced.items())]
    # documents / OCR
    files = db.execute(select(SourceFile).where(SourceFile.case_id == case.id)).scalars().all()
    runs = {r.source_file_id: r for r in db.execute(select(ParseRun).where(ParseRun.case_id == case.id)).scalars()}
    docs = []
    for f in files:
        if f.detected_kind in {"csv", "xlsx", "json"}:
            continue
        run = runs.get(f.id)
        evs = db.execute(select(EvidenceItem).where(EvidenceItem.source_file_id == f.id, EvidenceItem.extraction_method.in_(["ocr", "text_layer", "paragraph", "line", "plain", "docx_paragraph", "docx_table"]))).scalars().all()
        ocr_items = [e for e in evs if e.extraction_method == "ocr"]
        low = [e for e in ocr_items if "ocr_low_confidence" in (e.quality_flags or [])]
        if run is None or run.status == "failed":
            state = "PARSE_FAILED"
        elif ocr_items and (low or any("ocr_engine_unavailable" in w for w in (run.warnings or []))):
            state = "OCR_UNRELIABLE"
        elif any("ocr_engine_unavailable" in w or "no_ocr_engine" in w for w in (run.warnings or [])):
            state = "OCR_UNRELIABLE"
        elif not evs:
            state = "UNKNOWN"
        else:
            state = "COMPLETE_COVERAGE"
        docs.append({"subject_type": "document", "subject": f.original_name, "source_file_id": f.id, "sha256": f.sha256, "state": state, "pages": (run.stats or {}).get("pages") if run else None,
                     "text_blocks": len(evs), "ocr_blocks": len(ocr_items), "low_confidence_ocr_blocks": len(low), "warnings": (run.warnings or [])[:6] if run else []})
    # infrastructure: observation windows vs transaction window
    txs = [t.datetime_utc for t in db.execute(select(Transaction).where(Transaction.case_id == case.id, Transaction.datetime_utc.is_not(None))).scalars()]
    window = (min(txs), max(txs)) if txs else None
    ents = {e.id: e for e in db.execute(select(Entity).where(Entity.case_id == case.id, Entity.entity_type.in_(["domain", "ip"]))).scalars()}
    rels = db.execute(select(Relationship).where(Relationship.case_id == case.id, Relationship.relationship_type == "RESOLVES_TO")).scalars().all()
    infra: dict[str, dict] = {}
    for r in rels:
        d = ents.get(r.source_entity_id)
        if not d:
            continue
        row = infra.setdefault(d.key, {"subject_type": "domain", "subject": d.key, "observations": [], "state": "UNKNOWN"})
        current_only = r.method_name in {"connector_dns", "connector_rdap"} or "current_lookup_not_historical" in (r.limitations or [])
        row["observations"].append({"observed_at": _iso(r.observed_at), "valid_from": _iso(r.valid_from), "valid_to": _iso(r.valid_to), "ip": ents[r.target_entity_id].key if r.target_entity_id in ents else None,
                                    "evidence_level": r.evidence_level.value, "kind": "CURRENT_ONLY" if current_only else "historical_observation_as_supplied", "method": r.method_name})
    for row in infra.values():
        kinds = {o["kind"] for o in row["observations"]}
        in_window = [o for o in row["observations"] if window and o["observed_at"] and window[0] - timedelta(days=30) <= datetime.fromisoformat(o["observed_at"]) <= window[1] + timedelta(days=30)]
        if kinds == {"CURRENT_ONLY"}:
            row["state"] = "CURRENT_ONLY"
            row["note"] = "Only current lookups exist. The mapping during the transaction window is HISTORICAL_UNKNOWN."
        elif window and not in_window:
            row["state"] = "HISTORICAL_UNKNOWN"
            row["note"] = "Supplied observations fall outside the transaction window (±30 days); the mapping during the events is unknown."
        else:
            row["state"] = "COMPLETE_COVERAGE" if in_window else "UNKNOWN"
        row["transaction_window"] = [_iso(window[0]), _iso(window[1])] if window else None
    # negative-claim warnings: unresolved path ends
    paths = engine.reconstruct_paths(db, case)
    negatives = []
    for i, p in enumerate(paths):
        if p["status"] == "unresolved":
            negatives.append({"path_index": i, "account": p["accounts"][-1], "warning": "Do not assert that funds stopped here: no statement for this account was supplied (NOT_SUPPLIED).",
                              "needed": p["resolution_hint"]})
    needed = [{"evidence": f"Statement of {r['subject']}", "period": [r["period_of_interest_from"], r["period_of_interest_to"]], "reason": f"referenced in {r['referenced_in_transfers']} transfer(s); onward movement unknown", "organisation_type": "bank"} for r in not_supplied]
    for r in stmt:
        for g in r["gaps"]:
            needed.append({"evidence": f"Statement of {r['subject']} for {g['from'][:10]} to {g['to'][:10]}", "period": [g["from"], g["to"]],
                           "reason": f"balance moves by {g['unexplained_balance_change_minor']} paise across {g['span_days']} days with no rows: statement period missing", "organisation_type": "bank"})
    summary = defaultdict(int)
    for r in stmt + not_supplied + docs + list(infra.values()):
        summary[r["state"]] += 1
    findings = [finding("coverage_state", f"{r['subject_type']} {r['subject']}: {r['state']}", evidence_class="derived", subject=r["subject"], state=r["state"]) for r in stmt + not_supplied]
    return result(case, "evidence_coverage", COVERAGE_VERSION, findings=findings, limitations=["Coverage describes supplied records only. No record supplied is never treated as zero activity.",
                  "Observed-zero months require balance continuity across the month; without balances the month is UNKNOWN."],
                  statements=stmt, not_supplied=not_supplied, documents=docs, infrastructure=sorted(infra.values(), key=lambda r: r["subject"]), negative_claim_warnings=negatives,
                  next_evidence=needed, states=STATES, summary=dict(summary))
