"""Investigation completeness: interpretable checklist with component contributions. Not a probability of guilt or of a solved case."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import Case, EvidenceRequest, Hypothesis, PaymentInstruction, Relationship, Transaction
from app.services import claims, coverage
from app.services.contract import finding, result

COMPLETENESS_VERSION = "1.0.0"


def checklist(db: Session, case: Case) -> dict:
    paths = engine.reconstruct_paths(db, case)
    cov = coverage.coverage_report(db, case)
    rec = claims.reconcile(db, case)
    txs = db.execute(select(Transaction).where(Transaction.case_id == case.id)).scalars().all()
    rels = db.execute(select(Relationship).where(Relationship.case_id == case.id)).scalars().all()
    reqs = db.execute(select(EvidenceRequest).where(EvidenceRequest.case_id == case.id)).scalars().all()
    hyps = db.execute(select(Hypothesis).where(Hypothesis.case_id == case.id)).scalars().all()
    pis = db.execute(select(PaymentInstruction).where(PaymentInstruction.case_id == case.id)).scalars().all()
    items = []

    def item(key, label, open_count, weight, detail=None):
        items.append({"key": key, "label": label, "open": open_count, "weight": weight, "contribution": 0 if open_count else weight, "detail": detail})

    unresolved = [p for p in paths if p["status"] == "unresolved"]
    item("statements_missing", "Missing statements for accounts on reconstructed paths", len(cov["not_supplied"]), 20, [r["subject"] for r in cov["not_supplied"]][:8])
    item("coverage_gaps", "Missing statement periods (balance discontinuities)", sum(len(s["gaps"]) for s in cov["statements"]), 10, [f"{s['subject']} {g['from'][:10]}→{g['to'][:10]}" for s in cov["statements"] for g in s["gaps"]][:8])
    item("missing_utr", "Transactions without a reference/UTR", sum(1 for t in txs if not t.external_reference and t.amount_minor), 5)
    item("unknown_beneficiaries", "Transfers with unknown counterparty", sum(1 for t in txs if not t.counterparty_ref and t.amount_minor), 5)
    item("broken_paths", "Paths ending at an account without a statement", len(unresolved), 15, [p["accounts"][-1] for p in unresolved][:8])
    item("contradictory_balances", "Statement files with balance reconciliation mismatches", sum(1 for s in cov["statements"] if s["balance_mismatches_within_period"]), 5)
    item("unreviewed_infra_candidates", "Unreviewed shared-infrastructure candidates", sum(1 for r in rels if r.relationship_type == "SHARED_INFRASTRUCTURE" and r.review_status.value == "unreviewed"), 5)
    item("stale_observations", "Stale infrastructure observations not reviewed", sum(1 for r in rels if r.evidence_level.value == "stale" and r.review_status.value == "unreviewed"), 5)
    item("historical_dns_missing", "Domains with only current or out-of-window observations", sum(1 for i in cov["infrastructure"] if i["state"] in {"CURRENT_ONLY", "HISTORICAL_UNKNOWN"}), 5)
    item("open_requests", "Evidence requests not yet fulfilled/closed", sum(1 for r in reqs if r.status not in {"received", "reviewed", "closed", "rejected", "unavailable", "expired"}), 5)
    item("unmatched_instructions", "Payment instructions without a transaction match", sum(1 for p in pis if not any(r.method_name == "payment_bridge" and (r.attributes or {}).get("instruction_id") == p.id for r in rels)), 5)
    item("unreconciled_funds", "Claims with unresolved (claimed − traced) amounts", sum(1 for c in rec["claims"] if c["unresolved_minor"] > 0), 10)
    item("open_hypotheses", "Hypotheses open / disputed without review", sum(1 for h in hyps if h.status in {"open", "disputed"}), 5)
    total_w = sum(i["weight"] for i in items)
    got = sum(i["contribution"] for i in items)
    return result(case, "investigation_completeness", COMPLETENESS_VERSION, findings=[finding("completeness", f"{got}/{total_w} checklist points satisfied", evidence_class="derived")],
                  limitations=["A checklist of evidence completeness; not a probability of guilt, conviction or a solved case.", "Weights are editorial and shown per component."],
                  items=items, score={"satisfied": got, "total": total_w, "percent": round(100 * got / total_w) if total_w else 0}, open_items=[i for i in items if i["open"]])
