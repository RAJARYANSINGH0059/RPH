"""Proportional intervention and blast-radius simulator (analytical scenarios only).

For a selected account: distinguishes total observed balance, gross inflows, investigated (victim-origin) inflows, onward
transfers, withdrawals, reversals/refunds, observed balance, amount potentially attributable (upper bound), definitely
attributable (lower bound), and unknown. Unrelated activity is identified without labelling it legitimate or illegitimate.
Scenarios are hypothetical comparisons; the system cannot freeze, lien, notify or call anything. Legal availability of any
scenario must be validated by an authorised user.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import Case, Transaction
from app.services import bounded_flow
from app.services.contract import finding, result

INTERVENTION_VERSION = "1.0.0"
SCENARIOS = ["no_action_pending_review", "acquire_evidence_first", "transaction_scoped_amount", "whole_account_restriction"]
DISCLAIMER = ("Hypothetical analytical scenarios for an authorised decision-maker. This is a simulation; nothing here freezes, restricts, liens or notifies anything, "
              "and no scenario is a recommendation. Legal availability must be validated by an authorised officer.")


def exposure(db: Session, case: Case, account_ref: str) -> dict:
    alias = engine.alias_map(db, case)
    canon = alias.get(account_ref, account_ref)
    txs = [t for t in db.execute(select(Transaction).where(Transaction.case_id == case.id)).scalars() if t.amount_minor is not None and not t.duplicate_of]
    own = sorted([t for t in txs if alias.get(t.account_ref, t.account_ref) == canon], key=lambda t: ((0, t.datetime_utc.timestamp()) if t.datetime_utc else (1, 0.0), t.id))
    holders = {alias.get(t.account_ref, t.account_ref) for t in txs}
    paths = [p for p in engine.reconstruct_paths(db, case) if p["accounts"][0] in holders]  # victim-origin: the origin supplied its own statement
    on_path_tx = {h["tx_id"] for p in paths for h in p["hops"]}
    on_path_refs = {h["reference"] for p in paths for h in p["hops"] if h["dst"] == canon and h["reference"]}
    investigated_in = [t for t in own if t.direction == "credit" and (t.id in on_path_tx or (t.external_reference and t.external_reference in on_path_refs))]
    other_in = [t for t in own if t.direction == "credit" and t not in investigated_in]
    reversals = [t for t in own if t.direction == "credit" and any(k in (t.narration_raw or "").upper() for k in ("REV", "REFUND", "RETURN", "CHARGEBACK"))]
    onward = [t for t in own if t.direction == "debit" and (t.id in on_path_tx)]
    withdrawals = [t for t in own if t.direction == "debit" and t.channel == "CASH"]
    other_out = [t for t in own if t.direction == "debit" and t not in onward and t not in withdrawals]
    balance = next((t.balance_after_minor for t in reversed(own) if t.balance_after_minor is not None), None)
    has_statement = bool(own)
    # bounds for victim-origin funds that reached this account (sum over paths whose hop lands here)
    bounds_min = bounds_max = None
    bound_notes = []
    for i, p in enumerate(paths):
        if canon in p["accounts"][1:]:
            bf = bounded_flow.analyse(db, case, path_index=i)
            hops = [h for h in bf.get("hops", []) if h.get("to_account") == canon and h.get("minimum_attributable_minor") is not None]
            if hops:
                bounds_min = (bounds_min or 0) + sum(h["minimum_attributable_minor"] for h in hops)
                bounds_max = (bounds_max or 0) + sum(h["maximum_attributable_minor"] for h in hops)
            elif p["accounts"][1] == canon:
                amt = p["hops"][0]["amount_minor"]
                bounds_min = (bounds_min or 0) + amt
                bounds_max = (bounds_max or 0) + amt
            else:
                bound_notes.append(f"path {i}: attribution into {canon} is UNDETERMINED ({bf.get('attribution_status')})")
    sum_ = lambda xs: sum(t.amount_minor for t in xs)  # noqa: E731
    counterparties_unrelated = sorted({t.counterparty_ref for t in other_in + other_out if t.counterparty_ref})
    ledger = {"observed_balance_minor": balance, "gross_inflows_minor": sum_([t for t in own if t.direction == "credit"]), "investigated_inflows_minor": sum_(investigated_in),
              "other_inflows_minor_not_labelled": sum_(other_in), "reversals_refunds_minor": sum_(reversals), "onward_transfers_on_paths_minor": sum_(onward), "cash_withdrawals_minor": sum_(withdrawals),
              "other_outflows_minor_not_labelled": sum_(other_out), "definitely_attributable_minor_lower_bound": bounds_min, "potentially_attributable_minor_upper_bound": bounds_max,
              "unknown": [] if has_statement else ["no statement for this account: balance, unrelated activity and customer population are UNKNOWN (not zero)"],
              "derivation": {"investigated_inflows": "credits whose transaction id or (reference) appears on a reconstructed victim-origin path", "other_inflows": "all other credits; not labelled legitimate or illegitimate",
                             "onward": "debits that appear as hops on reconstructed paths", "bounds": "bounded_fund_provenance LP per path landing on this account (sum over paths)", "money": "integer paise; duplicates excluded"}}
    unrelated = {"counterparties_observed": counterparties_unrelated, "transactions": len(other_in) + len(other_out), "amount_minor": sum_(other_in) + sum_(other_out),
                 "unknown_population": "Only observed counterparties are listed; unobserved customers/transactions are unknown, not zero.", "labelling": "not labelled legitimate or suspicious"}
    scenarios = []
    for s in SCENARIOS:
        if s == "no_action_pending_review":
            covered, affected = 0, 0
        elif s == "acquire_evidence_first":
            covered, affected = 0, 0
        elif s == "transaction_scoped_amount":
            covered, affected = bounds_max or ledger["investigated_inflows_minor"], 0
        else:
            covered, affected = min(balance, bounds_max) if (balance is not None and bounds_max is not None) else (balance if balance is not None else None), unrelated["amount_minor"]
        scenarios.append({"scenario": s, "hypothetical": True, "investigated_amount_covered_minor": covered, "unrelated_activity_potentially_affected_minor": affected if s == "whole_account_restriction" else 0,
                          "unrelated_counterparties_potentially_affected": len(counterparties_unrelated) if s == "whole_account_restriction" else 0,
                          "uncertainty": {"attribution_bounds": [bounds_min, bounds_max], "balance_known": balance is not None, "statement_supplied": has_statement, "notes": bound_notes},
                          "missing_evidence": ([] if has_statement else [f"statement of {canon}"]) + bound_notes, "alternative_fund_routes": [p["accounts"] for p in paths if canon in p["accounts"][1:-1]][:5],
                          "assumptions": {"whole_account_restriction": "all observed activity of the account is affected; unobserved activity is unknown", "transaction_scoped_amount": "only the bounded investigated amount is in scope; needs identifiable transactions/amount",
                                          "acquire_evidence_first": "no immediate effect; defers until statement/KYC/session records are reviewed", "no_action_pending_review": "no effect"}[s],
                          "legal_availability": "must be validated by an authorised officer; not asserted here"})
    acct_type = "unknown (not inferred from name; intermediary/aggregator/pooled status requires evidence or trusted metadata)"
    return result(case, "intervention_impact", INTERVENTION_VERSION, findings=[finding("exposure", f"{canon}: investigated inflows ₹{ledger['investigated_inflows_minor'] / 100:,.2f}; bounds [{bounds_min}, {bounds_max}] paise; unrelated observed ₹{unrelated['amount_minor'] / 100:,.2f}", evidence_class="derived")],
                  status="completed" if has_statement else "UNDETERMINED", limitations=[DISCLAIMER, "Whole-account balance is never the investigated proceeds.", "Unobserved activity is unknown, not zero."],
                  account=canon, aliases=sorted(k for k, v in alias.items() if v == canon and k != canon), account_type=acct_type, ledger=ledger, unrelated_activity=unrelated, scenarios=scenarios,
                  acknowledgement_required="The viewer must acknowledge that this display is a simulation before scenarios are shown in the UI.", blast_radius={"nodes": [canon] + counterparties_unrelated + [h["src"] for p in paths for h in p["hops"] if h["dst"] == canon] + [h["dst"] for p in paths for h in p["hops"] if h["src"] == canon],
                  "edges": [{"from": t.counterparty_ref or "?", "to": canon, "kind": "investigated_inflow" if t in investigated_in else "other_inflow", "amount_minor": t.amount_minor} for t in own if t.direction == "credit"] +
                           [{"from": canon, "to": t.counterparty_ref or ("CASH" if t.channel == "CASH" else "?"), "kind": "onward_on_path" if t in onward else ("withdrawal" if t in withdrawals else "other_outflow"), "amount_minor": t.amount_minor} for t in own if t.direction == "debit"]})
