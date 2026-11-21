"""Payment-instruction-to-fund bridge.

Decode a QR image / upi:// URI / pasted text into a PaymentInstruction, then compare it field by field with recorded
transactions. The match level is explained by matched / missing / conflicting fields. A payee-name-only match is never
more than CANDIDATE_PARTIAL_MATCH; a one-character VPA difference is a different identifier.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import (Case, Entity, EvidenceItem, EvidenceLevel, PaymentInstruction, Relationship, RelationshipEvidence,
                        SourceFile, Transaction, User)
from app.parsers import qr
from app.parsers.qr import normalise_vpa, parse_payment_payload
from app.services import audit
from app.services.contract import finding, result
from app.services.ingestion import add_relationship, get_or_create_entity

MATCH_VERSION = "1.0.0"
LEVELS = ["EXACT_REFERENCE_AND_IDENTIFIER", "EXACT_IDENTIFIER_AMOUNT", "CORROBORATED_MULTI_FIELD", "CANDIDATE_PARTIAL_MATCH",
          "CONFLICTED_MATCH", "NO_MATCH", "UNRESOLVED"]
LIMITATION = "A matching payment instruction links the artefact to a payment record. It does not by itself identify the human controlling the payee account, website ownership, knowledge or guilt."
_REL_LEVEL = {"EXACT_REFERENCE_AND_IDENTIFIER": EvidenceLevel.corroborated, "EXACT_IDENTIFIER_AMOUNT": EvidenceLevel.corroborated,
              "CORROBORATED_MULTI_FIELD": EvidenceLevel.derived, "CANDIDATE_PARTIAL_MATCH": EvidenceLevel.candidate,
              "CONFLICTED_MATCH": EvidenceLevel.contradicted}


def _norm_ref(r: str | None) -> str | None:
    return r.strip().upper() if r and r.strip() else None


def register_instruction(db: Session, case: Case, user: User, *, raw_payload: str, extraction_method: str, source_file_id: str | None = None,
                         source_evidence_item_id: str | None = None, source_locator: dict | None = None, observed_at: datetime | None = None,
                         confidence: int | None = None, extra_warnings: list[str] | None = None) -> PaymentInstruction:
    parsed = parse_payment_payload(raw_payload)
    pi = PaymentInstruction(case_id=case.id, source_file_id=source_file_id, source_evidence_item_id=source_evidence_item_id,
                            source_locator=source_locator or {}, payload_type=parsed.payload_type, raw_payload=raw_payload,
                            fields={**parsed.fields, "pa_raw": parsed.payee_vpa_raw, "am_raw": parsed.amount_raw},
                            payee_vpa=parsed.payee_vpa, payee_name_raw=parsed.payee_name_raw, amount_minor=parsed.amount_minor,
                            currency=parsed.currency, reference=parsed.reference, note_raw=parsed.note_raw, extraction_method=extraction_method,
                            decoder_version=qr.DECODER_VERSION, confidence=confidence, warnings=parsed.warnings + (extra_warnings or []),
                            observed_at=observed_at, created_by=user.id)
    db.add(pi)
    db.flush()
    # evidence item so that the instruction participates in provenance like every other extracted record
    ev = EvidenceItem(case_id=case.id, source_file_id=source_file_id, source_type="payment_instruction", source_locator=source_locator or {},
                      raw_value=raw_payload, normalised_value={"payload_type": parsed.payload_type, "payee_vpa": parsed.payee_vpa, "amount_minor": parsed.amount_minor,
                                                               "currency": parsed.currency, "reference": parsed.reference, "note": parsed.note_raw, "payee_name": parsed.payee_name_raw},
                      extraction_method=extraction_method, parser_name="payment_payload", parser_version=qr.DECODER_VERSION, observed_at=observed_at,
                      time_precision="unknown", quality_flags=list(pi.warnings))
    db.add(ev)
    db.flush()
    pi.source_evidence_item_id = pi.source_evidence_item_id or ev.id
    ent = get_or_create_entity(db, case.id, "payment_instruction", f"pi:{pi.id[:8]}", f"Payment instruction {parsed.payee_vpa or parsed.payload_type}",
                               {"payload_type": parsed.payload_type, "payee_vpa": parsed.payee_vpa, "amount_minor": parsed.amount_minor, "reference": parsed.reference,
                                "instruction_id": pi.id}, observed_at)
    if parsed.payee_vpa:
        payee = get_or_create_entity(db, case.id, "vpa", parsed.payee_vpa, parsed.payee_name_raw or parsed.payee_vpa,
                                     {"name_raw": parsed.payee_name_raw} if parsed.payee_name_raw else None, observed_at)
        add_relationship(db, case.id, ent, payee, "INSTRUCTS_PAYMENT_TO", EvidenceLevel.directly_observed if extraction_method != "ocr_text" else EvidenceLevel.candidate,
                         "payment_payload", [ev.id], observed_at=observed_at,
                         limitations=["payee_named_in_instruction_not_proof_of_account_control"] + (["extracted_by_ocr_verify_against_image"] if extraction_method == "ocr_text" else []),
                         attributes={"instruction_id": pi.id, "amount_minor": parsed.amount_minor, "reference": parsed.reference})
    audit.record(db, "payment_instruction.registered", actor_id=user.id, case_id=case.id, target_type="payment_instruction", target_id=pi.id,
                 detail={"payload_type": parsed.payload_type, "method": extraction_method, "warnings": pi.warnings[:8]})
    return pi


def decode_image_instructions(db: Session, case: Case, user: User, sf: SourceFile, data: bytes) -> list[PaymentInstruction]:
    """Decode every QR code in an uploaded image and register each as an instruction (locator = QR region)."""
    decodes, warnings = qr.decode_qr(data)
    out = []
    for i, d in enumerate(decodes):
        out.append(register_instruction(db, case, user, raw_payload=d.payload, extraction_method="qr_decoder", source_file_id=sf.id,
                                        source_locator={"region": f"qr-{i + 1:02d}", "bbox": d.bbox, "decode_method": d.method},
                                        observed_at=None, extra_warnings=[w for w in warnings if w != "no_qr_code_decoded"]))  # observed_at unknown: when the victim saw the code is not recorded
    return out


def match_instruction(db: Session, case: Case, pi: PaymentInstruction, *, tolerance_hours: int = 72, persist: bool = True) -> dict:
    """Compare one instruction against all recorded transactions of the case."""
    alias = engine.alias_map(db, case)
    payee = pi.payee_vpa
    payee_canon = alias.get(payee, payee) if payee else None
    ref = _norm_ref(pi.reference)
    txs = db.execute(select(Transaction).where(Transaction.case_id == case.id)).scalars().all()
    candidates = []
    for t in txs:
        cp = normalise_vpa(t.counterparty_ref)
        cp_canon = alias.get(cp, cp) if cp else None
        matched, conflicting, missing = [], [], []
        # payee identifier
        if payee and cp:
            if cp == payee or (cp_canon and payee_canon and cp_canon == payee_canon):
                matched.append("payee_vpa" if cp == payee else "payee_vpa_via_alias")
        elif payee and not cp:
            missing.append("transaction_counterparty")
        # reference
        tref = _norm_ref(t.external_reference)
        if ref and tref:
            (matched if tref == ref else conflicting).append("reference")
        elif ref and not tref:
            missing.append("transaction_reference")
        if not matched:
            continue  # at least one identifying field (payee or reference) must match to be a candidate
        # amount & currency
        if pi.amount_minor is not None and t.amount_minor is not None:
            (matched if t.amount_minor == pi.amount_minor else conflicting).append("amount")
        elif pi.amount_minor is None:
            missing.append("instruction_amount")
        else:
            missing.append("transaction_amount")
        if pi.currency and t.currency:
            (matched if t.currency.upper() == pi.currency else conflicting).append("currency")
        elif pi.currency is None:
            missing.append("instruction_currency")
        # note / narration (weak)
        if pi.note_raw and t.narration_raw and pi.note_raw.strip().lower() in t.narration_raw.lower():
            matched.append("note_in_narration")
        # payee name (weak; never upgrades)
        if pi.payee_name_raw and t.counterparty_name_raw and pi.payee_name_raw.strip().lower() == t.counterparty_name_raw.strip().lower():
            matched.append("payee_name_weak")
        # time
        tdiff = None
        if pi.observed_at and t.datetime_utc:
            tdiff = int((t.datetime_utc - pi.observed_at).total_seconds())
            if abs(tdiff) <= tolerance_hours * 3600:
                matched.append("time_within_tolerance")
            else:
                conflicting.append("time_outside_tolerance")
        if t.time_precision in {"ambiguous", "unknown"}:
            missing.append("transaction_time_precise")
        strong = {"payee_vpa", "payee_vpa_via_alias", "reference", "amount"}
        if "reference" in matched and ("payee_vpa" in matched or "payee_vpa_via_alias" in matched) and "amount" not in conflicting and "currency" not in conflicting:
            status = "EXACT_REFERENCE_AND_IDENTIFIER"
        elif ("payee_vpa" in matched or "payee_vpa_via_alias" in matched) and "amount" in matched and "currency" not in conflicting and "reference" not in conflicting:
            status = "EXACT_IDENTIFIER_AMOUNT"
        elif any(c in {"amount", "currency", "reference"} for c in conflicting):
            status = "CONFLICTED_MATCH"
        elif len([m for m in matched if m in strong or m in {"note_in_narration", "time_within_tolerance"}]) >= 2:
            status = "CORROBORATED_MULTI_FIELD"
        else:
            status = "CANDIDATE_PARTIAL_MATCH"
        candidates.append({"transaction_id": t.id, "evidence_item_id": t.evidence_item_id, "status": status, "matched_fields": matched,
                           "conflicting_fields": conflicting, "missing_fields": missing, "time_difference_seconds": tdiff,
                           "transaction": {"account": t.account_ref, "counterparty_raw": t.counterparty_ref, "amount_minor": t.amount_minor, "currency": t.currency,
                                           "reference": t.external_reference, "direction": t.direction, "event_time": t.datetime_utc.isoformat() if t.datetime_utc else None,
                                           "time_precision": t.time_precision, "duplicate_of": t.duplicate_of, "warnings": t.warnings or []}})
    order = {s: i for i, s in enumerate(LEVELS)}
    candidates.sort(key=lambda c: (order[c["status"]], -len(c["matched_fields"]), c["transaction_id"]))
    if not payee and not ref:
        overall = "UNRESOLVED"
    elif not candidates:
        overall = "NO_MATCH"
    else:
        overall = candidates[0]["status"]
    warnings = list(pi.warnings or [])
    best = [c for c in candidates if c["status"] == overall]
    if len(best) > 1:
        dup_ids = {c["transaction"]["duplicate_of"] for c in best if c["transaction"]["duplicate_of"]}
        warnings.append("multiple_transactions_match_at_same_level" + (":includes_duplicate_rows" if dup_ids else ":possibly_distinct_payments"))
    if pi.extraction_method == "ocr_text":
        warnings.append("instruction_fields_come_from_ocr_verify_against_image")
    # persist relationship(s) for the best candidates (never for NO_MATCH / UNRESOLVED)
    if persist:
        ent = db.execute(select(Entity).where(Entity.case_id == case.id, Entity.entity_type == "payment_instruction", Entity.key == f"pi:{pi.id[:8]}")).scalar_one_or_none()
        old = [r for r in db.execute(select(Relationship).where(Relationship.case_id == case.id, Relationship.method_name == "payment_bridge")).scalars()
               if (r.attributes or {}).get("instruction_id") == pi.id] if ent else []
        for r in old:
            db.execute(delete(RelationshipEvidence).where(RelationshipEvidence.relationship_id == r.id))
            db.delete(r)
        if ent and overall in _REL_LEVEL:
            for c in best[:3]:
                t = db.get(Transaction, c["transaction_id"])
                cp_key = normalise_vpa(t.counterparty_ref) or t.account_ref
                tgt = db.execute(select(Entity).where(Entity.case_id == case.id, Entity.key == cp_key)).scalars().first()
                if tgt is None:
                    continue
                add_relationship(db, case.id, ent, tgt, "PAYMENT_INSTRUCTION_MATCHES_TRANSACTION", _REL_LEVEL[overall], "payment_bridge",
                                 [pi.source_evidence_item_id, t.evidence_item_id], observed_at=pi.observed_at, valid_from=t.datetime_utc, valid_to=t.datetime_utc,
                                 score={"EXACT_REFERENCE_AND_IDENTIFIER": 95, "EXACT_IDENTIFIER_AMOUNT": 85, "CORROBORATED_MULTI_FIELD": 60, "CANDIDATE_PARTIAL_MATCH": 25, "CONFLICTED_MATCH": 10}[overall],
                                 limitations=[LIMITATION] + (["conflicting_fields:" + ",".join(c["conflicting_fields"])] if c["conflicting_fields"] else []),
                                 attributes={"instruction_id": pi.id, "match_status": overall, "matched_fields": c["matched_fields"], "conflicting_fields": c["conflicting_fields"],
                                             "transaction_id": t.id, "match_version": MATCH_VERSION})
        db.flush()
    findings = [finding("payment_instruction_match", f"Instruction {pi.payee_vpa or pi.payload_type} → {overall.replace('_', ' ').lower()}",
                        evidence_class={"EXACT_REFERENCE_AND_IDENTIFIER": "corroborated", "EXACT_IDENTIFIER_AMOUNT": "corroborated", "CORROBORATED_MULTI_FIELD": "derived",
                                        "CANDIDATE_PARTIAL_MATCH": "candidate", "CONFLICTED_MATCH": "contradicted", "NO_MATCH": "unresolved", "UNRESOLVED": "unresolved"}[overall],
                        evidence_refs=[pi.source_evidence_item_id] + [c["evidence_item_id"] for c in best[:3]], match_status=overall)]
    return result(case, "payment_instruction_bridge", MATCH_VERSION, findings=findings,
                  input_evidence_ids=[pi.source_evidence_item_id] + [c["evidence_item_id"] for c in candidates],
                  limitations=[LIMITATION, "Name-only similarity never upgrades a match.", f"Time tolerance ±{tolerance_hours} h applies only when both times are known."],
                  warnings=warnings, instruction=instruction_out(pi), match_status=overall, candidates=candidates, levels=LEVELS)


def instruction_out(pi: PaymentInstruction) -> dict:
    return {"id": pi.id, "payload_type": pi.payload_type, "raw_payload": pi.raw_payload, "fields": pi.fields, "payee_vpa": pi.payee_vpa,
            "payee_name_raw": pi.payee_name_raw, "amount_minor": pi.amount_minor, "currency": pi.currency, "reference": pi.reference, "note_raw": pi.note_raw,
            "extraction_method": pi.extraction_method, "decoder_version": pi.decoder_version, "confidence": pi.confidence, "warnings": pi.warnings or [],
            "source_file_id": pi.source_file_id, "source_evidence_item_id": pi.source_evidence_item_id, "source_locator": pi.source_locator,
            "observed_at": pi.observed_at.isoformat() if pi.observed_at else None, "created_at": pi.created_at.isoformat() if pi.created_at else None}


def list_instructions(db: Session, case: Case) -> list[PaymentInstruction]:
    return db.execute(select(PaymentInstruction).where(PaymentInstruction.case_id == case.id).order_by(PaymentInstruction.created_at)).scalars().all()

