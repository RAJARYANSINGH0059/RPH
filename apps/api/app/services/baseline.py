"""Graph-only baseline used for honest comparison in the benchmark and the blind challenge.

It is deliberately what a conventional, unsafeguarded link chart does:
  * naive transaction-link traversal — every debit from any statement-holder account is followed to its counterparty and onwards,
    with no corroboration, timing, amount, duplicate or noise filtering; every account reached is "flagged";
  * naive common-identifier matching — any two domains that ever resolved to the same IP are treated as linked (an asserted
    common operator).
It never reads sealed truth; scoring against truth happens in app.synthetic.challenge after a locked submission or in the
benchmark runner. Nothing here is used by the investigative UI as a finding."""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import Case, Entity, Relationship, Transaction

VERSION = "0.1.0"
DEFINITION = ("Graph-only baseline: follow every debit from every statement-holder account to its counterparty and onwards (no corroboration, "
              "timing, amount, duplicate or noise filtering; every account reached is flagged) and treat any two domains sharing an IP as a "
              "common operator. Reproducible and deliberately unsafeguarded; it is the comparison point, not a recommendation.")


def run(db: Session, case: Case) -> dict:
    alias = engine.alias_map(db, case)
    canon = lambda a: alias.get(a, a)  # noqa: E731
    txs = db.execute(select(Transaction).where(Transaction.case_id == case.id)).scalars().all()
    holders = {canon(t.account_ref) for t in txs}
    out_edges: dict[str, set[str]] = defaultdict(set)
    for t in txs:
        if t.direction == "debit" and t.counterparty_ref:
            out_edges[canon(t.account_ref)].add(canon(t.counterparty_ref))
    flagged: set[str] = set()
    seen, frontier = set(holders), list(holders)
    while frontier:
        a = frontier.pop()
        for b in out_edges.get(a, ()):
            flagged.add(b)
            if b not in seen:
                seen.add(b)
                frontier.append(b)
    ents = {e.id: e for e in db.execute(select(Entity).where(Entity.case_id == case.id)).scalars()}
    by_ip: dict[str, set[str]] = defaultdict(set)
    for r in db.execute(select(Relationship).where(Relationship.case_id == case.id, Relationship.relationship_type == "RESOLVES_TO")).scalars():
        d, ip = ents.get(r.source_entity_id), ents.get(r.target_entity_id)
        if d and ip:
            by_ip[ip.key].add(d.key)
    pairs: set[tuple[str, str]] = set()
    for doms in by_ip.values():
        ds = sorted(doms)
        for i in range(len(ds)):
            for j in range(i + 1, len(ds)):
                pairs.add((ds[i], ds[j]))
    return {"version": VERSION, "definition": DEFINITION, "statement_holders": sorted(holders), "flagged_accounts": sorted(flagged),
            "asserted_common_operator_pairs": sorted(pairs), "label": "BASELINE — not a PS05-X finding"}
