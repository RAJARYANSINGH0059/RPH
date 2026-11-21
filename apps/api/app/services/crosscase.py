"""Cross-case correlation (query-time). Permission-aware: only cases the caller can access are ever read.

Match classes (not probabilities):
  exact        - the same normalised identifier (account / VPA / phone / email / reference / URL / domain) appears in >= 2 cases
  corroborated - exact identifier match PLUS a transaction bridge: same external reference AND amount in both cases, within 72 h
  derived      - transaction bridge (reference + amount + time) without a shared identifier entity
  candidate    - shared IP / hosting only (multi-tenant counter-explanation attached), or a time-inconsistent bridge
  stale        - the supporting infrastructure observation is itself stale in its case
Similar names, same bank or same provider never create a link; they are listed under `rejected` so the investigator sees
what was NOT asserted and why. Entities are never merged across cases.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import user_can_access_case
from app.services.adversary import ALTERNATIVES as _ALT
from app.models import (Case, CaseMembership, Entity, EvidenceItem, Relationship, RelationshipEvidence, Role, SourceFile,
                        Transaction, User)

ALGORITHM_VERSION = "1.0.0"
IDENTIFIER_TYPES = {"account", "vpa", "phone", "email", "reference", "url", "domain"}
STRONG_IDENTITY_TYPES = {"account", "vpa", "phone", "email"}


def _norm(entity_type: str, key: str) -> str:
    k = key.strip()
    if entity_type in {"vpa", "email", "domain", "url"}:
        k = k.lower()
    if entity_type == "account":
        k = k.replace(" ", "").upper()
    return k


def authorised_cases(db: Session, user: User, case_ids: list[str] | None = None) -> list[Case]:
    """Cases the user may read. With explicit ids, every id must be accessible (else the caller gets a 404-style refusal)."""
    if case_ids is not None:
        cases = [db.get(Case, cid) for cid in dict.fromkeys(case_ids)]
        if any(c is None or not user_can_access_case(db, user, c) for c in cases):
            return []
        return [c for c in cases if c]
    q = select(Case)
    if user.role != Role.admin:
        member_ids = select(CaseMembership.case_id).where(CaseMembership.user_id == user.id)
        q = q.where((Case.created_by == user.id) | (Case.id.in_(member_ids)))
    return list(db.execute(q).scalars())


def _evidence_refs(db: Session, case_ids: list[str], entity_ids: set[str]) -> dict[str, list[dict]]:
    """entity_id -> up to 3 provenance refs {evidence_item_id, source_file_id, sha256, file, locator, method, observed_at, event_time}."""
    if not entity_ids:
        return {}
    rels = db.execute(select(Relationship).where(Relationship.case_id.in_(case_ids),
                                                 (Relationship.source_entity_id.in_(entity_ids)) | (Relationship.target_entity_id.in_(entity_ids)))).scalars().all()
    rel_ids = [r.id for r in rels]
    ev_links = db.execute(select(RelationshipEvidence).where(RelationshipEvidence.relationship_id.in_(rel_ids))).scalars().all() if rel_ids else []
    ev_ids = {x.evidence_item_id for x in ev_links}
    evs = {e.id: e for e in db.execute(select(EvidenceItem).where(EvidenceItem.id.in_(ev_ids))).scalars()} if ev_ids else {}
    files = {f.id: f for f in db.execute(select(SourceFile).where(SourceFile.case_id.in_(case_ids))).scalars()}
    by_rel: dict[str, list[str]] = defaultdict(list)
    for x in ev_links:
        by_rel[x.relationship_id].append(x.evidence_item_id)
    out: dict[str, list[dict]] = defaultdict(list)
    for r in sorted(rels, key=lambda r: (r.relationship_type, r.id)):
        for eid in by_rel.get(r.id, [])[:2]:
            e = evs.get(eid)
            if not e:
                continue
            f = files.get(e.source_file_id or "")
            for ent_id in (r.source_entity_id, r.target_entity_id):
                if ent_id in entity_ids and len(out[ent_id]) < 3:
                    out[ent_id].append({"evidence_item_id": e.id, "case_id": e.case_id, "source_file_id": e.source_file_id,
                                        "file": f.original_name if f else None, "sha256": f.sha256 if f else None, "locator": e.source_locator,
                                        "method": e.extraction_method, "parser": f"{e.parser_name}@{e.parser_version}",
                                        "event_time": e.event_time_start.isoformat() if e.event_time_start else None,
                                        "time_precision": e.time_precision, "observed_at": e.observed_at.isoformat() if e.observed_at else None,
                                        "quality_flags": e.quality_flags or [], "relationship_type": r.relationship_type,
                                        "relationship_level": r.evidence_level.value})
    return out


def correlate(db: Session, user: User, case_ids: list[str]) -> dict | None:
    cases = authorised_cases(db, user, case_ids)
    if not cases or len(cases) != len(dict.fromkeys(case_ids)):
        return None
    cids = [c.id for c in cases]
    titles = {c.id: c.title for c in cases}
    synthetic = {c.id: c.is_synthetic for c in cases}
    ents = db.execute(select(Entity).where(Entity.case_id.in_(cids))).scalars().all()
    rels = db.execute(select(Relationship).where(Relationship.case_id.in_(cids))).scalars().all()
    txs = db.execute(select(Transaction).where(Transaction.case_id.in_(cids))).scalars().all()
    ent_by_id = {e.id: e for e in ents}

    # ---- 1. exact identifier matches across cases
    groups: dict[tuple[str, str], dict[str, list[Entity]]] = defaultdict(lambda: defaultdict(list))
    for e in ents:
        if e.entity_type in IDENTIFIER_TYPES:
            groups[(e.entity_type, _norm(e.entity_type, e.key))][e.case_id].append(e)
    exact: list[dict] = []
    exact_ids: set[str] = set()
    for (etype, key), per_case in sorted(groups.items()):
        if len(per_case) < 2:
            continue
        exact.append({"kind": "identifier", "entity_type": etype, "value": key, "cases": sorted(per_case),
                      "entity_ids": {cid: [e.id for e in es] for cid, es in per_case.items()}})
        for es in per_case.values():
            exact_ids.update(e.id for e in es)

    # ---- 2. transaction bridges: same reference + amount in two cases; time consistency within 72 h
    by_ref: dict[tuple[str, int], dict[str, list[Transaction]]] = defaultdict(lambda: defaultdict(list))
    for t in txs:
        if t.external_reference and t.amount_minor is not None:
            by_ref[(t.external_reference.strip().upper(), t.amount_minor)][t.case_id].append(t)
    bridges: list[dict] = []
    for (ref, amt), per_case in sorted(by_ref.items()):
        if len(per_case) < 2:
            continue
        times = [t.datetime_utc for ts in per_case.values() for t in ts if t.datetime_utc]
        consistent = (max(times) - min(times) <= timedelta(hours=72)) if len(times) >= 2 else None
        precision_flags = sorted({t.time_precision for ts in per_case.values() for t in ts if t.time_precision in {"ambiguous", "unknown"}})
        dup = any(t.duplicate_of for ts in per_case.values() for t in ts)
        bridges.append({"kind": "transaction_bridge", "reference": ref, "amount_minor": amt, "cases": sorted(per_case),
                        "transaction_ids": {cid: [t.id for t in ts] for cid, ts in per_case.items()},
                        "evidence_item_ids": {cid: [t.evidence_item_id for t in ts] for cid, ts in per_case.items()},
                        "accounts": {cid: sorted({x for t in ts for x in (t.account_ref, t.counterparty_ref) if x}) for cid, ts in per_case.items()},
                        "time_consistent": consistent, "time_precision_flags": precision_flags, "duplicate_flag": dup,
                        "event_times": {cid: [t.datetime_utc.isoformat() if t.datetime_utc else None for t in ts] for cid, ts in per_case.items()}})

    # ---- 3. shared infrastructure across cases (candidate only)
    ip_cases: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))  # ip key -> case -> domains
    stale_ips: set[str] = set()
    for r in rels:
        if r.relationship_type == "RESOLVES_TO":
            d, ip = ent_by_id.get(r.source_entity_id), ent_by_id.get(r.target_entity_id)
            if d and ip:
                ip_cases[ip.key][r.case_id].add(d.key)
                if r.evidence_level.value == "stale":
                    stale_ips.add(f"{ip.key}|{r.case_id}")
    infra: list[dict] = []
    for ip, per_case in sorted(ip_cases.items()):
        if len(per_case) < 2:
            continue
        doms = {cid: sorted(ds) for cid, ds in per_case.items()}
        same_domain = len(set.intersection(*[set(v) for v in doms.values()])) > 0
        stale = any(f"{ip}|{cid}" in stale_ips for cid in per_case)
        infra.append({"kind": "shared_infrastructure", "ip": ip, "cases": sorted(per_case), "domains": doms, "same_domain_in_both": same_domain,
                      "match_class": "stale" if stale else ("exact" if same_domain else "candidate"),
                      "counter_evidence": [] if same_domain else ["Different domains on one IP: unrelated sites commonly share multi-tenant hosting/CDN addresses. No identifier bridges the cases through this IP."],
                      "limitations": ["shared_ip_is_not_proof_of_common_control", "dns_mapping_valid_only_at_observation_time"] + (["observation_stale_in_at_least_one_case"] if stale else []),
                      "challenge_state": "stale" if stale else ("corroborated" if same_domain else "candidate"),
                      "alternatives": [{"hypothesis": a, "why_relevant": b, "discriminating_evidence": c} for a, b, c in _ALT["SHARED_INFRASTRUCTURE"]]})

    # ---- 4. similar names across cases: NEVER a link; reported as rejected
    named = [(e, ((e.attributes or {}).get("name_raw") or e.label)) for e in ents if e.entity_type in {"account", "vpa"} and ((e.attributes or {}).get("name_raw") or e.label != e.key)]
    rejected: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()
    for i in range(len(named)):
        for j in range(i + 1, len(named)):
            (a, na), (b, nb) = named[i], named[j]
            if a.case_id == b.case_id or not na or not nb or _norm(a.entity_type, a.key) == _norm(b.entity_type, b.key):
                continue
            ratio = difflib.SequenceMatcher(None, na.lower(), nb.lower()).ratio()
            if ratio >= 0.85 and (a.id, b.id) not in seen_pairs:
                seen_pairs.add((a.id, b.id))
                rejected.append({"kind": "similar_name_not_identity", "cases": sorted({a.case_id, b.case_id}), "name_a": na, "name_b": nb,
                                 "identifier_a": a.key, "identifier_b": b.key, "similarity": round(ratio, 3),
                                 "reason": "Similar names with different identifiers do not establish the same person or account."})

    # ---- classification of identifier matches using bridges
    bridge_cases = {tuple(b["cases"]) for b in bridges if b["time_consistent"] is not False}
    links: list[dict] = []
    refs = _evidence_refs(db, cids, exact_ids)
    for m in exact:
        strong = m["entity_type"] in STRONG_IDENTITY_TYPES
        has_bridge = any(set(bc) <= set(m["cases"]) for bc in bridge_cases)
        if strong and has_bridge:
            cls = "corroborated"
        elif strong:
            cls = "exact"
        else:
            cls = "exact"  # exact indicator (URL/domain/reference) - still not identity of a person
        lim = ["exact_string_match_after_normalisation"]
        if not strong:
            lim.append("indicator_match_is_not_identity_of_a_person_or_operator")
        if m["entity_type"] == "reference":
            lim.append("references_can_be_truncated_or_reused_verify_amount_and_date")
        links.append({"kind": "identifier", "match_class": cls, "entity_type": m["entity_type"], "value": m["value"], "cases": m["cases"],
                      "case_titles": {c: titles[c] for c in m["cases"]}, "evidence": {cid: [x for eid in eids for x in refs.get(eid, [])] for cid, eids in m["entity_ids"].items()},
                      "method": {"name": "crosscase_exact_identifier", "version": ALGORITHM_VERSION}, "limitations": lim, "counter_evidence": []})
    for b in bridges:
        cls = "derived" if b["time_consistent"] is not False else "candidate"
        ce = [] if b["time_consistent"] is not False else ["Event times differ by more than 72 h across cases; the shared reference may be reused or mis-parsed."]
        if b["time_precision_flags"]:
            ce.append(f"Event time precision is {', '.join(b['time_precision_flags'])} in at least one record; ordering is uncertain.")
        if b["duplicate_flag"]:
            ce.append("At least one record is a duplicate candidate in its own statement.")
        links.append({**b, "match_class": cls, "case_titles": {c: titles[c] for c in b["cases"]},
                      "method": {"name": "crosscase_reference_amount_time", "version": ALGORITHM_VERSION},
                      "limitations": ["reference_plus_amount_is_one_controlled_bridge_not_definitive"], "counter_evidence": ce})
    for x in infra:
        links.append({**x, "case_titles": {c: titles[c] for c in x["cases"]}, "method": {"name": "crosscase_shared_ip", "version": ALGORITHM_VERSION}})

    order = {"corroborated": 0, "exact": 1, "derived": 2, "candidate": 3, "stale": 4}
    links.sort(key=lambda l: (order.get(l["match_class"], 9), l["kind"], json.dumps(l.get("value") or l.get("reference") or l.get("ip"))))
    summary = defaultdict(int)
    for l in links:
        summary[l["match_class"]] += 1
    payload = {"algorithm_version": ALGORITHM_VERSION, "cases": [{"id": c.id, "title": c.title, "is_synthetic": c.is_synthetic} for c in cases],
               "links": links, "rejected": rejected, "summary": dict(summary),
               "notes": ["Match classes are categories, not probabilities.", "Entities are never merged across cases.",
                         "Shared hosting is a pivot, not evidence of common control.", "Data status per case: " + ", ".join(f"{titles[c]} = {'synthetic' if synthetic[c] else 'uploaded'}" for c in cids)]}
    payload["fingerprint"] = hashlib.sha256(json.dumps({k: payload[k] for k in ("algorithm_version", "links", "rejected")}, sort_keys=True, default=str).encode()).hexdigest()[:16]
    payload["generated_at"] = datetime.now(timezone.utc).isoformat()
    return payload


def related_cases(db: Session, user: User, case: Case) -> list[dict]:
    """Other cases the user may access that share at least one exact identifier with `case`. Never reveals inaccessible cases."""
    mine = db.execute(select(Entity).where(Entity.case_id == case.id, Entity.entity_type.in_(IDENTIFIER_TYPES))).scalars().all()
    keys = {(e.entity_type, _norm(e.entity_type, e.key)) for e in mine}
    out = []
    for other in authorised_cases(db, user):
        if other.id == case.id:
            continue
        theirs = db.execute(select(Entity).where(Entity.case_id == other.id, Entity.entity_type.in_(IDENTIFIER_TYPES))).scalars().all()
        shared = sorted({(e.entity_type, _norm(e.entity_type, e.key)) for e in theirs} & keys)
        if shared:
            out.append({"case_id": other.id, "title": other.title, "is_synthetic": other.is_synthetic, "shared_identifiers": [{"type": t, "value": v} for t, v in shared[:10]],
                        "shared_count": len(shared), "strong_identity_matches": sum(1 for t, _ in shared if t in STRONG_IDENTITY_TYPES)})
    out.sort(key=lambda x: (-x["strong_identity_matches"], -x["shared_count"], x["title"]))
    return out
