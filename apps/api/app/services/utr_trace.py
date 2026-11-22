"""Start a money trail from the victim's own transaction reference.

The product could reconstruct paths across a whole case, but an investigator does not start there. They start with
one complaint carrying one UTR, and they need to follow that money. This module is that entry point.

Two rules shape it.

The first is that an ambiguous reference is never resolved silently. If a reference matches more than one row, the
investigator is shown each candidate with the evidence behind it and chooses; the system does not pick for them,
because picking the wrong origin invents a trail that was never there.

The second is that the trail stops where the records stop. A hop is only followed into an account whose own statement
is in the case. Where it is not, the hop is reported unresolved, naming the statement that would continue it, rather
than guessing at what happened next.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import Case, EvidenceItem, SourceFile, Transaction

TRACE_VERSION = "1.0.0"
MAX_HOPS = 8
CHAIN_WINDOW_HOURS = 240          # how long after a credit an onward transfer may still be chained to it


def _normalise(ref: str) -> str:
    """References are written with spaces, slashes and mixed case across banks and complaints."""
    return re.sub(r"[^A-Z0-9]", "", (ref or "").upper())


def _tx_out(t: Transaction, locator: dict | None, file: SourceFile | None) -> dict:
    return {
        "transaction_id": t.id,
        "reference": t.external_reference,
        "amount_minor": t.amount_minor,
        "amount_raw": t.amount_raw,
        "currency": t.currency,
        "direction": t.direction,
        "account_ref": t.account_ref,
        "counterparty_ref": t.counterparty_ref,
        "counterparty_name": t.counterparty_name_raw,
        "narration": t.narration_raw,
        "channel": t.channel,
        "event_time": t.datetime_utc.isoformat() if t.datetime_utc else None,
        "time_raw": t.datetime_raw,
        "time_precision": t.time_precision,
        "balance_after_minor": t.balance_after_minor,
        "warnings": t.warnings,
        "duplicate_of": t.duplicate_of,
        "evidence_item_id": t.evidence_item_id,
        "source_file": {"id": file.id, "name": file.original_name, "sha256": file.sha256} if file else None,
        "source_locator": locator,
    }


def search(db: Session, case: Case, *, reference: str | None = None, amount_minor: int | None = None,
           account_ref: str | None = None, on_date: str | None = None) -> dict:
    """Find the transaction a complaint refers to, in the statements and in the documents.

    Returns every candidate rather than one answer. Where more than one row matches, the investigator decides.
    """
    wanted = _normalise(reference) if reference else ""
    rows = db.execute(
        select(Transaction, EvidenceItem.source_locator, SourceFile)
        .join(EvidenceItem, Transaction.evidence_item_id == EvidenceItem.id)
        .outerjoin(SourceFile, EvidenceItem.source_file_id == SourceFile.id)
        .where(Transaction.case_id == case.id)
    ).all()

    exact, partial = [], []
    for t, locator, file in rows:
        if amount_minor is not None and t.amount_minor != amount_minor:
            continue
        if account_ref and account_ref not in {t.account_ref, t.counterparty_ref}:
            continue
        if on_date and (not t.datetime_utc or t.datetime_utc.date().isoformat() != on_date[:10]):
            continue
        if wanted:
            have = _normalise(t.external_reference or "")
            in_narration = wanted and wanted in _normalise(t.narration_raw or "")
            if have and have == wanted:
                exact.append(_tx_out(t, locator, file))
            elif in_narration or (have and (wanted in have or have in wanted) and len(wanted) >= 6):
                partial.append({**_tx_out(t, locator, file),
                                "match": "reference appears in the narration" if in_narration else "partial reference match"})
        else:
            partial.append({**_tx_out(t, locator, file), "match": "matched on amount, account or date rather than a reference"})

    # The same reference may also be quoted in a complaint or a message export, which is evidence of what the victim
    # was told even when no statement row carries it.
    mentions = []
    if wanted:
        for item in db.execute(select(EvidenceItem).where(EvidenceItem.case_id == case.id,
                                                          EvidenceItem.source_type != "bank_statement")).scalars():
            haystack = _normalise(f"{item.raw_value or ''} {item.normalised_value or ''}")
            if wanted and wanted in haystack:
                mentions.append({"evidence_item_id": item.id, "source_type": item.source_type,
                                 "locator": item.source_locator, "excerpt": (item.raw_value or "")[:240]})

    status = ("exact_single" if len(exact) == 1 else
              "ambiguous" if len(exact) > 1 else
              "partial_only" if partial else
              "not_found")
    return {
        "version": TRACE_VERSION,
        "query": {"reference": reference, "amount_minor": amount_minor, "account_ref": account_ref, "on_date": on_date},
        "status": status,
        "exact_matches": exact,
        "partial_matches": partial[:25],
        "mentioned_in_documents": mentions[:25],
        "next_step": {
            "exact_single": "One statement row carries this reference. Trace from it.",
            "ambiguous": "More than one row carries this reference. Choose the originating transaction; the system will not choose for you.",
            "partial_only": "No row carries this reference exactly. The near matches below are candidates, not the transaction.",
            "not_found": "No supplied statement carries this reference. The victim's own bank statement for that date would establish it.",
        }[status],
        "limitations": [
            "A reference quoted in a complaint is what the victim was told, which is not the same as a bank record.",
            "Only statements supplied to this case are searched.",
        ],
    }


def trace(db: Session, case: Case, *, transaction_id: str, max_hops: int = MAX_HOPS) -> dict:
    """Follow the money from one originating transaction, hop by hop, stopping where the records stop."""
    root = db.get(Transaction, transaction_id)
    if root is None or root.case_id != case.id:
        raise LookupError("transaction not found in this case")

    alias = engine.alias_map(db, case)
    canon = lambda a: alias.get(a, a) if a else a  # noqa: E731
    edges = engine.money_edges(db, case)
    by_src: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        by_src[e["src"]].append(e)

    locators = {}
    for t, loc, f in db.execute(
        select(Transaction, EvidenceItem.source_locator, SourceFile)
        .join(EvidenceItem, Transaction.evidence_item_id == EvidenceItem.id)
        .outerjoin(SourceFile, EvidenceItem.source_file_id == SourceFile.id)
        .where(Transaction.case_id == case.id)
    ).all():
        locators[t.id] = (loc, f, t)

    statement_holders = {canon(t.account_ref) for t in db.execute(select(Transaction).where(Transaction.case_id == case.id)).scalars()}

    victim_account = canon(root.account_ref) if root.direction == "debit" else canon(root.counterparty_ref)
    first_receiver = canon(root.counterparty_ref) if root.direction == "debit" else canon(root.account_ref)

    def hop_out(e: dict, depth: int, note: str | None = None) -> dict:
        loc, file, t = locators.get(e["tx_id"], (None, None, None))
        return {
            "hop": depth,
            "from_account": e["src"],
            "to_account": e["dst"],
            "amount_minor": e["amount_minor"],
            "reference": e["reference"],
            "event_time": e["time"].isoformat() if e["time"] else None,
            "time_precision": e["precision"],
            "corroborated": e["corroborated"],
            "duplicate": e["duplicate"],
            "transaction_id": e["tx_id"],
            "evidence_item_id": e["evidence_item_id"],
            "source_file": {"id": file.id, "name": file.original_name, "sha256": file.sha256} if file else None,
            "source_locator": loc,
            "note": note,
        }

    root_edge = next((e for e in edges if e["tx_id"] == root.id), None)
    hops: list[dict] = []
    unresolved: list[dict] = []
    if root_edge is None:
        unresolved.append({"account": victim_account, "reason": "the originating row is not a transfer between two identifiers",
                           "needed": "a statement row showing where this money went"})
    else:
        hops.append(hop_out(root_edge, 1, "the victim's own transfer"))

    # Follow onward movements, breadth first, only into accounts whose statements are present.
    frontier = [(first_receiver, root_edge["time"] if root_edge else None, 1)]
    seen_tx = {root.id}
    splits, merges = 0, 0
    while frontier:
        account, after, depth = frontier.pop(0)
        if depth >= max_hops:
            unresolved.append({"account": account, "reason": f"the trail reached the {max_hops}-hop limit",
                               "needed": "continue the trace from this account if the records support it"})
            continue
        if account not in statement_holders:
            unresolved.append({"account": account,
                               "reason": "no statement for this account is in the case, so what left it is unknown",
                               "needed": f"the bank statement of {account} covering the period after the credit"})
            continue
        onward = [e for e in by_src.get(account, [])
                  if e["tx_id"] not in seen_tx and (not after or not e["time"] or after <= e["time"] <= after + timedelta(hours=CHAIN_WINDOW_HOURS))]
        if not onward:
            unresolved.append({"account": account, "reason": "the statement shows no onward transfer within the chaining window",
                               "needed": "a later statement period, or confirmation that the money remained"})
            continue
        if len(onward) > 1:
            splits += 1
        for e in onward:
            seen_tx.add(e["tx_id"])
            hops.append(hop_out(e, depth + 1, "one of several onward transfers" if len(onward) > 1 else None))
            frontier.append((e["dst"], e["time"], depth + 1))

    credits_into = defaultdict(int)
    for h in hops:
        credits_into[h["to_account"]] += 1
    merges = sum(1 for _a, n in credits_into.items() if n > 1)

    accounts = []
    for ref in dict.fromkeys([victim_account] + [h["to_account"] for h in hops]):
        accounts.append({
            "account_ref": ref,
            "masked": (ref[:2] + "*" * max(0, len(ref) - 6) + ref[-4:]) if ref and len(ref) > 6 else ref,
            "role": "victim" if ref == victim_account else "receiving",
            "has_own_statement": ref in statement_holders,
        })

    return {
        "version": TRACE_VERSION,
        "root": {"transaction_id": root.id, "reference": root.external_reference,
                 "amount_minor": root.amount_minor, "event_time": root.datetime_utc.isoformat() if root.datetime_utc else None,
                 "victim_account": victim_account, "first_receiver": first_receiver},
        "hops": hops,
        "accounts": accounts,
        "unresolved": unresolved,
        "shape": {"splits_observed": splits, "merges_observed": merges, "hops": len(hops), "max_hops": max_hops,
                  "chaining_window_hours": CHAIN_WINDOW_HOURS},
        "limitations": [
            "A hop is followed only into an account whose own statement is in the case; every stop is listed with the record that would continue it.",
            "That money moved along this path does not establish that every rupee came from the victim. Bounded fund provenance gives the feasible range.",
            "Chaining uses a time window; a transfer outside it is not linked, and an unknown timestamp is carried as uncertain rather than assumed.",
        ],
        "next": "Open bounded fund provenance for the attributable range on each hop, and the account typologies for the pattern each receiving account shows.",
    }
