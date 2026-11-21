"""NetworkX view of a case: typed graph export, multi-hop path reconstruction, account features, timeline."""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Case, Entity, EvidenceItem, Relationship, Transaction

def _tkey(t: datetime | None) -> tuple[int, float]:
    """Sort key that puts unknown times last and is deterministic."""
    return (1, 0.0) if t is None else (0, t.timestamp())


LEGEND = {
    "directly_observed": "Explicit source record supports the edge",
    "corroborated": "Two or more independent source types agree",
    "derived": "Deterministically computed from source records",
    "candidate": "Possible association; requires human review",
    "contradicted": "Counter-evidence weakens the edge",
    "stale": "Observation outside the relevant time window",
    "insufficient": "Not enough evidence to support the edge",
}


def load_graph(db: Session, case: Case, *, entity_types: set[str] | None = None, levels: set[str] | None = None,
               review: set[str] | None = None, date_from: datetime | None = None, date_to: datetime | None = None) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    ents = db.execute(select(Entity).where(Entity.case_id == case.id)).scalars().all()
    for e in ents:
        if entity_types and e.entity_type not in entity_types:
            continue
        g.add_node(e.id, type=e.entity_type, label=e.label, key=e.key, attributes=e.attributes or {})
    rels = db.execute(select(Relationship).where(Relationship.case_id == case.id)).scalars().all()
    for r in rels:
        if r.source_entity_id not in g or r.target_entity_id not in g:
            continue
        if levels and r.evidence_level.value not in levels:
            continue
        if review and r.review_status.value not in review:
            continue
        if date_from and r.valid_from and r.valid_from < date_from:
            continue
        if date_to and r.valid_from and r.valid_from > date_to:
            continue
        g.add_edge(r.source_entity_id, r.target_entity_id, key=r.id, rel=r)
    return g


def graph_payload(g: nx.MultiDiGraph) -> dict:
    nodes = [{"id": n, "type": d["type"], "label": d["label"], "attributes": {**d["attributes"], "key": d["key"]}} for n, d in g.nodes(data=True)]
    edges = []
    for u, v, k, d in g.edges(keys=True, data=True):
        r: Relationship = d["rel"]
        edges.append({"id": r.id, "source": u, "target": v, "type": r.relationship_type, "evidence_level": r.evidence_level.value,
                      "review_status": r.review_status.value, "valid_from": r.valid_from, "valid_to": r.valid_to,
                      "observed_at": r.observed_at, "heuristic_score": r.heuristic_score, "limitations": r.limitations or [],
                      "attributes": r.attributes or {}})
    by_level: dict[str, int] = defaultdict(int)
    for e in edges:
        by_level[e["evidence_level"]] += 1
    return {"nodes": nodes, "edges": edges, "legend": LEGEND,
            "stats": {"nodes": len(nodes), "edges": len(edges), "edges_by_level": dict(by_level)}}


# ---------------------------------------------------------------- financial reconstruction

def _tx_by_account(db: Session, case: Case) -> dict[str, list[Transaction]]:
    txs = db.execute(select(Transaction).where(Transaction.case_id == case.id)).scalars().all()
    by_acct: dict[str, list[Transaction]] = defaultdict(list)
    for t in txs:
        by_acct[t.account_ref].append(t)
    return by_acct


def alias_map(db: Session, case: Case) -> dict[str, str]:
    """Identifier -> canonical identifier, from derived SAME_ACCOUNT_IDENTIFIER edges (account numbers preferred over VPAs)."""
    ents = {e.id: e for e in db.execute(select(Entity).where(Entity.case_id == case.id, Entity.entity_type.in_(["account", "vpa"]))).scalars()}
    parent: dict[str, str] = {}

    def find(k: str) -> str:
        while parent.get(k, k) != k:
            k = parent[k]
        return k

    for r in db.execute(select(Relationship).where(Relationship.case_id == case.id, Relationship.relationship_type == "SAME_ACCOUNT_IDENTIFIER")).scalars():
        a, b = ents.get(r.source_entity_id), ents.get(r.target_entity_id)
        if not a or not b:
            continue
        ra, rb = find(a.key), find(b.key)
        if ra == rb:
            continue
        # canonical = account-type key if available, else lexicographically smaller (deterministic)
        ta = next((e.entity_type for e in ents.values() if e.key == ra), "vpa")
        tb = next((e.entity_type for e in ents.values() if e.key == rb), "vpa")
        if ta == "account" and tb != "account":
            parent[rb] = ra
        elif tb == "account" and ta != "account":
            parent[ra] = rb
        else:
            parent[max(ra, rb)] = min(ra, rb)
    return {k: find(k) for k in set(e.key for e in ents.values())}


def money_edges(db: Session, case: Case) -> list[dict]:
    """Directed money movements derived from transactions (debits = account->counterparty, credits = counterparty->account).
    Identifiers are canonicalised through derived alias edges so that a VPA and its account number become one node for path purposes."""
    txs = db.execute(select(Transaction).where(Transaction.case_id == case.id)).scalars().all()
    alias = alias_map(db, case)
    edges = []
    seen = set()
    for t in txs:
        if t.amount_minor is None or not t.counterparty_ref or t.direction not in {"debit", "credit"}:
            continue
        acct, cp = alias.get(t.account_ref, t.account_ref), alias.get(t.counterparty_ref, t.counterparty_ref)
        src, dst = (acct, cp) if t.direction == "debit" else (cp, acct)
        key = (src, dst, t.external_reference or t.id, t.amount_minor)
        corroborated = key in seen  # same transfer seen from both statements
        if corroborated:
            for e in edges:
                if (e["src"], e["dst"], e["reference"] or e["tx_id"], e["amount_minor"]) == key:
                    e["corroborated"] = True
            continue
        seen.add(key)
        edges.append({"src": src, "dst": dst, "amount_minor": t.amount_minor, "time": t.datetime_utc,
                      "reference": t.external_reference, "tx_id": t.id, "evidence_item_id": t.evidence_item_id,
                      "precision": t.time_precision, "duplicate": bool(t.duplicate_of), "corroborated": False})
    return edges


def reconstruct_paths(db: Session, case: Case, *, max_hops: int = 4, max_paths: int = 50, window_hours: int = 96) -> list[dict]:
    """Time-ordered multi-hop fund paths. A hop is only chained when it happens after the previous hop
    (or time is unknown) and within the window. Deterministic ordering; no amounts are invented."""
    edges = [e for e in money_edges(db, case) if not e["duplicate"]]
    out_by: dict[str, list[dict]] = defaultdict(list)
    in_count: dict[str, int] = defaultdict(int)
    for e in edges:
        out_by[e["src"]].append(e)
        in_count[e["dst"]] += 1
    # origins: every account with outgoing money; sub-paths contained in a longer path are pruned afterwards
    origins = sorted(out_by)
    paths: list[dict] = []
    internal_cap = max_paths * 6

    def walk(acct: str, path: list[dict], last_time: datetime | None, visited: set[str]):
        if len(paths) >= internal_cap:
            return
        extended = False
        for nxt in sorted(out_by.get(acct, []), key=lambda e: (_tkey(e["time"]), e["amount_minor"], e["tx_id"])):
            if nxt["dst"] in visited or len(path) >= max_hops:
                continue
            if last_time and nxt["time"]:
                if nxt["time"] < last_time or nxt["time"] - last_time > timedelta(hours=window_hours):
                    continue
            extended = True
            walk(nxt["dst"], path + [nxt], nxt["time"] or last_time, visited | {nxt["dst"]})
        if not extended and len(path) >= 1:
            paths.append({"hops": [{k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in h.items()} for h in path],
                          "accounts": [path[0]["src"]] + [h["dst"] for h in path],
                          "total_in_minor": path[0]["amount_minor"], "exit_amount_minor": path[-1]["amount_minor"],
                          "hop_count": len(path), "time_uncertain": any(h["precision"] in {"ambiguous", "unknown"} for h in path),
                          "evidence_item_ids": [h["evidence_item_id"] for h in path]})

    for o in origins:
        walk(o, [], None, {o})
    # prune paths whose hop sequence is a contiguous sub-sequence of a longer path
    seqs = [tuple(h["tx_id"] for h in p["hops"]) for p in paths]
    keep = []
    for i, p in enumerate(paths):
        s = seqs[i]
        contained = False
        for j, other in enumerate(seqs):
            if j != i and len(other) > len(s) and any(other[k:k + len(s)] == s for k in range(len(other) - len(s) + 1)):
                contained = True
                break
        if not contained:
            keep.append(p)
    keep.sort(key=lambda p: (-p["hop_count"], -p["total_in_minor"], p["accounts"][0]))
    return keep[:max_paths]


def account_features(db: Session, case: Case) -> dict[str, dict]:
    """Per-account triage features. Deterministic. Inputs are the money edges only."""
    edges = money_edges(db, case)
    feats: dict[str, dict] = {}
    inc: dict[str, list[dict]] = defaultdict(list)
    outg: dict[str, list[dict]] = defaultdict(list)
    for e in edges:
        outg[e["src"]].append(e)
        inc[e["dst"]].append(e)
    accounts = set(inc) | set(outg)
    by_acct_tx = _tx_by_account(db, case)
    for a in sorted(accounts):
        i, o = inc[a], outg[a]
        total_in = sum(e["amount_minor"] for e in i)
        total_out = sum(e["amount_minor"] for e in o)
        times_in = sorted(e["time"] for e in i if e["time"])
        times_out = sorted(e["time"] for e in o if e["time"])
        holding = []
        for t_out in times_out:
            prior = [t for t in times_in if t <= t_out]
            if prior:
                holding.append((t_out - prior[-1]).total_seconds() / 3600)
        all_times = sorted(times_in + times_out)
        span_h = (all_times[-1] - all_times[0]).total_seconds() / 3600 if len(all_times) > 1 else 0.0
        amounts_out = sorted((e["amount_minor"] for e in o), reverse=True)
        concentration = (amounts_out[0] / total_out) if total_out and amounts_out else 0.0
        own_tx = by_acct_tx.get(a, [])
        feats[a] = {
            "in_degree": len({e["src"] for e in i}),
            "out_degree": len({e["dst"] for e in o}),
            "tx_in": len(i), "tx_out": len(o),
            "total_in_minor": total_in, "total_out_minor": total_out,
            "out_in_ratio": (total_out / total_in) if total_in else (1.0 if total_out else 0.0),
            "median_holding_hours": statistics.median(holding) if holding else -1.0,
            "unique_counterparties": len({e["src"] for e in i} | {e["dst"] for e in o}),
            "velocity_tx_per_day": ((len(i) + len(o)) / (span_h / 24)) if span_h > 0 else float(len(i) + len(o)),
            "amount_concentration": concentration,
            "fan_in": len({e["src"] for e in i}), "fan_out": len({e["dst"] for e in o}),
            "has_own_statement": len(own_tx) > 0,
            "missing_field_ratio": (sum(1 for t in own_tx if t.warnings) / len(own_tx)) if own_tx else 0.0,
            "duplicate_count": sum(1 for e in i + o if e["duplicate"]),
            "time_uncertain_ratio": (sum(1 for e in i + o if e["precision"] in {"ambiguous", "unknown"}) / len(i + o)) if (i or o) else 0.0,
        }
    return feats


def rules_triage(f: dict) -> dict:
    """Transparent rules baseline. Output is a signal label, never a guilt decision."""
    reasons = []
    if f["fan_in"] >= 2 and f["out_in_ratio"] >= 0.7:
        reasons.append("collects_from_multiple_sources_and_forwards_most_funds")
    if 0 <= f["median_holding_hours"] <= 48 and f["tx_out"] >= 1 and f["tx_in"] >= 1:
        reasons.append("short_holding_time")
    if f["fan_out"] >= 3 and f["total_out_minor"] > 0:
        reasons.append("splits_outflow_across_many_accounts")
    if f["velocity_tx_per_day"] >= 4 and (f["tx_in"] + f["tx_out"]) >= 4:
        reasons.append("high_transaction_velocity")
    score = min(100, 25 * len(reasons))
    label = "possible_mule_pattern_requires_review" if len(reasons) >= 2 else ("weak_signal" if reasons else "no_rule_signal")
    return {"label": label, "heuristic_score": score, "reasons": reasons}


def timeline(db: Session, case: Case) -> list[dict]:
    items = db.execute(select(EvidenceItem).where(EvidenceItem.case_id == case.id)).scalars().all()
    events = []
    for it in items:
        if it.source_type == "bank_statement":
            nv = it.normalised_value or {}
            amt = nv.get("amount_minor")
            label = f"{nv.get('direction', '?')} {amt / 100:.2f} {nv.get('account', '')} ↔ {nv.get('counterparty') or 'unknown'}" if amt is not None else "transaction (amount missing)"
            events.append({"id": it.id, "family": "transaction", "time": it.event_time_start,
                           "time_raw": (nv.get("cells") or {}).get("datetime"), "time_precision": it.time_precision,
                           "label": label, "evidence_item_id": it.id, "attributes": {"reference": nv.get("reference")}})
        elif it.source_type == "technical_observation":
            nv = it.normalised_value or {}
            fam = {"dns": "dns", "hosting": "hosting", "cdn": "hosting", "url": "url", "rdap": "registration"}.get(nv.get("type"), "technical")
            events.append({"id": it.id, "family": fam, "time": it.observed_at, "time_raw": str(nv.get("observed_at")),
                           "time_precision": it.time_precision, "label": f"{nv.get('type')} {nv.get('domain') or nv.get('url') or ''} {nv.get('ip') or ''}".strip(),
                           "evidence_item_id": it.id, "attributes": {k: v for k, v in nv.items() if k in {"ttl", "provider", "asn", "source"}}})
        elif it.source_type in {"complaint", "document"} and it.extraction_method.startswith("regex_"):
            nv = it.normalised_value or {}
            events.append({"id": it.id, "family": "url" if nv.get("indicator_kind") in {"url", "domain"} else "complaint",
                           "time": it.observed_at, "time_raw": None, "time_precision": "ingestion_time_only",
                           "label": f"{nv.get('indicator_kind')} mentioned: {nv.get('value')}", "evidence_item_id": it.id,
                           "attributes": {"locator": it.source_locator}})
    events.sort(key=lambda e: (_tkey(e["time"]), e["id"]))
    return events
