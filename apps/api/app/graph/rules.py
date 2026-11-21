"""Relationship verification layer: derived edges, evidence levels, temporal checks and counter-evidence.

Rules (from the blueprint):
- Shared IP / CDN / ASN / registrar alone never creates a common-ownership or common-operator finding.
- Similar names alone never merge entities; they produce a candidate SIMILAR_NAME edge with counter-evidence.
- Approximate matches retain the matching method and conflicting identifiers.
- Current DNS is never represented as historical DNS.
- Heuristic scores are ranking scores, not probabilities.

`safeguards=False` reproduces the naive "Baseline C" behaviour (shared IP => COMMON_OPERATOR) for benchmarking only.
"""
from __future__ import annotations

import difflib
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import Case, CounterEvidence, Entity, EvidenceLevel, Relationship, RelationshipEvidence, Transaction
from app.services.ingestion import add_relationship

DERIVED_METHODS = {"shared_infrastructure", "same_identifier", "similar_name", "duplicate_reference", "naive_shared_ip",
                   "path_reconstruction", "triage_rules"}


def _counter(db: Session, case_id: str, rel: Relationship, kind: str, description: str, severity: str = "medium", evidence_item_id: str | None = None):
    db.add(CounterEvidence(case_id=case_id, relationship_id=rel.id, kind=kind, description=description, severity=severity,
                           evidence_item_id=evidence_item_id))


def _evidence_ids(db: Session, rel: Relationship) -> list[str]:
    return [r.evidence_item_id for r in db.execute(select(RelationshipEvidence).where(RelationshipEvidence.relationship_id == rel.id)).scalars()]


def rebuild_derived(db: Session, case: Case, *, safeguards: bool = True, infra: bool = True) -> dict:
    """Recompute derived relationships and counter-evidence for a case. Idempotent."""
    # 1. remove previously derived edges (and their counter evidence) but never observed ones
    old = db.execute(select(Relationship).where(Relationship.case_id == case.id, Relationship.method_name.in_(DERIVED_METHODS))).scalars().all()
    for r in old:
        db.execute(delete(CounterEvidence).where(CounterEvidence.relationship_id == r.id))
        db.delete(r)
    # counter-evidence on observed edges is also recomputed
    observed = db.execute(select(Relationship).where(Relationship.case_id == case.id)).scalars().all()
    for r in observed:
        db.execute(delete(CounterEvidence).where(CounterEvidence.relationship_id == r.id))
        if r.evidence_level in {EvidenceLevel.stale, EvidenceLevel.contradicted, EvidenceLevel.corroborated} and r.method_name in {"statement_row", "dns_observation", "hosting_observation"}:
            r.evidence_level = EvidenceLevel.directly_observed
    db.flush()

    stats = {"shared_infra": 0, "same_identifier": 0, "similar_name": 0, "duplicates": 0, "stale_dns": 0, "corroborated": 0, "naive_common_operator": 0}
    ents = db.execute(select(Entity).where(Entity.case_id == case.id)).scalars().all()
    by_id = {e.id: e for e in ents}
    rels = db.execute(select(Relationship).where(Relationship.case_id == case.id)).scalars().all()

    # ---------- transaction window (for temporal validity checks)
    txs = db.execute(select(Transaction).where(Transaction.case_id == case.id, Transaction.datetime_utc.is_not(None))).scalars().all()
    tx_times = sorted(t.datetime_utc for t in txs)
    window = (tx_times[0] - timedelta(days=30), tx_times[-1] + timedelta(days=30)) if tx_times else None

    # ---------- 2. corroboration + identifier aliasing via (reference, amount) seen in two different statements
    # The victim's statement names the beneficiary by VPA; the beneficiary's own statement names its account number.
    # A shared UTR/reference AND amount across two statements is deterministic evidence that the two identifiers
    # denote the same account for that transfer. This is a DERIVED edge (SAME_ACCOUNT_IDENTIFIER), never a merge.
    groups: dict[tuple, list[Relationship]] = defaultdict(list)
    for r in rels:
        if r.relationship_type == "TRANSFERRED_TO" and r.method_name == "statement_row":
            a = r.attributes or {}
            if a.get("reference"):
                groups[(a.get("reference"), a.get("amount_minor"))].append(r)
    alias_pairs: set[tuple[str, str]] = set()
    for key, group in groups.items():
        statements = {(r.attributes or {}).get("statement_account") for r in group}
        if len(statements) >= 2:
            for r in group:
                r.evidence_level = EvidenceLevel.corroborated
            stats["corroborated"] += 1
            base = group[0]
            for other in group[1:]:
                for x, y in ((base.source_entity_id, other.source_entity_id), (base.target_entity_id, other.target_entity_id)):
                    if x != y and (y, x) not in alias_pairs:
                        alias_pairs.add((x, y))
                        ev = _evidence_ids(db, base) + _evidence_ids(db, other)
                        add_relationship(db, case.id, by_id[x], by_id[y], "SAME_ACCOUNT_IDENTIFIER", EvidenceLevel.derived, "same_identifier", ev,
                                         direction="undirected", score=90,
                                         limitations=["inferred_from_matching_reference_and_amount_in_two_statements", "entities_kept_separate_not_merged"],
                                         attributes={"reference": key[0], "amount_minor": key[1], "matching_method": "exact_reference_and_amount"})
        elif len(group) >= 2:
            for r in group[1:]:
                _counter(db, case.id, r, "duplicate_reference", f"Reference {key[0]} appears {len(group)} times in the same statement; may be a duplicate row.", "medium")
            stats["duplicates"] += 1

    # ---------- 3. temporal validity of DNS / hosting observations relative to the transaction window
    for r in rels:
        if r.relationship_type in {"RESOLVES_TO", "HOSTED_ON"} and window and r.observed_at:
            if r.observed_at < window[0] or r.observed_at > window[1]:
                r.evidence_level = EvidenceLevel.stale
                _counter(db, case.id, r, "observation_outside_event_window",
                         f"Observed {r.observed_at.date()} which is outside the transaction window {window[0].date()}..{window[1].date()}. Mapping may not have been in effect during the events.", "high")
                stats["stale_dns"] += 1
            if r.valid_to and r.valid_to < (window[0] + timedelta(days=30)) and r.evidence_level != EvidenceLevel.stale:
                _counter(db, case.id, r, "ttl_expired_before_events", "TTL/validity expired before the first transaction.", "medium")
        if r.relationship_type == "RESOLVES_TO" and r.method_name in {"connector_dns", "connector_rdap"}:
            lims = set(r.limitations or [])
            lims.add("current_lookup_not_historical")
            r.limitations = sorted(lims)

    # ---------- 4. shared infrastructure (domains resolving to one IP / hosted on one provider)
    if infra:
        ip_to_domains: dict[str, set[str]] = defaultdict(set)
        ip_rel_evidence: dict[str, list[str]] = defaultdict(list)
        for r in rels:
            if r.relationship_type == "RESOLVES_TO":
                ip_to_domains[r.target_entity_id].add(r.source_entity_id)
                ip_rel_evidence[r.target_entity_id] += _evidence_ids(db, r)
        multi_tenant_ips = set()
        for r in rels:
            if r.relationship_type == "HOSTED_ON":
                tgt = by_id.get(r.target_entity_id)
                if tgt and ((tgt.attributes or {}).get("is_cdn") or (r.attributes or {}).get("multi_tenant")):
                    multi_tenant_ips.add(r.source_entity_id)
        for ip_id, doms in ip_to_domains.items():
            doms_l = sorted(doms)
            if len(doms_l) < 2:
                continue
            ip_ent = by_id[ip_id]
            for i in range(len(doms_l)):
                for j in range(i + 1, len(doms_l)):
                    a, b = by_id[doms_l[i]], by_id[doms_l[j]]
                    if safeguards:
                        rel = add_relationship(db, case.id, a, b, "SHARED_INFRASTRUCTURE", EvidenceLevel.candidate, "shared_infrastructure",
                                               ip_rel_evidence[ip_id], direction="undirected", score=15,
                                               limitations=["shared_ip_is_not_proof_of_common_control", "pivot_only_requires_independent_identifier_bridge"],
                                               attributes={"shared_ip": ip_ent.key, "multi_tenant": ip_id in multi_tenant_ips, "domain_count_on_ip": len(doms_l)})
                        reason = "IP is observed as multi-tenant/CDN hosting" if ip_id in multi_tenant_ips else f"IP hosts {len(doms_l)} domains in this case alone"
                        _counter(db, case.id, rel, "multi_tenant_infrastructure",
                                 f"Alternative explanation: {reason}; unrelated sites commonly share addresses. No identifier (payment VPA, account, email, phone) bridges these domains.",
                                 "high" if ip_id in multi_tenant_ips else "medium")
                        stats["shared_infra"] += 1
                    else:
                        # Baseline C (benchmark only): naive common-operator from shared IP
                        add_relationship(db, case.id, a, b, "COMMON_OPERATOR", EvidenceLevel.derived, "naive_shared_ip", ip_rel_evidence[ip_id],
                                         direction="undirected", score=70, attributes={"shared_ip": ip_ent.key, "benchmark_baseline": "no_safeguards"})
                        stats["naive_common_operator"] += 1

    # ---------- 5. same identifier across independent source types (bridge: VPA/account/phone/email seen in complaint AND statement)
    for e in ents:
        if e.entity_type not in {"vpa", "account", "phone", "email"}:
            continue
        mention_rels = [r for r in rels if r.target_entity_id == e.id and r.relationship_type == "MENTIONS"]
        money_rels = [r for r in rels if (r.source_entity_id == e.id or r.target_entity_id == e.id) and r.relationship_type == "TRANSFERRED_TO"]
        if mention_rels and money_rels:
            for mr in mention_rels:
                src_file = by_id.get(mr.source_entity_id)
                ev = _evidence_ids(db, mr) + [eid for r in money_rels[:3] for eid in _evidence_ids(db, r)]
                rel = add_relationship(db, case.id, src_file, e, "SAME_IDENTIFIER", EvidenceLevel.corroborated, "same_identifier", ev,
                                       score=80, limitations=["exact_string_match_after_normalisation"],
                                       attributes={"identifier_type": e.entity_type, "matching_method": "exact_normalised", "sources": ["document", "bank_statement"]})
                stats["same_identifier"] += 1
            if safeguards:
                for r in money_rels:
                    if r.evidence_level == EvidenceLevel.directly_observed:
                        r.evidence_level = EvidenceLevel.corroborated

    # ---------- 6. similar names: candidate only, never merge
    named = [(e, (e.attributes or {}).get("name_raw") or e.label) for e in ents if e.entity_type in {"account", "vpa"} and ((e.attributes or {}).get("name_raw") or (e.label != e.key))]
    for i in range(len(named)):
        for j in range(i + 1, len(named)):
            (ea, na), (eb, nb) = named[i], named[j]
            if not na or not nb or na.lower() == nb.lower():
                continue
            ratio = difflib.SequenceMatcher(None, na.lower(), nb.lower()).ratio()
            if ratio >= 0.85:
                rel = add_relationship(db, case.id, ea, eb, "SIMILAR_NAME", EvidenceLevel.candidate, "similar_name", [], direction="undirected",
                                       score=int(ratio * 40), limitations=["approximate_name_match_only", "entities_not_merged"],
                                       attributes={"name_a": na, "name_b": nb, "similarity": round(ratio, 3), "matching_method": "difflib_ratio",
                                                   "conflicting_identifiers": [ea.key, eb.key]})
                _counter(db, case.id, rel, "approximate_name_identifiers_conflict",
                         f"Names '{na}' and '{nb}' are similar but the account/VPA identifiers differ ({ea.key} vs {eb.key}). Do not merge without an independent identifier.", "high")
                stats["similar_name"] += 1

    # ---------- 7. low-quality OCR dependency
    for r in rels:
        if "extracted_by_ocr_verify_against_image" in (r.limitations or []):
            _counter(db, case.id, r, "single_low_quality_ocr_source", "This relationship depends on one OCR extraction; verify against the page image.", "medium")

    # ---------- 8. time-uncertain transfers
    for r in rels:
        if r.relationship_type == "TRANSFERRED_TO" and "event_time_uncertain" in (r.limitations or []):
            _counter(db, case.id, r, "ambiguous_event_time", "Transaction date is ambiguous (dd/mm vs mm/dd) or missing; ordering within a path is uncertain.", "medium")

    db.flush()
    return stats
