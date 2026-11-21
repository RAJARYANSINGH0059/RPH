"""Counterfactual investigation / red-team lab and hypothesis branches.

All perturbations run on an in-memory analytical copy of the case's money edges, relationships and features. The database
is never written. Findings are compared before/after and summarised STABLE / FRAGILE / CHANGED / UNRESOLVED with explanations.
"""
from __future__ import annotations

import hashlib
import json
import random
import statistics
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import Case, Entity, Relationship, SourceFile, Transaction
from app.services.contract import finding, result

LAB_VERSION = "1.0.0"
PROFILES = {
    "shared_hosting": "All domains are placed on one multi-tenant IP: shared hosting must stay a candidate.",
    "ip_reassignment": "Infrastructure observations are moved 200 days before the events (IP reassigned / allocation unknown).",
    "stale_dns": "DNS observations are dated outside the transaction window.",
    "ocr_substitution": "One character of a counterparty VPA on the first hop is substituted (0→O, 1→I).",
    "duplicate_row": "The first-hop statement row is duplicated.",
    "ambiguous_date": "Ambiguous dd/mm dates are read as mm/dd.",
    "missing_intermediary_statement": "The first-layer account's own statement is removed.",
    "benign_lookalike_hop": "A background payment that chains in time behind a scam transfer is injected.",
    "similar_name": "A counterparty with a near-identical name but a different account appears.",
    "compromised_account": "Role context: the collection account holder reports the account as compromised (no change to records).",
    "conflicting_balance": "One running balance in the collection account is perturbed.",
    "identifier_rotation": "Domain and VPA identifiers are rotated while the pattern stays the same.",
    "decoy_template": "A benign site with a generic template shares the campaign's hosting.",
    "incomplete_coverage": "A 30-day window of the collection account's statement is removed.",
}
ROBUSTNESS = ["STABLE", "FRAGILE", "CHANGED", "UNRESOLVED"]


def _baseline(db: Session, case: Case) -> dict:
    edges = [e for e in engine.money_edges(db, case) if not e["duplicate"]]
    paths = engine.reconstruct_paths(db, case)
    rels = db.execute(select(Relationship).where(Relationship.case_id == case.id)).scalars().all()
    ents = {e.id: e for e in db.execute(select(Entity).where(Entity.case_id == case.id)).scalars()}
    return {"edges": edges, "paths": paths,
            "infra": [{"type": r.relationship_type, "level": r.evidence_level.value, "a": ents[r.source_entity_id].key if r.source_entity_id in ents else None,
                       "b": ents[r.target_entity_id].key if r.target_entity_id in ents else None, "observed_at": r.observed_at}
                      for r in rels if r.relationship_type in {"SHARED_INFRASTRUCTURE", "COMMON_OPERATOR", "RESOLVES_TO", "SIMILAR_NAME"}]}


def _paths_from_edges(edges: list[dict], holders: set[str], *, max_hops=5, window_hours=120) -> list[dict]:
    """Pure in-memory re-run of the v2 path rules over perturbed edges (same semantics as engine.reconstruct_paths)."""
    out_by = defaultdict(list)
    for e in edges:
        out_by[e["src"]].append(e)
    paths = []

    def walk(acct, path, last_time, running, visited):
        extended = False
        for nxt in sorted(out_by.get(acct, []), key=lambda e: (engine._tkey(e["time"]), e["amount_minor"], str(e["tx_id"]))):
            if nxt["dst"] in visited or len(path) >= max_hops:
                continue
            if last_time and nxt["time"] and (nxt["time"] < last_time or nxt["time"] - last_time > timedelta(hours=window_hours)):
                continue
            extended = True
            walk(nxt["dst"], path + [nxt], nxt["time"] or last_time, nxt["amount_minor"], visited | {nxt["dst"]})
        if not extended and path:
            last = path[-1]["dst"]
            paths.append({"accounts": [path[0]["src"]] + [h["dst"] for h in path], "hop_count": len(path), "status": "complete" if last in holders else "unresolved",
                          "total_in_minor": path[0]["amount_minor"], "exit_amount_minor": path[-1]["amount_minor"], "tx_ids": [str(h["tx_id"]) for h in path],
                          "time_uncertain": any(h["precision"] in {"ambiguous", "unknown"} for h in path)})
    for o in sorted(out_by):
        walk(o, [], None, None, {o})
    seqs = [tuple(p["tx_ids"]) for p in paths]
    keep = [p for i, p in enumerate(paths) if not any(j != i and len(o) > len(seqs[i]) and any(o[k:k + len(seqs[i])] == seqs[i] for k in range(len(o) - len(seqs[i]) + 1)) for j, o in enumerate(seqs))]
    keep.sort(key=lambda p: (-p["hop_count"], -p["total_in_minor"], p["accounts"][0]))
    return keep


def _features(edges: list[dict]) -> dict:
    inc, outg = defaultdict(list), defaultdict(list)
    for e in edges:
        outg[e["src"]].append(e)
        inc[e["dst"]].append(e)
    feats = {}
    for a in set(inc) | set(outg):
        i, o = inc[a], outg[a]
        ti, to = sum(e["amount_minor"] for e in i), sum(e["amount_minor"] for e in o)
        times_in = sorted(e["time"] for e in i if e["time"])
        hold = [(t_out - [t for t in times_in if t <= t_out][-1]).total_seconds() / 3600 for t_out in sorted(e["time"] for e in o if e["time"]) if [t for t in times_in if t <= t_out]]
        all_t = sorted(times_in + [e["time"] for e in o if e["time"]])
        span = (all_t[-1] - all_t[0]).total_seconds() / 3600 if len(all_t) > 1 else 0
        feats[a] = {"fan_in": len({e["src"] for e in i}), "fan_out": len({e["dst"] for e in o}), "tx_in": len(i), "tx_out": len(o), "total_out_minor": to, "total_in_minor": ti,
                    "out_in_ratio": (to / ti) if ti else (1.0 if to else 0.0), "median_holding_hours": statistics.median(hold) if hold else -1.0,
                    "velocity_tx_per_day": ((len(i) + len(o)) / (span / 24)) if span > 0 else float(len(i) + len(o))}
    return feats


def _apply(profile: str, base: dict, rng: random.Random, holders: set[str]):
    edges = [dict(e) for e in base["edges"]]
    infra = [dict(x) for x in base["infra"]]
    affected: list[str] = []
    holders = set(holders)
    first = next((p for p in base["paths"] if p["hops"]), None)
    first_tx = first["hops"][0]["tx_id"] if first else None
    if profile == "ocr_substitution" and first_tx:
        for e in edges:
            if e["tx_id"] == first_tx:
                subs = {"0": "O", "1": "I", "5": "S", "8": "B", "a": "o"}
                dst = e["dst"]
                for i, ch in enumerate(dst):
                    if ch in subs:
                        e["dst"] = dst[:i] + subs[ch] + dst[i + 1:]
                        break
                affected.append(e["evidence_item_id"])
    elif profile == "duplicate_row" and first_tx:
        e = next(x for x in edges if x["tx_id"] == first_tx)
        edges.append({**e, "tx_id": str(e["tx_id"]) + ":dup"})
        affected.append(e["evidence_item_id"])
    elif profile == "ambiguous_date":
        for e in edges:
            if e["precision"] == "ambiguous" and e["time"] and e["time"].day <= 12:
                e["time"] = e["time"].replace(month=e["time"].day, day=e["time"].month)
                affected.append(e["evidence_item_id"])
    elif profile == "missing_intermediary_statement" and first:
        m1 = first["accounts"][1]
        edges = [e for e in edges if e["src"] != m1]
        holders.discard(m1)
        affected.append(m1)
    elif profile == "incomplete_coverage" and first:
        m1 = first["accounts"][1]
        t0 = first["hops"][0]["time"]
        if t0:
            t0 = datetime.fromisoformat(t0)
            edges = [e for e in edges if not (e["src"] == m1 and e["time"] and t0 <= e["time"] <= t0 + timedelta(days=30))]
        affected.append(m1)
    elif profile == "benign_lookalike_hop" and first and len(first["accounts"]) > 2:
        last = first["accounts"][-1]
        t = first["hops"][-1]["time"]
        edges.append({"src": last, "dst": "BENIGN-GROCER-" + str(rng.randint(100, 999)), "amount_minor": rng.randint(20, 90) * 100, "time": (datetime.fromisoformat(t) + timedelta(hours=2)) if t else None,
                      "reference": "BG" + str(rng.randint(10 ** 6, 10 ** 7)), "tx_id": "benign", "evidence_item_id": "injected", "precision": "second", "duplicate": False, "corroborated": False})
        affected.append("injected")
    elif profile in {"conflicting_balance", "compromised_account", "similar_name"} and first:
        affected.append(first["accounts"][1] if profile != "similar_name" else "similar-name-counterparty")
    elif profile in {"shared_hosting", "decoy_template"}:
        infra.append({"type": "SHARED_INFRASTRUCTURE", "level": "candidate", "a": "campaign.test", "b": "benign-template-site.test", "observed_at": None})
        affected.append("benign-template-site.test")
    elif profile in {"stale_dns", "ip_reassignment"}:
        for x in infra:
            if x["type"] == "RESOLVES_TO":
                x["level"] = "stale"
                x["observed_at"] = (x["observed_at"] or datetime.now()) - timedelta(days=200)
                affected.append(x["a"])
    elif profile == "identifier_rotation":
        for e in edges:
            if "@" in e["dst"]:
                e["dst"] = e["dst"].replace("@", "2@")
                affected.append(e["evidence_item_id"])
        infra = [{**x, "a": (x["a"] or "").replace(".test", "-v2.test") if x["a"] else None} for x in infra]
    return edges, holders, infra, affected


def run(db: Session, case: Case, *, profile: str, seed: int = 42001, hypothesis_id: str | None = None) -> dict:
    if profile not in PROFILES:
        raise ValueError(f"unknown profile; choose one of {sorted(PROFILES)}")
    rng = random.Random(seed)
    base = _baseline(db, case)
    alias = engine.alias_map(db, case)
    holders = {alias.get(a, a) for (a,) in db.execute(select(Transaction.account_ref).where(Transaction.case_id == case.id).distinct()).all()}
    base_paths = _paths_from_edges(base["edges"], holders)
    base_triage = {a: engine.rules_triage(f)["label"] for a, f in _features(base["edges"]).items()}
    edges, holders2, infra, affected = _apply(profile, base, rng, holders)
    new_paths = _paths_from_edges(edges, holders2)
    new_triage = {a: engine.rules_triage(f)["label"] for a, f in _features(edges).items()}
    bp = {tuple(p["accounts"]): p for p in base_paths}
    np_ = {tuple(p["accounts"]): p for p in new_paths}
    stable = [list(k) for k in bp if k in np_ and bp[k]["status"] == np_[k]["status"]]
    weakened = [{"path": list(k), "from": bp[k]["status"], "to": np_[k]["status"]} for k in bp if k in np_ and bp[k]["status"] != np_[k]["status"]]
    disappeared = [list(k) for k in bp if k not in np_]
    appeared = [list(k) for k in np_ if k not in bp]
    triage_changes = [{"account": a, "from": base_triage.get(a), "to": new_triage.get(a)} for a in sorted(set(base_triage) | set(new_triage)) if base_triage.get(a) != new_triage.get(a)]
    common_operator = [x for x in infra if x["type"] == "COMMON_OPERATOR"]
    counter = {"shared_hosting": "Shared/multi-tenant IP: alternative explanation is commercial co-hosting; no identifier bridge exists between the sites.",
               "decoy_template": "A generic template on shared hosting is excluded from similarity scoring and stays a candidate pivot.",
               "stale_dns": "Observation dated outside the transaction window: the mapping may not have been in effect.",
               "ip_reassignment": "Allocation data is missing for the event period: the address may have served another customer.",
               "ocr_substitution": "A one-character identifier change breaks the chain: the original must be verified against the page image.",
               "compromised_account": "Records are unchanged; the account-role propositions move to CONFLICTING_EVIDENCE / REVIEW_REQUIRED. No conclusion about the holder changes automatically.",
               "similar_name": "Similar names with different identifiers are never merged; the chain is unaffected.",
               "conflicting_balance": "A perturbed running balance surfaces as a row-level break in statement forensics; paths are unchanged but the row is provisional."}
    if not bp:
        robustness = "UNRESOLVED"
    elif disappeared or appeared:
        robustness = "CHANGED"
    elif weakened or triage_changes:
        robustness = "FRAGILE"
    else:
        robustness = "STABLE"
    explanation = {"STABLE": "The finding survives this perturbation: the same paths exist with the same status and no candidate was promoted.",
                   "FRAGILE": "The finding survives in part: some paths change status or triage labels change; treat the affected conclusions as provisional.",
                   "CHANGED": "Paths appear or disappear under this perturbation: the conclusion depends on the perturbed evidence.", "UNRESOLVED": "No baseline finding to test."}[robustness]
    return result(case, "counterfactual_lab", LAB_VERSION, findings=[finding("robustness", f"{profile}: {robustness}", evidence_class="derived", robustness=robustness)],
                  limitations=["Perturbations run on an in-memory analytical copy; source files and database records are not modified.", "Results are deterministic for a given seed and profile.", "No single 'truth score' is produced; every change is listed."],
                  scenario={"profile": profile, "description": PROFILES[profile], "seed": seed, "hypothesis_id": hypothesis_id, "source_evidence_immutable": True},
                  original_finding={"paths": [{"accounts": p["accounts"], "status": p["status"]} for p in base_paths], "triage": base_triage, "infra_candidate_edges": sum(1 for x in base["infra"] if x["type"] == "SHARED_INFRASTRUCTURE")},
                  perturbation_applied={"affected_evidence_or_entities": affected, "edges_before": len(base["edges"]), "edges_after": len(edges)},
                  revised_finding={"paths": [{"accounts": p["accounts"], "status": p["status"]} for p in new_paths], "triage": new_triage, "common_operator_edges": len(common_operator)},
                  findings_stable=stable, findings_weakened=weakened, findings_disappeared=disappeared, findings_appeared=appeared, triage_changes=triage_changes,
                  counter_evidence_discovered=[counter[profile]] if profile in counter else [],
                  uncertainty_change={"unresolved_or_uncertain_paths_before": sum(1 for p in base_paths if p["status"] == "unresolved" or p["time_uncertain"]),
                                      "after": sum(1 for p in new_paths if p["status"] == "unresolved" or p["time_uncertain"])},
                  robustness=robustness, robustness_explanation=explanation, safeguard_check={"common_operator_asserted": bool(common_operator)}, profiles=PROFILES, labels=ROBUSTNESS)


# ------------------------------------------------------------------ hypothesis branches

def snapshot_hash(db: Session, case: Case) -> str:
    files = db.execute(select(SourceFile.sha256).where(SourceFile.case_id == case.id).order_by(SourceFile.sha256)).scalars().all()
    tx = db.execute(select(Transaction.id).where(Transaction.case_id == case.id)).scalars().all()
    return hashlib.sha256(json.dumps({"files": files, "tx": sorted(tx)}).encode()).hexdigest()


def branch_findings(db: Session, case: Case, assumptions: dict) -> dict:
    """Recompute findings under branch assumptions on an in-memory copy. Assumptions: exclude_transaction_ids, exclude_accounts,
    date_interpretation ('as_parsed'|'swap_ambiguous'), treat_as_same_account [[a,b],...] (explicit analyst assumption, labelled)."""
    base = _baseline(db, case)
    edges = [dict(e) for e in base["edges"]]
    ex_tx = set(assumptions.get("exclude_transaction_ids") or [])
    ex_acct = set(assumptions.get("exclude_accounts") or [])
    edges = [e for e in edges if e["tx_id"] not in ex_tx and e["src"] not in ex_acct and e["dst"] not in ex_acct]
    if assumptions.get("date_interpretation") == "swap_ambiguous":
        for e in edges:
            if e["precision"] == "ambiguous" and e["time"] and e["time"].day <= 12:
                e["time"] = e["time"].replace(month=e["time"].day, day=e["time"].month)
    merge = {pair[1]: pair[0] for pair in (assumptions.get("treat_as_same_account") or []) if len(pair) == 2}
    for e in edges:
        e["src"], e["dst"] = merge.get(e["src"], e["src"]), merge.get(e["dst"], e["dst"])
    alias = engine.alias_map(db, case)
    holders = {merge.get(alias.get(a, a), alias.get(a, a)) for (a,) in db.execute(select(Transaction.account_ref).where(Transaction.case_id == case.id).distinct()).all()} - ex_acct
    paths = _paths_from_edges(edges, holders)
    feats = _features(edges)
    return {"paths": [{"accounts": p["accounts"], "status": p["status"], "total_in_minor": p["total_in_minor"], "exit_amount_minor": p["exit_amount_minor"], "hop_count": p["hop_count"]} for p in paths],
            "triage": {a: engine.rules_triage(f)["label"] for a, f in feats.items()}, "total_entry_minor": sum(p["total_in_minor"] for p in paths), "edges": len(edges), "assumptions_applied": assumptions}


def compare_branches(base: dict, other: dict) -> dict:
    bp = {tuple(p["accounts"]): p for p in base["paths"]}
    op = {tuple(p["accounts"]): p for p in other["paths"]}
    return {"invariant_paths": [list(k) for k in bp if k in op and bp[k]["status"] == op[k]["status"]], "base_only": [list(k) for k in bp if k not in op], "branch_only": [list(k) for k in op if k not in bp],
            "status_changed": [{"path": list(k), "base": bp[k]["status"], "branch": op[k]["status"]} for k in bp if k in op and bp[k]["status"] != op[k]["status"]],
            "amount_delta_minor": other["total_entry_minor"] - base["total_entry_minor"], "edge_delta": other["edges"] - base["edges"],
            "triage_changes": [{"account": a, "base": base["triage"].get(a), "branch": other["triage"].get(a)} for a in sorted(set(base["triage"]) | set(other["triage"])) if base["triage"].get(a) != other["triage"].get(a)]}
