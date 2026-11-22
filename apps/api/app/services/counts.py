"""Canonical case counts.

Three surfaces used to disagree: the overview counted every relationship row, the report counted the rows it chose to
table (excluding DOCUMENTS edges), and the results page read a field name the report never emitted, so it always said
zero paths. A number on screen is a claim about evidence, so the same question must get the same answer everywhere.

Every count in the application comes from this module, and each one is defined in `definitions` so a reader knows what
it includes. Nothing here filters by evidence level: a candidate relationship is counted and labelled as such, never
dropped to make a total look tidier.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import Case, Entity, ParseRun, Relationship, SourceFile, Transaction

COUNTS_VERSION = "1.0.0"

# Relationship types the report tables leave out: they record that a document mentions something, not an investigative
# relationship between two parties. They are still counted in the total, and named here so the difference is explicit.
PRESENTATION_EXCLUDED_TYPES = frozenset({"DOCUMENTS"})

DEFINITIONS = {
    "files.total": "Source files stored for this case, including any that failed to parse.",
    "transactions.total": "Parsed transaction rows, including rows flagged as duplicates.",
    "transactions.excluding_duplicates": "Transaction rows once rows flagged as a duplicate of another row are set aside. Duplicates are kept, never deleted.",
    "entities.total": "Distinct accounts, VPAs, domains, IPs, people and other identifiers extracted from evidence.",
    "relationships.total": "Every relationship row held for this case, at every evidence level and review status.",
    "relationships.in_graph": "Relationships both of whose endpoints are present as entities, so they can be drawn. A relationship is only excluded here if an endpoint is missing.",
    "relationships.in_report_tables": "Relationships listed in report tables: the total minus types that merely record a document mention (" + ", ".join(sorted(PRESENTATION_EXCLUDED_TYPES)) + ").",
    "relationships.awaiting_review": "Candidate, stale or contradicted relationships that are still unreviewed and need a human decision.",
    "paths.total": "Multi-hop fund paths reconstructed by the path algorithm with its default parameters (max 5 hops, 120-hour chaining window, 50 paths).",
    "paths.unresolved": "Reconstructed paths whose last hop could not be followed because the next account's statement is not in the case.",
    "indicators.total": "Infrastructure observations: URLs, domains, IP addresses, ASNs and hosting providers.",
    "parser_warnings": "Warnings raised across all parse runs: information to check, not errors and not findings.",
}

_INDICATOR_TYPES = ("url", "domain", "ip", "asn", "hosting_provider")


def case_counts(db: Session, case: Case, *, include_paths: bool = True) -> dict:
    """The canonical numbers for one case. `include_paths=False` skips path reconstruction, which is the expensive part."""
    def total(model) -> int:
        return int(db.execute(select(func.count()).select_from(model).where(model.case_id == case.id)).scalar_one())

    files = total(SourceFile)
    tx_total = total(Transaction)
    tx_dupes = int(db.execute(select(func.count()).select_from(Transaction)
                              .where(Transaction.case_id == case.id, Transaction.duplicate_of.is_not(None))).scalar_one())
    tx_with_amount = int(db.execute(select(func.count()).select_from(Transaction)
                                    .where(Transaction.case_id == case.id, Transaction.amount_minor.is_not(None))).scalar_one())

    ents = db.execute(select(Entity).where(Entity.case_id == case.id)).scalars().all()
    ent_ids = {e.id for e in ents}
    by_entity_type = Counter(e.entity_type for e in ents)

    rels = db.execute(select(Relationship).where(Relationship.case_id == case.id)).scalars().all()
    by_level = Counter(r.evidence_level.value for r in rels)
    by_review = Counter(r.review_status.value for r in rels)
    in_graph = sum(1 for r in rels if r.source_entity_id in ent_ids and r.target_entity_id in ent_ids)
    in_tables = sum(1 for r in rels if r.relationship_type not in PRESENTATION_EXCLUDED_TYPES)
    awaiting = sum(1 for r in rels if r.evidence_level.value in {"candidate", "stale", "contradicted"} and r.review_status.value == "unreviewed")

    warnings = sum(len(r.warnings or []) for r in db.execute(select(ParseRun).where(ParseRun.case_id == case.id)).scalars())

    out = {
        "version": COUNTS_VERSION,
        "case_id": case.id,
        "files": {"total": files},
        "transactions": {"total": tx_total, "with_amount": tx_with_amount, "duplicates": tx_dupes, "excluding_duplicates": tx_total - tx_dupes},
        "entities": {"total": len(ents), "by_type": dict(sorted(by_entity_type.items()))},
        "relationships": {
            "total": len(rels),
            "in_graph": in_graph,
            "in_report_tables": in_tables,
            "awaiting_review": awaiting,
            "by_evidence_level": dict(sorted(by_level.items())),
            "by_review_status": dict(sorted(by_review.items())),
        },
        "indicators": {"total": sum(by_entity_type.get(t, 0) for t in _INDICATOR_TYPES)},
        "parser_warnings": warnings,
        "definitions": DEFINITIONS,
        "note": "Counts include candidate and stale relationships; they are labelled, never dropped. Every surface in the application reads these numbers.",
    }
    if include_paths:
        paths = engine.reconstruct_paths(db, case)
        out["paths"] = {
            "total": len(paths),
            "unresolved": sum(1 for p in paths if p.get("status") == "unresolved"),
            "resolved": sum(1 for p in paths if p.get("status") != "unresolved"),
        }
    return out
