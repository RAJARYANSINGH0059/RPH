"""Victim claim and restitution-readiness reconciliation.

Amounts are kept strictly separate and never netted automatically:
  claimed   - what the victim states was lost (entered by an authorised user)
  traced    - sum of distinct source transactions linked to the claim (each transaction counted once per claim, capped at its amount)
  held      - documented holds on accounts the traced money reached (requires a source evidence item; simulated holds are labelled)
  restored  - documented restorations (same evidence rule)
  unresolved- claimed minus traced, floored at zero
Competing claims = two or more claims linked to the same transaction, or claims whose traced inflows into one account exceed
that account's documented held amount. The service reports these; it never allocates.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Case, ClaimTransactionLink, EvidenceItem, FundsRecord, Transaction, VictimClaim

DISCLAIMER = ("Reconciliation aid for authorised Money Restoration Module review. No entitlement, allocation or legal determination is made "
              "here. Hold and restoration figures are shown only when backed by a recorded source document.")


def reconcile(db: Session, case: Case) -> dict:
    claims = db.execute(select(VictimClaim).where(VictimClaim.case_id == case.id).order_by(VictimClaim.created_at)).scalars().all()
    links = db.execute(select(ClaimTransactionLink).join(VictimClaim).where(VictimClaim.case_id == case.id)).scalars().all()
    tx_ids = {l.transaction_id for l in links}
    txs = {t.id: t for t in db.execute(select(Transaction).where(Transaction.id.in_(tx_ids))).scalars()} if tx_ids else {}
    funds = db.execute(select(FundsRecord).where(FundsRecord.case_id == case.id)).scalars().all()
    ev_ids = {f.source_evidence_item_id for f in funds}
    evs = {e.id: e for e in db.execute(select(EvidenceItem).where(EvidenceItem.id.in_(ev_ids))).scalars()} if ev_ids else {}

    by_claim: dict[str, list[ClaimTransactionLink]] = defaultdict(list)
    by_tx: dict[str, list[ClaimTransactionLink]] = defaultdict(list)
    for l in links:
        by_claim[l.claim_id].append(l)
        by_tx[l.transaction_id].append(l)

    # inflow per receiving account, counting each transaction once (not once per claim)
    inflow_by_account: dict[str, int] = defaultdict(int)
    seen_tx: set[str] = set()
    for l in links:
        t = txs.get(l.transaction_id)
        if not t or t.id in seen_tx or t.amount_minor is None:
            continue
        seen_tx.add(t.id)
        dest = t.counterparty_ref if t.direction == "debit" else t.account_ref
        if dest:
            inflow_by_account[dest] += t.amount_minor
    held_by_account: dict[str, int] = defaultdict(int)
    restored_by_account: dict[str, int] = defaultdict(int)
    simulated_accounts: set[str] = set()
    for f in funds:
        (held_by_account if f.kind == "held" else restored_by_account)[f.account_ref] += f.amount_minor
        if f.is_simulated:
            simulated_accounts.add(f.account_ref)

    rows = []
    duplicates = []
    seen_sig: dict[tuple, str] = {}
    for c in claims:
        ls = by_claim.get(c.id, [])
        traced = 0
        tx_rows = []
        for l in ls:
            t = txs.get(l.transaction_id)
            if not t:
                continue
            portion = min(l.amount_minor, t.amount_minor or 0)
            traced += portion
            tx_rows.append({"transaction_id": t.id, "evidence_item_id": t.evidence_item_id, "when": t.datetime_utc.isoformat() if t.datetime_utc else None,
                            "time_precision": t.time_precision, "account": t.account_ref, "counterparty": t.counterparty_ref, "reference": t.external_reference,
                            "amount_minor": t.amount_minor, "attributed_minor": portion, "competing_claims": len(by_tx[t.id]) - 1})
        sig = (c.complaint_ack_no.strip().lower(), c.fir_reference.strip().lower(), c.claimed_loss_minor)
        if c.complaint_ack_no and sig in seen_sig:
            duplicates.append({"claim_id": c.id, "duplicate_of": seen_sig[sig], "reason": "same acknowledgement number, FIR reference and claimed amount"})
        elif c.complaint_ack_no:
            seen_sig[sig] = c.id
        rows.append({"claim_id": c.id, "victim_label": c.victim_label, "complaint_ack_no": c.complaint_ack_no, "fir_reference": c.fir_reference,
                     "status": c.status.value, "claimed_minor": c.claimed_loss_minor, "traced_minor": traced,
                     "over_traced": traced > c.claimed_loss_minor, "unresolved_minor": max(0, c.claimed_loss_minor - traced),
                     "transactions": tx_rows, "competing": any(r["competing_claims"] > 0 for r in tx_rows), "notes": c.notes})

    accounts = []
    for acct in sorted(set(inflow_by_account) | set(held_by_account) | set(restored_by_account)):
        inflow, held, restored = inflow_by_account.get(acct, 0), held_by_account.get(acct, 0), restored_by_account.get(acct, 0)
        claims_on_acct = sorted({l.claim_id for l in links if (t := txs.get(l.transaction_id)) and ((t.counterparty_ref if t.direction == "debit" else t.account_ref) == acct)})
        accounts.append({"account": acct, "traced_inflow_minor": inflow, "documented_held_minor": held, "documented_restored_minor": restored,
                         "held_is_simulated": acct in simulated_accounts, "claims": claims_on_acct,
                         "oversubscribed": held > 0 and inflow > held, "shortfall_minor": max(0, inflow - held) if held > 0 else None,
                         "note": "Multiple claims trace into this account; allocation requires human/legal review." if len(claims_on_acct) > 1 else None})

    totals = {"claimed_minor": sum(r["claimed_minor"] for r in rows), "traced_distinct_minor": sum(inflow_by_account.values()),
              "documented_held_minor": sum(held_by_account.values()), "documented_restored_minor": sum(restored_by_account.values()),
              "unresolved_minor": sum(r["unresolved_minor"] for r in rows),
              "unallocated_held_minor": None}  # intentionally not computed: allocation is a human decision
    return {"disclaimer": DISCLAIMER, "claims": rows, "accounts": accounts, "duplicate_claims": duplicates, "totals": totals,
            "funds_records": [{"id": f.id, "kind": f.kind, "account": f.account_ref, "amount_minor": f.amount_minor, "source_kind": f.source_kind,
                               "is_simulated": f.is_simulated, "reference": f.reference, "source_evidence_item_id": f.source_evidence_item_id,
                               "source_locator": evs[f.source_evidence_item_id].source_locator if f.source_evidence_item_id in evs else None,
                               "source_file_id": evs[f.source_evidence_item_id].source_file_id if f.source_evidence_item_id in evs else None} for f in funds],
            "competing_transactions": [{"transaction_id": tid, "claim_ids": [l.claim_id for l in ls]} for tid, ls in by_tx.items() if len(ls) > 1],
            "export_ready": bool(rows) and all(r["status"] == "export_ready" for r in rows)}
