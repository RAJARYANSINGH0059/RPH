"""Proof-carrying money trail: a derivation manifest for a reconstructed path that an independent examiner can verify offline
with scripts/verify_proof.py (standard library only). Integrity-protected (SHA-256, optional HMAC); not a legal certificate."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import engine
from app.graph.rules import DERIVED_METHODS  # noqa: F401  (documents the rule set version in the manifest)
from app.models import Case, CounterEvidence, EvidenceItem, ParseRun, Relationship, SourceFile, Transaction
from app.parsers import common
from app.services.ingestion import METHOD_VERSION

MANIFEST_VERSION = "1.0.0"
RULES = {"path_algorithm_version": engine.PATH_ALGORITHM_VERSION, "relationship_method_version": METHOD_VERSION, "parser_version": common.PARSER_VERSION,
         "alias_rule": "SAME_ACCOUNT_IDENTIFIER: identical external reference AND amount observed in two different statements (exact match; entities not merged)",
         "money_representation": "integer paise; raw amount strings preserved", "hop_chaining": "next hop starts at/after previous hop and within 120 h; unknown times allowed but flagged",
         "amount_flags": "split when hop < 98% of running amount; merged_inflow when hop > 102%"}


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def _sign(digest: str) -> dict:
    key = os.environ.get("PROOF_SIGNING_KEY", "")
    if not key:
        return {"hmac_sha256": None, "key_version": None, "note": "PROOF_SIGNING_KEY not configured: manifest is hash-protected only"}
    return {"hmac_sha256": hmac.new(key.encode(), digest.encode(), hashlib.sha256).hexdigest(), "key_version": os.environ.get("PROOF_SIGNING_KEY_VERSION", "v1")}


def build_manifest(db: Session, case: Case, path_index: int) -> dict:
    paths = engine.reconstruct_paths(db, case)
    if path_index < 0 or path_index >= len(paths):
        raise IndexError("path index out of range")
    p = paths[path_index]
    files = {f.id: f for f in db.execute(select(SourceFile).where(SourceFile.case_id == case.id)).scalars()}
    runs = {r.id: r for r in db.execute(select(ParseRun).where(ParseRun.case_id == case.id)).scalars()}
    used_files: dict[str, SourceFile] = {}
    hops = []
    rels = {(r.attributes or {}).get("transaction_id"): r for r in db.execute(select(Relationship).where(Relationship.case_id == case.id, Relationship.relationship_type == "TRANSFERRED_TO")).scalars()}
    for i, h in enumerate(p["hops"], 1):
        t = db.get(Transaction, h["tx_id"])
        ev = db.get(EvidenceItem, h["evidence_item_id"])
        f = files.get(ev.source_file_id) if ev else None
        run = runs.get(ev.parse_run_id) if ev and ev.parse_run_id else None
        if f:
            used_files[f.id] = f
        rel = rels.get(h["tx_id"])
        counters = db.execute(select(CounterEvidence).where(CounterEvidence.relationship_id == rel.id)).scalars().all() if rel else []
        raw_row = None
        try:
            raw_row = json.loads(ev.raw_value) if ev and ev.raw_value else None
        except Exception:
            raw_row = {"_raw": ev.raw_value if ev else None}
        hops.append({"hop": i, "from_account": h["src"], "to_account": h["dst"], "amount_minor": h["amount_minor"], "reference": h["reference"], "event_time": h["time"],
                     "time_precision": h["precision"], "hop_class": h["hop_class"], "flags": h["flags"], "corroborated": h["corroborated"], "transaction_id": h["tx_id"],
                     "evidence_item_id": h["evidence_item_id"], "source_file_id": f.id if f else None, "source_sha256": f.sha256 if f else None, "source_name": f.original_name if f else None,
                     "locator": ev.source_locator if ev else None, "raw_row": raw_row, "normalised": ev.normalised_value if ev else None, "column_mapping": run.column_mapping if run else None,
                     "parser": {"name": ev.parser_name, "version": ev.parser_version, "method": ev.extraction_method} if ev else None,
                     "statement_account_raw": t.account_ref if t else None, "direction": t.direction if t else None, "amount_raw": t.amount_raw if t else None, "datetime_raw": t.datetime_raw if t else None,
                     "relationship_id": rel.id if rel else None, "relationship_level": rel.evidence_level.value if rel else None,
                     "contradictions": [{"kind": c.kind, "severity": c.severity, "description": c.description} for c in counters]})
    times = [h["event_time"] for h in hops if h["event_time"]]
    manifest = {"manifest_version": MANIFEST_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(), "generator": "PS05-X proof.build_manifest",
                "case": {"id": case.id, "title": case.title, "synthetic": case.is_synthetic, "data_status": "SYNTHETIC DATA" if case.is_synthetic else "UPLOADED DATA"},
                "path": {"index": path_index, "accounts": p["accounts"], "hop_count": p["hop_count"], "status": p["status"], "unresolved_reason": p["unresolved_reason"], "path_class": p["path_class"],
                         "alias_map_used": {k: v for k, v in engine.alias_map(db, case).items() if k != v and (k in p["accounts"] or v in p["accounts"])}},
                "hops": hops,
                "source_files": [{"id": f.id, "name": f.original_name, "sha256": f.sha256, "size_bytes": f.size_bytes, "kind": f.detected_kind, "synthetic": f.is_synthetic} for f in used_files.values()],
                "rules": RULES,
                "constraints": {"conservation": {"entry_minor": p["total_in_minor"], "exit_minor": p["exit_amount_minor"], "ratio": p["conservation_ratio"], "flags": p["flags"],
                                                 "statement": "exit <= entry unless a merged_inflow flag is present; amounts are never invented"},
                                "temporal": {"monotone_non_decreasing": all(times[i] <= times[i + 1] for i in range(len(times) - 1)), "known_times": len(times), "uncertain_hops": [h["hop"] for h in hops if h["hop_class"] == "uncertain_time"]}},
                "contradictions": [c for h in hops for c in h["contradictions"]],
                "limitations": ["Integrity-protected derivation record; not a legal certificate or an electronic signature.",
                                "A verified manifest shows that the derivation reproduces from the cited files; it does not establish who controlled any account.",
                                p["unresolved_reason"] or "Path ends at an account whose statement is in the case."]}
    digest = hashlib.sha256(canonical(manifest)).hexdigest()
    manifest["integrity"] = {"manifest_sha256": digest, **_sign(digest), "canonicalisation": "json sort_keys, separators (',', ':'), utf-8, excluding the integrity block"}
    return manifest


def verify_manifest_integrity(manifest: dict) -> dict:
    """Server-side quick check (the full offline verifier lives in scripts/verify_proof.py)."""
    body = {k: v for k, v in manifest.items() if k != "integrity"}
    digest = hashlib.sha256(canonical(body)).hexdigest()
    ok = digest == (manifest.get("integrity") or {}).get("manifest_sha256")
    return {"manifest_hash_ok": ok, "recomputed": digest}
