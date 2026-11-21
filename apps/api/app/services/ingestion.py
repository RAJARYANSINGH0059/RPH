"""Ingestion orchestrator: the ONE public path for both user uploads and synthetic-case imports.

validate -> hash -> store -> detect kind -> parse -> evidence items (raw + normalised + locator)
-> transactions / indicators / observations -> entities + directly-observed relationships.

Derived relationships and counter-evidence are computed afterwards by app.graph.rules.rebuild_derived.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (Case, Entity, EvidenceItem, EvidenceLevel, ParseRun, Relationship,
                        RelationshipEvidence, SourceFile, Transaction, User, utcnow)
from app.parsers import common, documents, indicators, tabular, technical_json
from app.services import audit
from app.services.storage import get_storage, sha256_bytes

ALLOWED_KINDS = {"pdf", "xlsx", "csv", "json", "docx", "txt", "png", "jpeg"}
MIME_BY_KIND = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "json": "application/json",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "png": "image/png",
    "jpeg": "image/jpeg",
}
METHOD_VERSION = "0.1.0"
log = logging.getLogger("ps05x.ingestion")


@dataclass
class IngestOutcome:
    source_file: SourceFile
    parse_run: ParseRun | None
    preview: dict


# ---------------------------------------------------------------- entities / relationships helpers

def get_or_create_entity(db: Session, case_id: str, entity_type: str, key: str, label: str | None = None,
                         attributes: dict | None = None, seen_at: datetime | None = None) -> Entity:
    key = key.strip()
    ent = db.execute(select(Entity).where(Entity.case_id == case_id, Entity.entity_type == entity_type, Entity.key == key)).scalar_one_or_none()
    if ent is None:
        ent = Entity(case_id=case_id, entity_type=entity_type, key=key, label=label or key, attributes=attributes or {},
                     first_seen=seen_at, last_seen=seen_at)
        db.add(ent)
        db.flush()
    else:
        if attributes:
            merged = dict(ent.attributes or {})
            merged.update({k: v for k, v in attributes.items() if v is not None})
            ent.attributes = merged
        if seen_at:
            if ent.first_seen is None or seen_at < ent.first_seen:
                ent.first_seen = seen_at
            if ent.last_seen is None or seen_at > ent.last_seen:
                ent.last_seen = seen_at
    return ent


def add_relationship(db: Session, case_id: str, src: Entity, dst: Entity, rel_type: str, level: EvidenceLevel,
                     method: str, evidence_ids: list[str], *, valid_from=None, valid_to=None, observed_at=None,
                     limitations: list[str] | None = None, attributes: dict | None = None, score: int | None = None,
                     direction: str = "directed") -> Relationship:
    rel = Relationship(case_id=case_id, source_entity_id=src.id, target_entity_id=dst.id, relationship_type=rel_type,
                       direction=direction, evidence_level=level, valid_from=valid_from, valid_to=valid_to,
                       observed_at=observed_at, method_name=method, method_version=METHOD_VERSION,
                       heuristic_score=score, limitations=limitations or [], attributes=attributes or {})
    db.add(rel)
    db.flush()
    for eid in dict.fromkeys(evidence_ids):
        db.add(RelationshipEvidence(relationship_id=rel.id, evidence_item_id=eid))
    return rel


# ---------------------------------------------------------------- public entry point

def ingest_upload(db: Session, case: Case, user: User, filename: str, data: bytes, *, is_synthetic: bool = False,
                  mapping_override: dict[str, str] | None = None) -> IngestOutcome:
    settings = get_settings()
    if len(data) == 0:
        raise HTTPException(400, "Empty file")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"File exceeds limit of {settings.max_upload_bytes} bytes")
    safe_name = re.sub(r"[^\w.\- ()]", "_", filename)[:200] or "upload.bin"
    kind, kind_warnings = common.detect_kind(data, safe_name)
    if kind not in ALLOWED_KINDS:
        raise HTTPException(415, f"Unsupported or unrecognised file type ({kind}). Allowed: {sorted(ALLOWED_KINDS)}")

    digest = sha256_bytes(data)
    dup = db.execute(select(SourceFile).where(SourceFile.case_id == case.id, SourceFile.sha256 == digest)).scalar_one_or_none()
    storage_key = get_storage().put(case.id, data, kind)
    sf = SourceFile(case_id=case.id, original_name=safe_name, storage_key=storage_key, mime_type=MIME_BY_KIND[kind],
                    detected_kind=kind, size_bytes=len(data), sha256=digest, uploaded_by=user.id,
                    is_synthetic=is_synthetic or case.is_synthetic, status="parsing")
    db.add(sf)
    db.flush()
    audit.record(db, "file.uploaded", actor_id=user.id, case_id=case.id, target_type="source_file", target_id=sf.id,
                 detail={"sha256": digest, "kind": kind, "size": len(data), "synthetic": sf.is_synthetic})

    file_entity = get_or_create_entity(db, case.id, "evidence_file", f"file:{digest[:16]}", safe_name,
                                       {"sha256": digest, "kind": kind, "source_file_id": sf.id}, utcnow())
    initial_warnings = list(kind_warnings)
    if dup is not None:
        initial_warnings.append(f"duplicate_file_already_uploaded:{dup.id}")

    try:
        if kind in {"csv", "xlsx"}:
            run, preview = _ingest_statement(db, case, sf, file_entity, data, kind, initial_warnings, mapping_override)
        elif kind == "json":
            run, preview = _ingest_technical_json(db, case, sf, file_entity, data, initial_warnings)
        else:
            run, preview = _ingest_document(db, case, sf, file_entity, data, kind, initial_warnings)
        sf.status = "needs_review" if run.warnings else "parsed"
        run.status = "completed"
    except HTTPException:
        raise
    except Exception as exc:  # parser failure must never crash the API
        log.exception("ingestion failed for %s (%s)", safe_name, kind)
        sf.status = "failed"
        run = ParseRun(case_id=case.id, source_file_id=sf.id, parser_name="dispatcher", parser_version=common.PARSER_VERSION,
                       status="failed", warnings=initial_warnings + [f"parser_error:{type(exc).__name__}"], stats={})
        db.add(run)
        preview = {"error": f"{type(exc).__name__}: parser failed; file kept for manual review"}
    run.finished_at = utcnow()
    db.flush()
    return IngestOutcome(sf, run, preview)


# ---------------------------------------------------------------- statements (CSV/XLSX)

def _cell_locator(sheet: str | None, row_idx: int, headers: list[str], header: str | None) -> dict:
    loc: dict = {"row": row_idx}
    if sheet:
        loc["sheet"] = sheet
    if header is not None and header in headers:
        col = headers.index(header)
        loc["column"] = header
        loc["cell"] = f"{tabular.column_letter(col)}{row_idx}"
    return loc


def _ingest_statement(db: Session, case: Case, sf: SourceFile, file_entity: Entity, data: bytes, kind: str,
                      warnings: list[str], mapping_override: dict[str, str] | None) -> tuple[ParseRun, dict]:
    parsed = tabular.parse_csv_bytes(data) if kind == "csv" else tabular.parse_xlsx_bytes(data)
    parser_name = tabular.PARSER_NAME_CSV if kind == "csv" else tabular.PARSER_NAME_XLSX
    mapping, unmapped = common.guess_column_mapping(parsed.headers)
    if mapping_override:
        for k, v in mapping_override.items():
            if v in parsed.headers:
                mapping[k] = v
        unmapped = [h for h in parsed.headers if h not in mapping.values()]
    warnings = warnings + parsed.warnings
    if unmapped:
        warnings.append("unmapped_columns:" + ",".join(unmapped))
    has_amount = "amount" in mapping or "debit" in mapping or "credit" in mapping
    if "datetime" not in mapping or not has_amount:
        warnings.append("mapping_incomplete_transactions_not_normalised")
    run = ParseRun(case_id=case.id, source_file_id=sf.id, parser_name=parser_name, parser_version=common.PARSER_VERSION,
                   column_mapping=mapping, warnings=warnings, stats={"rows": len(parsed.rows), "headers": parsed.headers})
    db.add(run)
    db.flush()

    statement_account_default = f"STATEMENT:{sf.sha256[:10]}"
    if "account" not in mapping:
        warnings.append("account_column_absent_statement_holder_inferred_from_file")

    counts = {"transactions": 0, "missing_amount": 0, "ambiguous_dates": 0, "duplicates": 0}
    seen_refs: dict[str, str] = {}
    preview_rows: list[dict] = []
    sum_debit = 0
    sum_credit = 0
    first_balance = last_balance = None

    for row in parsed.rows:
        def cell(field: str):
            h = mapping.get(field)
            return row.values.get(h) if h else None

        raw_row = {h: (None if v is None else str(v)) for h, v in row.values.items()}
        tx_warnings: list[str] = []

        d = common.parse_datetime(cell("datetime"))
        tx_warnings += d.warnings
        if d.precision == "ambiguous":
            counts["ambiguous_dates"] += 1

        direction = "unknown"
        amount: common.MoneyResult
        if "debit" in mapping or "credit" in mapping:
            deb = common.parse_money(cell("debit")) if "debit" in mapping else common.MoneyResult(None, "", [])
            cre = common.parse_money(cell("credit")) if "credit" in mapping else common.MoneyResult(None, "", [])
            if deb.minor and cre.minor:
                tx_warnings.append("both_debit_and_credit_present")
                amount, direction = deb, "debit"
            elif deb.minor:
                amount, direction = deb, "debit"
            elif cre.minor:
                amount, direction = cre, "credit"
            else:
                amount = common.MoneyResult(None, str(cell("debit") or cell("credit") or ""), ["missing_amount"])
        else:
            amount = common.parse_money(cell("amount"))
            dir_raw = str(cell("direction") or "").strip().lower()
            if dir_raw in {"dr", "debit", "d", "withdrawal", "out"}:
                direction = "debit"
            elif dir_raw in {"cr", "credit", "c", "deposit", "in"}:
                direction = "credit"
            elif amount.hint_direction:
                direction = amount.hint_direction
            elif amount.minor is not None and amount.minor < 0:
                direction = "debit"
                amount.minor = -amount.minor
            elif amount.minor is not None and "direction" not in mapping:
                tx_warnings.append("direction_not_in_source")
        tx_warnings += [w for w in amount.warnings if w not in tx_warnings]
        if amount.minor is None:
            counts["missing_amount"] += 1

        bal = common.parse_money(cell("balance")) if "balance" in mapping else common.MoneyResult(None, "", [])
        narration = cell("narration")
        narration = None if narration is None else str(narration)
        ref = cell("reference")
        ref = None if ref is None or str(ref).strip() in {"", "nan"} else str(ref).strip()
        cp = cell("counterparty")
        cp = None if cp is None or str(cp).strip() in {"", "nan"} else str(cp).strip()
        cp_name = cell("counterparty_name")
        cp_name = None if cp_name is None or str(cp_name).strip() in {"", "nan"} else str(cp_name).strip()
        acct = cell("account")
        acct = str(acct).strip() if acct is not None and str(acct).strip() not in {"", "nan"} else statement_account_default
        if cp is None and narration:
            found = indicators.extract_indicators(narration)
            for ind in found:
                if ind.kind in {"vpa", "account"}:
                    cp = ind.value
                    tx_warnings.append("counterparty_extracted_from_narration")
                    break
        if cp is None:
            tx_warnings.append("missing_counterparty")
        channel = str(cell("channel")).strip().upper() if cell("channel") else common.infer_channel(narration or (cp or ""))
        if channel not in {"UPI", "IMPS", "NEFT", "RTGS", "CARD", "CASH"}:
            channel = common.infer_channel(f"{narration or ''} {cp or ''}")

        ev = EvidenceItem(case_id=case.id, source_file_id=sf.id, parse_run_id=run.id, source_type="bank_statement",
                          source_locator=_cell_locator(parsed.sheet, row.row_index, parsed.headers, None),
                          raw_value=json.dumps(raw_row, ensure_ascii=False),
                          normalised_value={"direction": direction, "amount_minor": amount.minor, "reference": ref,
                                            "account": acct, "counterparty": cp, "counterparty_name": cp_name,
                                            "balance_after_minor": bal.minor, "channel": channel,
                                            "datetime_utc": d.dt.isoformat() if d.dt else None,
                                            "cells": {f: _cell_locator(parsed.sheet, row.row_index, parsed.headers, mapping[f]).get("cell") for f in mapping}},
                          extraction_method="tabular_cell", parser_name=parser_name, parser_version=common.PARSER_VERSION,
                          event_time_start=d.dt, event_time_end=d.dt, time_precision=d.precision,
                          source_timezone=d.timezone_name, observed_at=sf.uploaded_at, quality_flags=tx_warnings)
        db.add(ev)
        db.flush()

        tx = Transaction(case_id=case.id, evidence_item_id=ev.id, external_reference=ref, account_ref=acct,
                         counterparty_ref=cp, counterparty_name_raw=cp_name, datetime_raw=d.raw, datetime_utc=d.dt,
                         time_precision=d.precision, direction=direction, amount_minor=amount.minor, amount_raw=amount.raw,
                         narration_raw=narration, channel=channel, balance_after_minor=bal.minor,
                         quality_label="ok" if not tx_warnings else ("review" if amount.minor is not None else "incomplete"),
                         warnings=tx_warnings)
        if ref:
            if ref in seen_refs:
                tx.duplicate_of = seen_refs[ref]
                tx.warnings = tx.warnings + ["duplicate_reference_candidate"]
                counts["duplicates"] += 1
            else:
                seen_refs[ref] = ev.id
        db.add(tx)
        db.flush()
        counts["transactions"] += 1
        if amount.minor is not None:
            if direction == "debit":
                sum_debit += amount.minor
            elif direction == "credit":
                sum_credit += amount.minor
        if bal.minor is not None:
            if first_balance is None:
                first_balance = bal.minor
            last_balance = bal.minor

        # entities + directly observed TRANSFERRED_TO
        acct_ent = get_or_create_entity(db, case.id, "account", acct, acct, {"source": "statement"}, d.dt)
        if cp:
            cp_type = "vpa" if "@" in cp else "account"
            cp_ent = get_or_create_entity(db, case.id, cp_type, cp, cp_name or cp,
                                          {"name_raw": cp_name} if cp_name else None, d.dt)
            if amount.minor is not None and direction in {"debit", "credit"}:
                src, dst = (acct_ent, cp_ent) if direction == "debit" else (cp_ent, acct_ent)
                lim = []
                if d.precision in {"ambiguous", "unknown"}:
                    lim.append("event_time_uncertain")
                if "counterparty_extracted_from_narration" in tx_warnings:
                    lim.append("counterparty_parsed_from_narration_text")
                add_relationship(db, case.id, src, dst, "TRANSFERRED_TO", EvidenceLevel.directly_observed,
                                 "statement_row", [ev.id], valid_from=d.dt, valid_to=d.dt, observed_at=sf.uploaded_at,
                                 limitations=lim, attributes={"amount_minor": amount.minor, "reference": ref,
                                                              "transaction_id": tx.id, "channel": channel,
                                                              "statement_account": acct})
        if len(preview_rows) < 15:
            preview_rows.append({"row": row.row_index, "raw": raw_row, "normalised": ev.normalised_value, "warnings": tx_warnings})

    # balance reconciliation (only possible when balances are present)
    recon = None
    if first_balance is not None and last_balance is not None and counts["transactions"] > 1:
        # expected closing = first balance after first row's own effect is already included; approximate check
        expected = first_balance + sum_credit - sum_debit
        # first row's own amount is already in first_balance; correct for it
        first_tx = db.execute(select(Transaction).where(Transaction.case_id == case.id).join(EvidenceItem).where(EvidenceItem.source_file_id == sf.id).order_by(Transaction.datetime_utc)).scalars().first()
        if first_tx and first_tx.amount_minor is not None:
            expected -= first_tx.amount_minor if first_tx.direction == "credit" else -first_tx.amount_minor
        recon = {"first_balance_minor": first_balance, "last_balance_minor": last_balance, "expected_last_minor": expected,
                 "mismatch_minor": last_balance - expected}
        if abs(last_balance - expected) > 0:
            warnings.append(f"balance_reconciliation_mismatch:{last_balance - expected}")
    run.warnings = warnings
    run.stats = {**run.stats, **counts, "sum_debit_minor": sum_debit, "sum_credit_minor": sum_credit, "reconciliation": recon}
    # MENTIONS from file -> statement account
    acct_ent = get_or_create_entity(db, case.id, "account", statement_account_default if "account" not in mapping else acct, None)
    add_relationship(db, case.id, file_entity, acct_ent, "DOCUMENTS", EvidenceLevel.directly_observed, "statement_file", [],
                     observed_at=sf.uploaded_at, attributes={"source_file_id": sf.id})
    preview = {"headers": parsed.headers, "mapping": mapping, "unmapped": unmapped, "rows": preview_rows, "counts": counts,
               "reconciliation": recon, "warnings": warnings}
    return run, preview


# ---------------------------------------------------------------- documents (PDF/DOCX/TXT/images)

def _ingest_document(db: Session, case: Case, sf: SourceFile, file_entity: Entity, data: bytes, kind: str,
                     warnings: list[str]) -> tuple[ParseRun, dict]:
    settings = get_settings()
    if kind == "pdf":
        res, pname = documents.parse_pdf_bytes(data, settings.max_pdf_pages), documents.PARSER_NAME_PDF
    elif kind == "docx":
        res, pname = documents.parse_docx_bytes(data), documents.PARSER_NAME_DOCX
    elif kind == "txt":
        res, pname = documents.parse_txt_bytes(data), documents.PARSER_NAME_TXT
    else:
        res, pname = documents.parse_image_bytes(data), documents.PARSER_NAME_IMAGE
    warnings = warnings + res.warnings
    run = ParseRun(case_id=case.id, source_file_id=sf.id, parser_name=pname, parser_version=common.PARSER_VERSION,
                   warnings=warnings, stats={"blocks": len(res.blocks), "pages": res.page_count})
    db.add(run)
    db.flush()
    source_type = "complaint" if re.search(r"complaint|fir|statement of victim", sf.original_name, re.I) else "document"
    found_total: dict[str, int] = {}
    snippets: list[dict] = []
    for block in res.blocks:
        ocr_meta = getattr(block, "ocr", None) or {}
        ocr_flags = []
        if block.method == "ocr":
            ocr_flags = ["ocr_review_required"] + (["ocr_low_confidence"] if ocr_meta.get("quality") != "ok" else [])
        nv = {"text_length": len(block.text)}
        if ocr_meta:
            nv["ocr"] = {k: v for k, v in ocr_meta.items() if k != "boxes"}
            nv["ocr_boxes"] = ocr_meta.get("boxes", [])[:60]
        ev = EvidenceItem(case_id=case.id, source_file_id=sf.id, parse_run_id=run.id, source_type=source_type,
                          source_locator=block.locator, raw_value=block.text[:20000],
                          normalised_value=nv, extraction_method=block.method,
                          parser_name=pname, parser_version=common.PARSER_VERSION, observed_at=sf.uploaded_at,
                          time_precision="unknown", quality_flags=ocr_flags)
        db.add(ev)
        db.flush()
        inds = indicators.extract_indicators(block.text)
        for ind in inds:
            found_total[ind.kind] = found_total.get(ind.kind, 0) + 1
            etype = {"url": "url", "domain": "domain", "ip": "ip", "email": "email", "vpa": "vpa", "phone": "phone",
                     "utr": "reference", "account": "account"}[ind.kind]
            attrs = {"mentioned_in": sf.original_name}
            if etype == "ip":
                attrs["classification"] = indicators.ip_classification(ind.value)
            ent = get_or_create_entity(db, case.id, etype, ind.value, ind.value, attrs, sf.uploaded_at)
            iev = EvidenceItem(case_id=case.id, source_file_id=sf.id, parse_run_id=run.id, source_type=source_type,
                               source_locator={**block.locator, "char_span": list(ind.span)},
                               raw_value=block.text[max(0, ind.span[0] - 60): ind.span[1] + 60],
                               normalised_value={"indicator_kind": ind.kind, "value": ind.value},
                               extraction_method=f"regex_{ind.kind}", parser_name=pname, parser_version=common.PARSER_VERSION,
                               observed_at=sf.uploaded_at, time_precision="unknown", quality_flags=list(ocr_flags))
            db.add(iev)
            db.flush()
            lim = ["mention_only_not_proof_of_involvement"]
            if block.method == "ocr":
                lim.append("extracted_by_ocr_verify_against_image")
                if ocr_meta.get("quality") != "ok":
                    lim.append("low_confidence_ocr_needs_corroboration")
            level = EvidenceLevel.candidate if (block.method == "ocr" and ocr_meta.get("quality") != "ok") else EvidenceLevel.directly_observed
            add_relationship(db, case.id, file_entity, ent, "MENTIONS", level, "document_regex",
                             [iev.id], observed_at=sf.uploaded_at, limitations=lim,
                             attributes={"indicator_kind": ind.kind, "locator": iev.source_locator})
        if len(snippets) < 5:
            snippets.append({"locator": block.locator, "method": block.method, "text": block.text[:400],
                             "ocr": {k: v for k, v in ocr_meta.items() if k != "boxes"} if ocr_meta else None})
    # payment instructions: upi:// payloads in text blocks (OCR-derived ones stay candidates) and QR codes in images
    try:
        from app.services import payment_bridge
        from app.models import User as _User
        uploader = db.get(_User, sf.uploaded_by)
        uris = []
        for block in res.blocks:
            for m in re.finditer(r"upi://pay\?[^\s\"'<>]+", block.text, re.I):
                uris.append((m.group(0), block))
        for uri, block in uris[:10]:
            pi = payment_bridge.register_instruction(db, case, uploader, raw_payload=uri, extraction_method="ocr_text" if block.method == "ocr" else "uri_text", source_file_id=sf.id,
                                                     source_locator={**block.locator, "char_span": [block.text.find(uri), block.text.find(uri) + len(uri)]}, observed_at=None,
                                                     confidence=int(round((block.confidence or 0) * 100)) if block.method == "ocr" and block.confidence is not None else None)
            payment_bridge.match_instruction(db, case, pi)
            found_total["payment_instruction"] = found_total.get("payment_instruction", 0) + 1
        if kind in {"png", "jpeg"}:
            for pi in payment_bridge.decode_image_instructions(db, case, uploader, sf, data):
                payment_bridge.match_instruction(db, case, pi)
                found_total["qr_payment_instruction"] = found_total.get("qr_payment_instruction", 0) + 1
    except Exception as exc:  # never fail ingestion because of payload decoding
        warnings.append(f"payment_payload_extraction_failed:{type(exc).__name__}")
        log.exception("payment payload extraction failed")
    run.stats = {**run.stats, "indicators": found_total}
    preview = {"blocks": len(res.blocks), "pages": res.page_count, "indicators": found_total, "snippets": snippets, "warnings": warnings}
    return run, preview


# ---------------------------------------------------------------- technical observations (JSON)

def _parse_iso(v) -> datetime | None:
    if v is None:
        return None
    r = common.parse_datetime(str(v), assume_tz="UTC")
    return r.dt


def _ingest_technical_json(db: Session, case: Case, sf: SourceFile, file_entity: Entity, data: bytes,
                           warnings: list[str]) -> tuple[ParseRun, dict]:
    res = technical_json.parse_technical_json_bytes(data)
    warnings = warnings + res.warnings
    run = ParseRun(case_id=case.id, source_file_id=sf.id, parser_name=technical_json.PARSER_NAME,
                   parser_version=common.PARSER_VERSION, warnings=warnings, stats={"observations": len(res.observations)})
    db.add(run)
    db.flush()
    counts: dict[str, int] = {}
    for obs in res.observations:
        counts[obs.obs_type] = counts.get(obs.obs_type, 0) + 1
        observed = _parse_iso(obs.fields.get("observed_at"))
        valid_from = _parse_iso(obs.fields.get("valid_from")) or observed
        valid_to = _parse_iso(obs.fields.get("valid_to"))
        ttl = obs.fields.get("ttl")
        if valid_to is None and observed is not None and isinstance(ttl, (int, float)):
            from datetime import timedelta
            valid_to = observed + timedelta(seconds=float(ttl))
        ev = EvidenceItem(case_id=case.id, source_file_id=sf.id, parse_run_id=run.id, source_type="technical_observation",
                          source_locator={"json_path": obs.json_path}, raw_value=json.dumps({**obs.fields, **obs.extra}, default=str),
                          normalised_value={"type": obs.obs_type, **{k: v for k, v in obs.fields.items() if k != "type"}},
                          extraction_method="json_field", parser_name=technical_json.PARSER_NAME,
                          parser_version=common.PARSER_VERSION, event_time_start=valid_from, event_time_end=valid_to,
                          time_precision="second" if observed else "unknown", source_timezone="UTC",
                          observed_at=observed, quality_flags=obs.warnings)
        db.add(ev)
        db.flush()
        domain = obs.fields.get("domain")
        ip = obs.fields.get("ip")
        provider = obs.fields.get("provider")
        asn = obs.fields.get("asn")
        url = obs.fields.get("url")
        src_label = str(obs.fields.get("source") or "technical_report")
        base_lims = [f"reported_by:{src_label}"]
        if observed is None:
            base_lims.append("observation_time_missing")
        note_txt = str(obs.fields.get("note") or obs.extra.get("note") or "").lower()
        if "current" in src_label.lower() or "current lookup" in note_txt or "current-only" in note_txt:
            base_lims.append("current_lookup_not_historical")
            ev.quality_flags = list(ev.quality_flags or []) + ["current_lookup_not_historical"]
        if obs.obs_type == "dns" and domain and ip:
            d_ent = get_or_create_entity(db, case.id, "domain", str(domain).lower(), None, None, observed)
            ip_ent = get_or_create_entity(db, case.id, "ip", str(ip), None, {"classification": indicators.ip_classification(str(ip))}, observed)
            add_relationship(db, case.id, d_ent, ip_ent, "RESOLVES_TO", EvidenceLevel.directly_observed, "dns_observation",
                             [ev.id], valid_from=valid_from, valid_to=valid_to, observed_at=observed,
                             limitations=base_lims + ["dns_mapping_valid_only_at_observation_time"],
                             attributes={"ttl": ttl, "resolver": obs.fields.get("resolver")})
        elif obs.obs_type in {"hosting", "cdn"} and ip:
            ip_ent = get_or_create_entity(db, case.id, "ip", str(ip), None, {"classification": indicators.ip_classification(str(ip))}, observed)
            host_key = str(asn or provider or "unknown_provider")
            host_ent = get_or_create_entity(db, case.id, "asn" if asn else "hosting_provider", host_key, str(provider or host_key),
                                            {"provider": provider, "asn": asn, "is_cdn": obs.obs_type == "cdn" or bool(obs.extra.get("multi_tenant"))}, observed)
            add_relationship(db, case.id, ip_ent, host_ent, "HOSTED_ON", EvidenceLevel.directly_observed, "hosting_observation",
                             [ev.id], valid_from=valid_from, valid_to=valid_to, observed_at=observed,
                             limitations=base_lims + ["hosting_association_is_not_common_control"],
                             attributes={"provider": provider, "asn": asn, "multi_tenant": obs.extra.get("multi_tenant")})
            if domain:
                d_ent = get_or_create_entity(db, case.id, "domain", str(domain).lower(), None, None, observed)
                add_relationship(db, case.id, d_ent, ip_ent, "RESOLVES_TO", EvidenceLevel.directly_observed, "hosting_observation",
                                 [ev.id], valid_from=valid_from, valid_to=valid_to, observed_at=observed,
                                 limitations=base_lims + ["dns_mapping_valid_only_at_observation_time"])
        elif obs.obs_type == "url" and url:
            u_ent = get_or_create_entity(db, case.id, "url", str(url), None, None, observed)
            d = indicators._domain_from_url(str(url))
            if d:
                d_ent = get_or_create_entity(db, case.id, "domain", d, None, None, observed)
                add_relationship(db, case.id, u_ent, d_ent, "BELONGS_TO_DOMAIN", EvidenceLevel.derived, "url_parse", [ev.id],
                                 observed_at=observed, limitations=[])
            add_relationship(db, case.id, file_entity, u_ent, "MENTIONS", EvidenceLevel.directly_observed, "technical_report",
                             [ev.id], observed_at=observed, limitations=base_lims)
        elif obs.obs_type == "rdap" and domain:
            d_ent = get_or_create_entity(db, case.id, "domain", str(domain).lower(), None,
                                         {"registrar": obs.fields.get("registrar"), "created": obs.fields.get("created")}, observed)
            add_relationship(db, case.id, file_entity, d_ent, "REGISTRATION_OBSERVED", EvidenceLevel.directly_observed, "rdap_observation",
                             [ev.id], observed_at=observed, limitations=base_lims + ["rdap_is_current_registration_not_historical_ownership"],
                             attributes={"registrar": obs.fields.get("registrar")})
        else:
            if domain:
                get_or_create_entity(db, case.id, "domain", str(domain).lower(), None, None, observed)
            if ip:
                get_or_create_entity(db, case.id, "ip", str(ip), None, {"classification": indicators.ip_classification(str(ip))}, observed)
    run.stats = {**run.stats, "by_type": counts}
    preview = {"observations": len(res.observations), "by_type": counts, "warnings": warnings,
               "sample": [{"path": o.json_path, "type": o.obs_type, "fields": o.fields} for o in res.observations[:10]]}
    return run, preview
