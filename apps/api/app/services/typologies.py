"""Explainable account typologies.

The existing rules triage produces a short list of reasons. An investigator needs more than a label: which
transactions triggered a pattern, what the threshold was, what the observed value was, what would explain the same
behaviour innocently, and what the evidence does not cover.

Each typology below answers all of that. Nothing here decides anything: the output is a pattern observed in records,
with the records named, and it says so in its own wording. There is no guilt score, no offender ranking, and an
account is never called a mule. Where the supplied statements cannot answer a question, the typology returns
NOT_ENOUGH_HISTORY rather than a verdict drawn from an absence.

Thresholds are declared in THRESHOLDS, carried in every result, and versioned, so a finding can be reproduced and
argued with.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import timedelta

from sqlalchemy.orm import Session

from app.graph import engine
from app.models import Case

TYPOLOGY_VERSION = "1.0.0"

THRESHOLDS: dict[str, dict] = {
    "rapid_in_out": {
        "max_median_holding_hours": 48,
        "min_forwarded_ratio": 0.70,
        "min_pairs": 2,
        "why": "Money that arrives and leaves again quickly, most of it forwarded, is the shape of a pass-through account.",
    },
    "many_small_credits": {
        "min_credits": 5,
        "max_credit_minor": 50_000_00,
        "min_distinct_senders": 4,
        "min_small_ratio": 0.60,
        "why": "Many small credits from senders with no relationship to each other, pooled and sent on, is a collection pattern.",
    },
    "round_figure_layering": {
        "denominations_minor": [500_00, 1_000_00, 5_000_00, 10_000_00, 25_000_00, 50_000_00],
        "min_round_transfers": 3,
        "min_round_ratio": 0.50,
        "why": "Repeated transfers at exact denominations suggest amounts chosen by a person rather than by a purchase.",
    },
    "dormant_reactivation": {
        "min_dormant_days": 60,
        "min_history_days": 90,
        "burst_window_hours": 72,
        "min_burst_transactions": 3,
        "why": "An account quiet for months that suddenly carries a burst of movement is worth asking about.",
    },
    "repeated_counterparties": {
        "min_repeats": 3,
        "min_shared_accounts": 2,
        "why": "The same counterparty appearing again and again, or across several accounts, links activity that may otherwise look separate.",
    },
    "split_and_merge": {
        "min_splits": 2,
        "min_merges": 2,
        "why": "One credit leaving as several debits, or several credits leaving as one, is how a trail is broken up or recombined.",
    },
    "pass_through": {
        "min_ratio": 0.90,
        "min_total_minor": 10_000_00,
        "why": "An account that forwards almost everything it receives holds nothing of its own.",
    },
}

# Innocent explanations that fit the same records. Shown with every triggered typology, because a pattern that has an
# ordinary explanation is a question, not a finding.
ALTERNATIVES: dict[str, list[str]] = {
    "rapid_in_out": [
        "A person moving their own money between their own accounts, for example to a deposit or a loan repayment.",
        "A business sweeping receipts to a main account at the end of each day.",
    ],
    "many_small_credits": [
        "A trader, tuition teacher, delivery rider or small shop receiving ordinary customer payments.",
        "A collection for an event, a fund or a group expense.",
    ],
    "round_figure_layering": [
        "Rent, fees, instalments and salaries are routinely paid in round amounts.",
        "Cash deposits and ATM limits produce round figures by themselves.",
    ],
    "dormant_reactivation": [
        "An account reopened for a specific purpose: a festival, a sale, a return to work.",
        "The supplied statement may simply not cover the earlier period.",
    ],
    "repeated_counterparties": [
        "A landlord, employer, supplier or family member recurs by nature.",
        "A shared counterparty may be a common service such as a payment aggregator.",
    ],
    "split_and_merge": [
        "Transfer limits force a payment to be split.",
        "Several people contributing to one payment produces a merge.",
    ],
    "pass_through": [
        "An account used only to route money for a household or a business.",
    ],
}


@dataclass
class TypologyResult:
    type: str
    triggered: bool
    status: str                       # observed | not_observed | not_enough_history | not_enough_evidence
    observed_values: dict = field(default_factory=dict)
    thresholds: dict = field(default_factory=dict)
    supporting_transactions: list[str] = field(default_factory=list)
    explanation: str = ""
    alternatives: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def _money(minor: int) -> str:
    return f"₹{minor / 100:,.2f}"


def _edges_by_account(db: Session, case: Case):
    edges = engine.money_edges(db, case)
    inc: dict[str, list[dict]] = defaultdict(list)
    out: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        out[e["src"]].append(e)
        inc[e["dst"]].append(e)
    return inc, out, edges


# ---------------------------------------------------------------------------------------------- typologies

def _rapid_in_out(inc, out) -> TypologyResult:
    t = THRESHOLDS["rapid_in_out"]
    times_in = sorted((e["time"], e) for e in inc if e["time"])
    pairs, supporting, holdings = [], [], []
    for e in sorted((x for x in out if x["time"]), key=lambda x: x["time"]):
        prior = [(ti, ei) for ti, ei in times_in if ti <= e["time"]]
        if not prior:
            continue
        ti, ei = prior[-1]
        hours = (e["time"] - ti).total_seconds() / 3600
        holdings.append(hours)
        if hours <= t["max_median_holding_hours"]:
            pairs.append((ei, e, hours))
            supporting.extend([ei["tx_id"], e["tx_id"]])
    total_in = sum(e["amount_minor"] for e in inc)
    total_out = sum(e["amount_minor"] for e in out)
    ratio = (total_out / total_in) if total_in else 0.0
    if not inc or not out:
        return TypologyResult("rapid_in_out", False, "not_enough_evidence",
                              limitations=["The supplied records show movement in only one direction for this account."],
                              thresholds=t)
    median_hold = statistics.median(holdings) if holdings else -1.0
    triggered = len(pairs) >= t["min_pairs"] and median_hold >= 0 and median_hold <= t["max_median_holding_hours"] and ratio >= t["min_forwarded_ratio"]
    return TypologyResult(
        "rapid_in_out", triggered, "observed" if triggered else "not_observed",
        observed_values={"median_holding_hours": round(median_hold, 2), "fastest_hours": round(min(holdings), 2) if holdings else None,
                         "forwarded_ratio": round(ratio, 3), "quick_pairs": len(pairs),
                         "total_in": _money(total_in), "total_out": _money(total_out)},
        thresholds=t, supporting_transactions=sorted(set(supporting))[:40],
        explanation=(f"{len(pairs)} transfer(s) left within {t['max_median_holding_hours']}h of money arriving; the median wait was "
                     f"{median_hold:.1f}h and {ratio:.0%} of what arrived was forwarded." if triggered else
                     f"Median wait {median_hold:.1f}h and {ratio:.0%} forwarded: below the threshold for this pattern."),
        alternatives=ALTERNATIVES["rapid_in_out"] if triggered else [],
        limitations=["Holding time is measured between transfers that are present in the supplied statements; an unseen movement would change it."])


def _many_small_credits(inc, out) -> TypologyResult:
    t = THRESHOLDS["many_small_credits"]
    smalls = [e for e in inc if e["amount_minor"] <= t["max_credit_minor"]]
    senders = {e["src"] for e in smalls}
    ratio = (len(smalls) / len(inc)) if inc else 0.0
    onward = sum(e["amount_minor"] for e in out)
    triggered = (len(smalls) >= t["min_credits"] and len(senders) >= t["min_distinct_senders"] and ratio >= t["min_small_ratio"])
    return TypologyResult(
        "many_small_credits", triggered, "observed" if triggered else "not_observed",
        observed_values={"small_credits": len(smalls), "distinct_senders": len(senders), "small_credit_ratio": round(ratio, 3),
                         "pooled_in": _money(sum(e["amount_minor"] for e in smalls)), "sent_onward": _money(onward)},
        thresholds=t, supporting_transactions=[e["tx_id"] for e in smalls][:40],
        explanation=(f"{len(smalls)} credit(s) of {_money(t['max_credit_minor'])} or less arrived from {len(senders)} different senders"
                     f" and {_money(onward)} left the account." if triggered else
                     f"{len(smalls)} small credit(s) from {len(senders)} sender(s): below the threshold for this pattern."),
        alternatives=ALTERNATIVES["many_small_credits"] if triggered else [],
        limitations=["Receiving many transfers is ordinary for a business or a collection. The senders' relationship to each other is not established by this pattern."])


def _round_figure(inc, out) -> TypologyResult:
    t = THRESHOLDS["round_figure_layering"]
    denoms = set(t["denominations_minor"])
    moves = list(out)
    rounds = [e for e in moves if e["amount_minor"] in denoms or (e["amount_minor"] % 100_00 == 0 and e["amount_minor"] >= 500_00)]
    ratio = (len(rounds) / len(moves)) if moves else 0.0
    triggered = len(rounds) >= t["min_round_transfers"] and ratio >= t["min_round_ratio"]
    return TypologyResult(
        "round_figure_layering", triggered, "observed" if triggered else "not_observed",
        observed_values={"round_transfers": len(rounds), "outgoing_transfers": len(moves), "round_ratio": round(ratio, 3),
                         "amounts": sorted({_money(e["amount_minor"]) for e in rounds})[:10]},
        thresholds=t, supporting_transactions=[e["tx_id"] for e in rounds][:40],
        explanation=(f"{len(rounds)} of {len(moves)} outgoing transfer(s) were exact round amounts." if triggered else
                     f"{len(rounds)} of {len(moves)} outgoing transfer(s) were round amounts: below the threshold."),
        alternatives=ALTERNATIVES["round_figure_layering"] if triggered else [],
        limitations=["Round amounts are normal for rent, fees, instalments and cash handling. This pattern alone carries little weight."])


def _dormant_reactivation(inc, out) -> TypologyResult:
    t = THRESHOLDS["dormant_reactivation"]
    times = sorted(e["time"] for e in list(inc) + list(out) if e["time"])
    if len(times) < 2:
        return TypologyResult("dormant_reactivation", False, "not_enough_history", thresholds=t,
                              limitations=["Fewer than two dated movements are supplied for this account."])
    span_days = (times[-1] - times[0]).days
    if span_days < t["min_history_days"]:
        return TypologyResult(
            "dormant_reactivation", False, "not_enough_history", thresholds=t,
            observed_values={"period_examined_days": span_days, "first_seen": times[0].isoformat(), "last_seen": times[-1].isoformat()},
            explanation=(f"The supplied statements cover {span_days} day(s). Dormancy cannot be assessed over a period shorter than "
                         f"{t['min_history_days']} days."),
            limitations=["An account is never called dormant from an absence of records. The statement period covering the earlier months would be needed."])
    gaps = [(times[i] - times[i - 1]).days for i in range(1, len(times))]
    longest = max(gaps)
    idx = gaps.index(longest) + 1
    burst_end = times[idx] + timedelta(hours=t["burst_window_hours"])
    burst = [tm for tm in times[idx:] if tm <= burst_end]
    triggered = longest >= t["min_dormant_days"] and len(burst) >= t["min_burst_transactions"]
    return TypologyResult(
        "dormant_reactivation", triggered, "observed" if triggered else "not_observed",
        observed_values={"longest_quiet_days": longest, "period_examined_days": span_days,
                         "reactivated_at": times[idx].isoformat(), "transactions_in_burst": len(burst)},
        thresholds=t, supporting_transactions=[],
        explanation=(f"The account was quiet for {longest} day(s), then carried {len(burst)} movement(s) within "
                     f"{t['burst_window_hours']}h of {times[idx].date()}." if triggered else
                     f"Longest quiet period {longest} day(s) across {span_days} day(s) examined: below the threshold."),
        alternatives=ALTERNATIVES["dormant_reactivation"] if triggered else [],
        limitations=[f"Only the supplied period was examined ({span_days} days). A gap in the records is not evidence of inactivity."])


def _repeated_counterparties(inc, out, all_edges) -> TypologyResult:
    t = THRESHOLDS["repeated_counterparties"]
    counts: dict[str, list[str]] = defaultdict(list)
    for e in inc:
        counts[e["src"]].append(e["tx_id"])
    for e in out:
        counts[e["dst"]].append(e["tx_id"])
    repeats = {cp: ids for cp, ids in counts.items() if len(ids) >= t["min_repeats"]}
    seen_elsewhere: dict[str, set[str]] = defaultdict(set)
    for e in all_edges:
        seen_elsewhere[e["src"]].add(e["dst"])
        seen_elsewhere[e["dst"]].add(e["src"])
    shared = {cp: sorted(acc) for cp, acc in seen_elsewhere.items() if cp in counts and len(acc) >= t["min_shared_accounts"]}
    triggered = bool(repeats) or bool(shared)
    return TypologyResult(
        "repeated_counterparties", triggered, "observed" if triggered else "not_observed",
        observed_values={"recurring": {cp: len(ids) for cp, ids in sorted(repeats.items())[:10]},
                         "counterparties_touching_several_accounts": {cp: len(a) for cp, a in sorted(shared.items())[:10]}},
        thresholds=t, supporting_transactions=sorted({i for ids in repeats.values() for i in ids})[:40],
        explanation=(f"{len(repeats)} counterparty(ies) recur at least {t['min_repeats']} times; "
                     f"{len(shared)} appear with more than one account in this case." if triggered else
                     "No counterparty recurs often enough in the supplied records."),
        alternatives=ALTERNATIVES["repeated_counterparties"] if triggered else [],
        limitations=["A shared counterparty may be a payment aggregator or a common service and does not link the account holders."])


def _split_and_merge(inc, out) -> TypologyResult:
    t = THRESHOLDS["split_and_merge"]
    splits, merges, supporting = 0, 0, []
    for credit in inc:
        if not credit["time"]:
            continue
        window = [e for e in out if e["time"] and credit["time"] <= e["time"] <= credit["time"] + timedelta(hours=72)]
        if len(window) >= t["min_splits"] and sum(e["amount_minor"] for e in window) <= credit["amount_minor"] * 1.05:
            splits += 1
            supporting.append(credit["tx_id"])
            supporting.extend(e["tx_id"] for e in window)
    for debit in out:
        if not debit["time"]:
            continue
        window = [e for e in inc if e["time"] and debit["time"] - timedelta(hours=72) <= e["time"] <= debit["time"]]
        if len(window) >= t["min_merges"] and sum(e["amount_minor"] for e in window) >= debit["amount_minor"] * 0.95:
            merges += 1
            supporting.append(debit["tx_id"])
    triggered = splits > 0 or merges > 0
    return TypologyResult(
        "split_and_merge", triggered, "observed" if triggered else "not_observed",
        observed_values={"credits_split_onward": splits, "debits_funded_by_several_credits": merges},
        thresholds=t, supporting_transactions=sorted(set(supporting))[:40],
        explanation=(f"{splits} credit(s) left as several smaller transfers and {merges} transfer(s) were funded by several credits."
                     if triggered else "No split or merge pattern in the supplied window."),
        alternatives=ALTERNATIVES["split_and_merge"] if triggered else [],
        limitations=["Which specific rupees moved is not established by a split or a merge; see bounded fund provenance for the feasible range."])


def _pass_through(inc, out) -> TypologyResult:
    t = THRESHOLDS["pass_through"]
    total_in = sum(e["amount_minor"] for e in inc)
    total_out = sum(e["amount_minor"] for e in out)
    ratio = (total_out / total_in) if total_in else 0.0
    triggered = total_in >= t["min_total_minor"] and ratio >= t["min_ratio"]
    return TypologyResult(
        "pass_through", triggered, "observed" if triggered else "not_observed",
        observed_values={"received": _money(total_in), "sent_on": _money(total_out), "ratio": round(ratio, 3)},
        thresholds=t,
        explanation=(f"{ratio:.0%} of the {_money(total_in)} received left the account again." if triggered else
                     f"{ratio:.0%} of what was received left again: below the threshold."),
        alternatives=ALTERNATIVES["pass_through"] if triggered else [],
        limitations=["Only movements present in the supplied statements are counted."] + (
            # A ratio above 100% is arithmetically possible and must be explained rather than hidden: more left the
            # account than arrived inside the window, so some of it was already there or arrived in a period that
            # was not supplied. Reading it as "the money that arrived was forwarded" would overstate the records.
            ["More left this account than arrived within the supplied period, so part of what left was already in "
             "the account or arrived in a period that was not supplied. The ratio is not a measure of how much of "
             "the incoming money was forwarded."] if ratio > 1 else []))


# ---------------------------------------------------------------------------------------------- profile

def account_profile(db: Session, case: Case, account_ref: str) -> dict:
    """Every typology for one account, each with its evidence, thresholds and innocent alternatives."""
    inc, out, all_edges = _edges_by_account(db, case)
    i, o = inc.get(account_ref, []), out.get(account_ref, [])
    results = [
        _rapid_in_out(i, o),
        _many_small_credits(i, o),
        _round_figure(i, o),
        _dormant_reactivation(i, o),
        _repeated_counterparties(i, o, all_edges),
        _split_and_merge(i, o),
        _pass_through(i, o),
    ]
    triggered = [r for r in results if r.triggered]
    feats = engine.account_features(db, case).get(account_ref, {})
    legacy = engine.rules_triage(feats) if feats else {"label": "no_rule_signal", "heuristic_score": 0, "reasons": []}

    # The label is a description of what the records show, never a judgement about a person.
    if len(triggered) >= 2:
        label = "possible_mule_pattern_requires_review"
    elif triggered:
        label = "single_pattern_observed_requires_review"
    else:
        label = "no_pattern_observed"

    return {
        "account_ref": account_ref,
        "masked_account_ref": (account_ref[:2] + "*" * max(0, len(account_ref) - 6) + account_ref[-4:]) if len(account_ref) > 6 else account_ref,
        "label": label,
        "patterns_observed": len(triggered),
        "typology_version": TYPOLOGY_VERSION,
        "typologies": [asdict(r) for r in results],
        "rules_triage": legacy,
        "evidence_coverage": {
            "has_own_statement": bool(feats.get("has_own_statement")),
            "transactions_in": len(i), "transactions_out": len(o),
            "time_uncertain_ratio": feats.get("time_uncertain_ratio"),
        },
        "review_required": bool(triggered),
        "limitations": [
            "These are patterns in the supplied records, not findings about any person.",
            "An account holder, the person who controlled the account and whoever benefited may be different people; see the account-control review.",
            "Every triggered pattern is shown with the ordinary explanations that would fit the same records.",
            "No score here expresses a probability of criminal involvement, and nothing is decided automatically.",
        ],
    }


def case_profiles(db: Session, case: Case, *, limit: int = 60) -> dict:
    """Typology profiles for every account in the case, ordered by how many patterns were observed."""
    inc, out, _ = _edges_by_account(db, case)
    accounts = sorted(set(inc) | set(out))[:limit]
    profiles = [account_profile(db, case, a) for a in accounts]
    profiles.sort(key=lambda p: (-p["patterns_observed"], p["account_ref"]))
    return {
        "typology_version": TYPOLOGY_VERSION,
        "thresholds": THRESHOLDS,
        "accounts_examined": len(profiles),
        "accounts_with_a_pattern": sum(1 for p in profiles if p["patterns_observed"]),
        "profiles": profiles,
        "note": "Ordering is by how many patterns the records show, not by suspicion. Review is a human decision.",
    }
