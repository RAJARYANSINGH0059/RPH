"""Evidence integrity and statement forensics.

Separate dimensions, never a single authenticity score: file_integrity (SHA-256 recomputed against the stored original),
source_authenticity (provenance class; 'verified' only with a recorded method), statement_completeness, arithmetic_consistency
(row-level running balance, duplicates, ordering), extraction_agreement (text layer vs OCR; debit+credit both present),
provenance (hash, metadata, parser version, transformations). Metadata anomalies are review leads only. Rows involved in a
disagreement are `provisional` and the TRANSFERRED_TO edges they back carry a limitation.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Case, EvidenceItem, ParseRun, Relationship, SourceFile, Transaction
from app.services.contract import finding, result
from app.services.storage import get_storage, sha256_bytes

INTEGRITY_VERSION = "1.0.0"
PROVENANCE_CLASSES = ["bank_originated_independently_verified", "bank_digital_export_supplied_by_user", "investigator_provided_pdf", "screenshot_or_image", "ocr_derived", "manually_transcribed", "technical_report", "unknown"]


def provenance_class(sf: SourceFile, evs: list[EvidenceItem]) -> tuple[str, str]:
    if sf.detected_kind in {"csv", "xlsx"}:
        return "bank_digital_export_supplied_by_user", "Machine-readable export supplied by the uploader. Not independently verified with the bank."
    if sf.detected_kind in {"png", "jpeg"}:
        return ("ocr_derived" if any(e.extraction_method == "ocr" for e in evs) else "screenshot_or_image"), "Image evidence; any text came from OCR and needs verification against the image."
    if sf.detected_kind == "pdf":
        if any(e.extraction_method == "ocr" for e in evs):
            return "ocr_derived", "Scanned PDF: text came from OCR."
        return "investigator_provided_pdf", "Text-layer PDF supplied by the uploader; origin not independently verified."
    if sf.detected_kind == "json":
        return "technical_report", "Technical observation file; the named source inside the file is reported, not verified."
    if sf.detected_kind in {"txt", "docx"}:
        return "manually_transcribed", "Plain document; may be transcribed or generated."
    return "unknown", "Unrecognised origin."


def pdf_metadata_leads(data: bytes) -> dict:
    """Safe PDF structure/metadata inspection. Leads only, never proof of forgery."""
    try:
        import fitz
    except Exception:
        return {"available": False}
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        return {"available": True, "error": f"unreadable: {type(exc).__name__}", "leads": ["pdf_unreadable"]}
    md = doc.metadata or {}
    leads = []
    cd, mdt = md.get("creationDate") or "", md.get("modDate") or ""
    if cd and mdt and mdt[:16] != cd[:16]:
        leads.append("modification_date_differs_from_creation_date (normal for edited documents; review lead only)")
    if not md.get("producer") and not md.get("creator"):
        leads.append("no_producer_or_creator_metadata")
    incremental = data.count(b"%%EOF")
    if incremental > 1:
        leads.append(f"incremental_updates_present:{incremental} (saved more than once; not evidence of tampering)")
    text_pages = sum(1 for pg in doc if pg.get_text().strip())
    image_pages = sum(1 for pg in doc if pg.get_images())
    if image_pages and text_pages and image_pages == len(doc) and text_pages == len(doc):
        leads.append("pages_contain_both_images_and_text (could be a scan with an OCR layer; compare layer and image)")
    return {"available": True, "pages": len(doc), "metadata": {k: md.get(k) for k in ("producer", "creator", "creationDate", "modDate", "title", "author") if md.get(k)},
            "text_pages": text_pages, "image_pages": image_pages, "incremental_updates": incremental, "leads": leads, "note": "Metadata anomalies are review leads, not proof of forgery or authenticity."}


def statement_forensics(db: Session, case: Case, sf: SourceFile) -> dict:
    rows = db.execute(select(Transaction, EvidenceItem).join(EvidenceItem, Transaction.evidence_item_id == EvidenceItem.id).where(EvidenceItem.source_file_id == sf.id)).all()
    items = sorted(rows, key=lambda r: ((r[1].source_locator or {}).get("row") or 0))
    anomalies = []
    by_ref = defaultdict(list)
    accounts = set()
    prev = None
    opening = closing = None
    credits = debits = 0
    for t, ev in items:
        row = (ev.source_locator or {}).get("row")
        accounts.add(t.account_ref)
        if t.external_reference:
            by_ref[t.external_reference].append(row)
        if t.amount_minor is None:
            anomalies.append({"row": row, "transaction_id": t.id, "kind": "missing_amount", "severity": "high", "detail": "amount could not be normalised"})
        elif t.direction == "credit":
            credits += t.amount_minor
        elif t.direction == "debit":
            debits += t.amount_minor
        else:
            anomalies.append({"row": row, "transaction_id": t.id, "kind": "direction_unknown", "severity": "medium", "detail": "debit/credit direction not determinable"})
        if "both_debit_and_credit_present" in (t.warnings or []):
            anomalies.append({"row": row, "transaction_id": t.id, "kind": "extraction_disagreement", "severity": "high", "detail": "both debit and credit cells carry values; direction chosen as debit provisionally"})
        if t.time_precision == "ambiguous":
            anomalies.append({"row": row, "transaction_id": t.id, "kind": "ambiguous_date", "severity": "medium", "detail": f"'{t.datetime_raw}' could be dd/mm or mm/dd; timezone assumed Asia/Kolkata (statement convention)"})
        if prev is not None:
            pt = prev
            if pt.datetime_utc and t.datetime_utc and t.datetime_utc < pt.datetime_utc and t.time_precision not in {"ambiguous", "unknown"} and pt.time_precision not in {"ambiguous", "unknown"}:
                anomalies.append({"row": row, "transaction_id": t.id, "kind": "out_of_order_date", "severity": "medium", "detail": f"row date {t.datetime_utc.date()} precedes previous row {pt.datetime_utc.date()}"})
            if pt.balance_after_minor is not None and t.balance_after_minor is not None and t.amount_minor is not None and not t.duplicate_of:
                expected = pt.balance_after_minor + (t.amount_minor if t.direction == "credit" else -t.amount_minor)
                if t.balance_after_minor != expected:
                    anomalies.append({"row": row, "transaction_id": t.id, "kind": "running_balance_break", "severity": "high",
                                      "detail": f"balance {t.balance_after_minor} ≠ previous {pt.balance_after_minor} {'+' if t.direction == 'credit' else '-'} {t.amount_minor} = {expected} (difference {t.balance_after_minor - expected} paise)"})
        if t.duplicate_of:
            anomalies.append({"row": row, "transaction_id": t.id, "kind": "duplicate_row", "severity": "medium", "detail": f"same reference as evidence {t.duplicate_of}; original kept, this row excluded from paths"})
        if t.balance_after_minor is not None:
            if opening is None and t.amount_minor is not None:
                opening = t.balance_after_minor - (t.amount_minor if t.direction == "credit" else -t.amount_minor)
            closing = t.balance_after_minor
        prev = t
    if len(accounts) > 1:
        anomalies.append({"row": None, "transaction_id": None, "kind": "inconsistent_account_identifier", "severity": "high", "detail": f"rows name {len(accounts)} different statement accounts: {sorted(accounts)[:4]}"})
    for ref, rws in by_ref.items():
        if len(rws) > 1:
            anomalies.append({"row": rws[1], "transaction_id": None, "kind": "repeated_reference", "severity": "medium", "detail": f"reference {ref} on rows {rws}"})
    arith = None
    if opening is not None and closing is not None and len(items) > 1:
        expected_close = opening + credits - debits
        arith = {"opening_minor": opening, "credits_minor": credits, "debits_minor": debits, "expected_closing_minor": expected_close, "stated_closing_minor": closing,
                 "difference_minor": closing - expected_close, "formula": "closing = opening + credits - debits (duplicate rows are included as stated here; excluded from paths)"}
    disputed = sorted({a["transaction_id"] for a in anomalies if a["transaction_id"] and a["kind"] in {"running_balance_break", "extraction_disagreement", "missing_amount", "direction_unknown"}})
    return {"rows": len(items), "accounts": sorted(accounts), "anomalies": anomalies, "arithmetic": arith, "provisional_transaction_ids": disputed,
            "summary_comparison": {"available": False, "note": "No declared statement summary block (totals/period) detected; totals cannot be compared to a declared summary."}}


def file_report(db: Session, case: Case, sf: SourceFile) -> dict:
    run = db.execute(select(ParseRun).where(ParseRun.source_file_id == sf.id).order_by(ParseRun.started_at.desc())).scalars().first()
    evs = db.execute(select(EvidenceItem).where(EvidenceItem.source_file_id == sf.id)).scalars().all()
    try:
        data = get_storage().get(sf.storage_key)
        actual = sha256_bytes(data)
        integrity = {"stored_sha256": sf.sha256, "recomputed_sha256": actual, "match": actual == sf.sha256, "size_bytes": len(data)}
    except Exception as exc:
        data = None
        integrity = {"stored_sha256": sf.sha256, "recomputed_sha256": None, "match": None, "error": f"original not readable: {type(exc).__name__}"}
    pclass, pnote = provenance_class(sf, evs)
    authenticity = {"provenance_class": pclass, "note": pnote, "verification": "none_recorded", "verified": False,
                    "meaning": "SHA-256 proves the stored bytes are unchanged since upload; it does not prove the document's origin, truth or admissibility."}
    metadata = pdf_metadata_leads(data) if (data and sf.detected_kind == "pdf") else {"available": False}
    forensics = statement_forensics(db, case, sf) if sf.detected_kind in {"csv", "xlsx"} else None
    agreement = None
    if sf.detected_kind in {"pdf", "png", "jpeg"}:
        by_page: dict = defaultdict(dict)
        for e in evs:
            if e.extraction_method in {"text_layer", "ocr"}:
                by_page[(e.source_locator or {}).get("page", 1)][e.extraction_method] = e
        disagreements = []
        for page, d in by_page.items():
            if "text_layer" in d and "ocr" in d:
                a, b = set((d["text_layer"].raw_value or "").split()), set((d["ocr"].raw_value or "").split())
                j = len(a & b) / len(a | b) if (a | b) else 1.0
                if j < 0.7:
                    disagreements.append({"page": page, "token_overlap": round(j, 3), "detail": "text layer and OCR disagree; route to human review"})
        low = [e.id for e in evs if "ocr_low_confidence" in (e.quality_flags or [])]
        methods = {e.extraction_method for e in evs if e.extraction_method in {"text_layer", "ocr"}}
        agreement = {"methods_present": sorted({e.extraction_method for e in evs}), "disagreements": disagreements, "low_confidence_ocr_blocks": low,
                     "status": "disputed" if disagreements else ("review_required" if low else ("single_method" if len(methods) < 2 else "agree"))}
    dims = {"file_integrity": "ok" if integrity.get("match") else ("unknown" if integrity.get("match") is None else "MODIFIED"),
            "source_authenticity": "unverified (" + pclass + ")",
            "statement_completeness": ("partial" if forensics and any(a["kind"] == "running_balance_break" for a in forensics["anomalies"]) else "as_supplied") if forensics else "n/a",
            "arithmetic_consistency": ("inconsistent" if forensics["arithmetic"] and forensics["arithmetic"]["difference_minor"] != 0 else ("consistent" if forensics["arithmetic"] else "not_checkable")) if forensics else "n/a",
            "extraction_agreement": agreement["status"] if agreement else ("single_method" if forensics else "n/a"), "provenance": "recorded"}
    return {"file": {"id": sf.id, "name": sf.original_name, "kind": sf.detected_kind, "mime": sf.mime_type, "uploaded_at": sf.uploaded_at.isoformat(), "synthetic": sf.is_synthetic, "status": sf.status},
            "dimensions": dims, "file_integrity": integrity, "source_authenticity": authenticity, "metadata_leads": metadata, "statement_forensics": forensics, "extraction_agreement": agreement,
            "provenance": {"parser": {"name": run.parser_name, "version": run.parser_version} if run else None, "ingested_at": run.started_at.isoformat() if run else None,
                           "transformations": ["original bytes stored immutably", "parsed to evidence items with locators"] + (["OCR derivative"] if any(e.extraction_method == "ocr" for e in evs) else []),
                           "evidence_items": len(evs), "warnings": (run.warnings or [])[:10] if run else []}}


def mark_provisional(db: Session, case: Case) -> int:
    files = db.execute(select(SourceFile).where(SourceFile.case_id == case.id, SourceFile.detected_kind.in_(["csv", "xlsx"]))).scalars().all()
    disputed: set[str] = set()
    for sf in files:
        disputed |= set(statement_forensics(db, case, sf)["provisional_transaction_ids"])
    n = 0
    for r in db.execute(select(Relationship).where(Relationship.case_id == case.id, Relationship.relationship_type == "TRANSFERRED_TO")).scalars():
        lims = set(r.limitations or [])
        if (r.attributes or {}).get("transaction_id") in disputed and "provisional_disputed_statement_row" not in lims:
            lims.add("provisional_disputed_statement_row")
            r.limitations = sorted(lims)
            n += 1
    return n


def case_report(db: Session, case: Case) -> dict:
    files = db.execute(select(SourceFile).where(SourceFile.case_id == case.id).order_by(SourceFile.uploaded_at)).scalars().all()
    reports = [file_report(db, case, f) for f in files]
    anomalies = sum(len((r["statement_forensics"] or {}).get("anomalies", [])) for r in reports)
    provisional = sorted({t for r in reports for t in ((r["statement_forensics"] or {}).get("provisional_transaction_ids", []))})
    findings = [finding("file_dimensions", f"{r['file']['name']}: integrity {r['dimensions']['file_integrity']}, arithmetic {r['dimensions']['arithmetic_consistency']}, extraction {r['dimensions']['extraction_agreement']}",
                        evidence_class="derived", file_id=r["file"]["id"]) for r in reports]
    return result(case, "evidence_integrity", INTEGRITY_VERSION, findings=findings, limitations=["SHA-256 proves bytes are unchanged since upload, not authenticity or truth.",
                  "Metadata anomalies are leads, not proof of forgery.", "Unverified periods are unknown, never zero activity."],
                  files=reports, anomaly_count=anomalies, provisional_transaction_ids=provisional, provenance_classes=PROVENANCE_CLASSES)
