"""Deterministic, source-grounded report generation (JSON + PDF). No LLM. Every statement cites evidence IDs/locators."""
from __future__ import annotations

import io
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services import counts, ml_triage
from app.graph import engine
from app.models.twin import EvidenceRequest
from app.services import typologies
from app.models import (AnalystReview, Case, CounterEvidence, Entity, EvidenceItem, ParseRun, Relationship,
                        RelationshipEvidence, SourceFile, Transaction)

DISCLAIMER = ("Investigative analysis aid; authorised human verification required. This report organises evidence and "
              "flags patterns for review. It does not establish guilt, ownership or legal admissibility.")


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def build_report(db: Session, case: Case) -> dict:
    s = get_settings()
    files = db.execute(select(SourceFile).where(SourceFile.case_id == case.id).order_by(SourceFile.uploaded_at)).scalars().all()
    runs = db.execute(select(ParseRun).where(ParseRun.case_id == case.id)).scalars().all()
    txs = db.execute(select(Transaction).where(Transaction.case_id == case.id).order_by(Transaction.datetime_utc)).scalars().all()
    ents = {e.id: e for e in db.execute(select(Entity).where(Entity.case_id == case.id)).scalars()}
    rels = db.execute(select(Relationship).where(Relationship.case_id == case.id)).scalars().all()
    counters = db.execute(select(CounterEvidence).where(CounterEvidence.case_id == case.id)).scalars().all()
    reviews = db.execute(select(AnalystReview).where(AnalystReview.case_id == case.id)).scalars().all()
    ev_by_rel: dict[str, list[str]] = {}
    for re_ in db.execute(select(RelationshipEvidence).join(Relationship).where(Relationship.case_id == case.id)).scalars():
        ev_by_rel.setdefault(re_.relationship_id, []).append(re_.evidence_item_id)
    ev_items = {e.id: e for e in db.execute(select(EvidenceItem).where(EvidenceItem.case_id == case.id)).scalars()}

    def locator_of(rel_id: str) -> list[dict]:
        out = []
        for eid in ev_by_rel.get(rel_id, [])[:3]:
            e = ev_items.get(eid)
            if e:
                sf = next((f for f in files if f.id == e.source_file_id), None)
                out.append({"evidence_item_id": eid, "file": sf.original_name if sf else None, "sha256": sf.sha256[:16] if sf else None,
                            "locator": e.source_locator, "method": e.extraction_method})
        return out

    paths = engine.reconstruct_paths(db, case)
    feats = engine.account_features(db, case)
    triage = {a: engine.rules_triage(f) for a, f in feats.items()}

    infra_types = {"RESOLVES_TO", "HOSTED_ON", "REGISTRATION_OBSERVED", "SHARED_INFRASTRUCTURE"}
    relationship_table = []
    for r in sorted(rels, key=lambda r: (r.relationship_type, r.evidence_level.value)):
        if r.relationship_type in {"DOCUMENTS"}:
            continue
        relationship_table.append({
            "id": r.id, "type": r.relationship_type, "source": ents[r.source_entity_id].label if r.source_entity_id in ents else "?",
            "source_type": ents[r.source_entity_id].entity_type if r.source_entity_id in ents else "?",
            "target": ents[r.target_entity_id].label if r.target_entity_id in ents else "?",
            "target_type": ents[r.target_entity_id].entity_type if r.target_entity_id in ents else "?",
            "evidence_level": r.evidence_level.value, "review_status": r.review_status.value,
            "valid_from": _iso(r.valid_from), "valid_to": _iso(r.valid_to), "observed_at": _iso(r.observed_at),
            "method": f"{r.method_name}@{r.method_version}", "heuristic_score_not_probability": r.heuristic_score,
            "limitations": r.limitations or [], "sources": locator_of(r.id),
        })
    counter_rows = [{"relationship_id": c.relationship_id, "kind": c.kind, "severity": c.severity, "description": c.description} for c in counters]
    gaps = []
    for run in runs:
        for w in run.warnings or []:
            gaps.append({"file": next((f.original_name for f in files if f.id == run.source_file_id), "?"), "warning": w})
    unresolved = [r for r in rels if r.evidence_level.value in {"candidate", "stale", "contradicted", "insufficient"} and r.review_status.value == "unreviewed"]
    return {
        "report_version": "0.1.0", "generated_at": datetime.now(timezone.utc).isoformat(), "generator": f"{s.app_name} {s.app_version} (deterministic templates)",
        "disclaimer": DISCLAIMER,
        "case": {"id": case.id, "title": case.title, "internal_ref": case.internal_ref, "status": case.status, "summary": case.summary,
                 "data_status": "SYNTHETIC DATA" if case.is_synthetic else "UPLOADED DATA (authorisation asserted by uploader)",
                 "live_connections": "NO LIVE POLICE/BANK CONNECTION"},
        "sources": [{"id": f.id, "name": f.original_name, "kind": f.detected_kind, "sha256": f.sha256, "size_bytes": f.size_bytes,
                     "uploaded_at": _iso(f.uploaded_at), "status": f.status, "synthetic": f.is_synthetic} for f in files],
        "parsing": [{"file": next((f.original_name for f in files if f.id == r.source_file_id), "?"), "parser": f"{r.parser_name}@{r.parser_version}",
                     "status": r.status, "mapping": r.column_mapping, "warnings": r.warnings, "stats": r.stats} for r in runs],
        "transactions": {"count": len(txs), "with_amount": sum(1 for t in txs if t.amount_minor is not None),
                         "ambiguous_dates": sum(1 for t in txs if t.time_precision == "ambiguous"),
                         "duplicate_candidates": sum(1 for t in txs if t.duplicate_of),
                         "rows": [{"id": t.id, "when_utc": _iso(t.datetime_utc), "when_raw": t.datetime_raw, "precision": t.time_precision,
                                   "account": t.account_ref, "direction": t.direction, "amount_minor": t.amount_minor, "amount_raw": t.amount_raw,
                                   "counterparty": t.counterparty_ref, "reference": t.external_reference, "channel": t.channel,
                                   "warnings": t.warnings, "evidence_item_id": t.evidence_item_id,
                                   "locator": ev_items[t.evidence_item_id].source_locator if t.evidence_item_id in ev_items else None} for t in txs[:500]]},
        "counts": counts.case_counts(db, case),  # canonical; the tables below are presentations of the same data
        "fund_paths": paths,
        "account_triage": [{"account": a, **triage[a], "ml_triage": ml_triage.score(feats[a]), "features": feats[a]} for a in sorted(triage, key=lambda a: -triage[a]["heuristic_score"])],
        "ml_model": ml_triage.status(),
        "infrastructure_observations": [r for r in relationship_table if r["type"] in infra_types],
        "relationships": relationship_table,
        "typologies": typologies.case_profiles(db, case),
        "evidence_requests": [
            {"id": r.id, "title": r.title, "custodian_type": r.organisation_type, "target_entity": r.target_entity,
             "target_record": r.target_record, "window_from": _iso(r.window_from), "window_to": _iso(r.window_to),
             "records_requested": r.required_fields or [], "status": r.status,
             "legal_authority": r.legal_authority or "to be completed by an authorised officer",
             "requesting_officer": r.requesting_officer or "to be completed by an authorised officer",
             "rationale": r.rationale, "could_resolve": r.could_resolve or [],
             "would_not_establish": r.would_not_establish or [],
             "transmitted_by_this_system": False}
            for r in db.execute(select(EvidenceRequest).where(EvidenceRequest.case_id == case.id)
                                .order_by(EvidenceRequest.id)).scalars()],
        "limitations": [
            DISCLAIMER,
            "A missing statement is reported as unknown. It is never evidence that no transaction occurred.",
            "Duplicate rows are kept as evidence and excluded from totals, never deleted.",
            "Timestamps carry their precision. Where a source gave no time zone, none is assumed.",
            "Heuristic scores rank accounts for review and are not calibrated probabilities.",
            "Any machine-learning output is advisory and never makes a decision.",
            "Shared addresses, nameservers, autonomous systems, registrars and certificates are candidate links "
            "only; none of them establishes common ownership or control.",
            "A current lookup describes the moment it was made and is never presented as historical evidence.",
        ],
        "counter_evidence": counter_rows,
        "reviews": [{"relationship_id": r.relationship_id, "decision": r.decision.value, "reason": r.reason, "at": _iso(r.created_at)} for r in reviews],
        "unresolved": {"relationships_requiring_review": len(unresolved), "parser_warnings": gaps,
                       "manual_review_required": [{"relationship_id": r.id, "type": r.relationship_type, "evidence_level": r.evidence_level.value} for r in unresolved[:100]]},
    }


def report_pdf(report: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                            title=f"PS05-X report {report['case']['id']}")
    ss = getSampleStyleSheet()
    small = ss["BodyText"]
    small.fontSize = 8
    small.leading = 10
    story = []
    c = report["case"]
    story.append(Paragraph(f"<b>PS05-X Investigation Report</b> — {c['title']}", ss["Title"]))
    story.append(Paragraph(f"<font color='#8a1c1c'><b>{c['data_status']}</b> · {c['live_connections']}</font>", ss["BodyText"]))
    story.append(Paragraph(f"Case {c['id']} · ref {c['internal_ref'] or '—'} · generated {report['generated_at']}", small))
    story.append(Paragraph(report["disclaimer"], small))
    story.append(Spacer(1, 8))

    def table(title, header, rows, widths=None):
        story.append(Paragraph(f"<b>{title}</b>", ss["Heading3"]))
        data = [header] + (rows or [["(none)"] + [""] * (len(header) - 1)])
        data = [[Paragraph(str(x)[:300], small) for x in r] for r in data]
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                               ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(t)
        story.append(Spacer(1, 6))

    cnt = report["counts"]
    story.append(Paragraph("<b>Summary</b>", ss["Heading3"]))
    story.append(Paragraph(
        f"{cnt['files']['total']} evidence file(s) · {cnt['transactions']['total']} transaction(s) "
        f"({cnt['transactions']['excluding_duplicates']} excluding duplicates) · "
        f"{cnt['entities']['total']} entities · {cnt['relationships']['total']} relationships "
        f"({cnt['relationships']['awaiting_review']} awaiting review) · "
        f"{(cnt.get('paths') or {}).get('total', 0)} reconstructed path(s), "
        f"{(cnt.get('paths') or {}).get('unresolved', 0)} unresolved. "
        f"Figures come from the canonical counts service (v{cnt['version']}), so they agree with the case "
        f"screens and the other exports.", small))
    story.append(Spacer(1, 6))
    table("Sources and hashes", ["File", "Kind", "SHA-256", "Status"], [[s["name"], s["kind"], s["sha256"], s["status"]] for s in report["sources"]], [6 * cm, 1.5 * cm, 8 * cm, 2.5 * cm])
    table("Parsing methods and warnings", ["File", "Parser", "Warnings"], [[p["file"], p["parser"], "; ".join(p["warnings"][:8]) or "—"] for p in report["parsing"]], [5 * cm, 4 * cm, 9 * cm])
    tx = report["transactions"]
    story.append(Paragraph(f"<b>Transaction trail</b>: {tx['count']} rows, {tx['with_amount']} with amount, {tx['ambiguous_dates']} ambiguous dates, {tx['duplicate_candidates']} duplicate candidates.", ss["BodyText"]))
    table("Transactions (first 60)", ["When (UTC) / raw", "Account", "Dir", "Amount (paise)", "Counterparty", "Ref", "Locator"],
          [[f"{r['when_utc'] or '?'}<br/>{r['when_raw'] or ''} [{r['precision']}]", r["account"], r["direction"], r["amount_minor"], r["counterparty"] or "—", r["reference"] or "—", str(r["locator"])] for r in tx["rows"][:60]],
          [3.6 * cm, 2.6 * cm, 1 * cm, 2 * cm, 3.2 * cm, 2.6 * cm, 3 * cm])
    table("Reconstructed fund paths (time-ordered)", ["Hops", "Accounts", "Entry (paise)", "Exit (paise)", "Time uncertain"],
          [[p["hop_count"], " → ".join(p["accounts"]), p["total_in_minor"], p["exit_amount_minor"], p["time_uncertain"]] for p in report["fund_paths"][:25]], [1.2 * cm, 9.5 * cm, 2.3 * cm, 2.3 * cm, 2.5 * cm])
    table("Account triage signals (rules; requires review — not a guilt decision)", ["Account", "Signal", "Score (heuristic)", "Reasons"],
          [[a["account"], a["label"], a["heuristic_score"], ", ".join(a["reasons"])] for a in report["account_triage"] if a["reasons"]][:30], [3 * cm, 5 * cm, 2 * cm, 8 * cm])
    table("Domain / IP / DNS / hosting observations (with observation times)", ["Type", "Source", "Target", "Level", "Observed", "Valid", "Limitations"],
          [[r["type"], r["source"], r["target"], r["evidence_level"], r["observed_at"] or "?", f"{r['valid_from'] or '?'} → {r['valid_to'] or 'open'}", "; ".join(r["limitations"][:3])] for r in report["infrastructure_observations"]],
          [2.6 * cm, 3.2 * cm, 3 * cm, 2 * cm, 2.4 * cm, 2.8 * cm, 2 * cm])
    table("Relationship table (evidence level + source locator)", ["Type", "Source → Target", "Level", "Review", "Method", "Source locator"],
          [[r["type"], f"{r['source']} → {r['target']}", r["evidence_level"], r["review_status"], r["method"], "; ".join(f"{s['file']}:{s['locator']}" for s in r["sources"]) or "—"] for r in report["relationships"][:120]],
          [2.8 * cm, 5 * cm, 2.2 * cm, 1.8 * cm, 2.4 * cm, 3.8 * cm])
    table("Counter-evidence and alternative explanations", ["Relationship", "Kind", "Severity", "Description"],
          [[c["relationship_id"][:8], c["kind"], c["severity"], c["description"]] for c in report["counter_evidence"]], [2 * cm, 4 * cm, 1.6 * cm, 10.4 * cm])
    # Explainable account behaviour: each pattern with the threshold it was judged against, the rows behind it
    # and the ordinary explanations that fit the same records. A score on its own is not explainable.
    typo = report.get("typologies") or {}
    typo_rows = []
    for prof in typo.get("profiles") or []:
        for t_ in prof.get("typologies") or []:
            if not (t_.get("triggered") or t_.get("status") in {"not_enough_history", "not_enough_evidence"}):
                continue
            th = {k: v for k, v in (t_.get("thresholds") or {}).items() if k != "why"}
            typo_rows.append([prof.get("masked_account_ref"), t_.get("type"), t_.get("status"),
                              t_.get("explanation"), str(th),
                              "; ".join(t_.get("supporting_transactions") or [])[:120] or "—",
                              "; ".join(t_.get("alternatives") or []) or "—"])
    table("Account behaviour patterns (explainable; requires review — not a finding about any person)",
          ["Account", "Pattern", "State", "What was observed", "Judged against", "Rows", "Ordinary explanations"],
          typo_rows[:40],
          [2.4 * cm, 2.6 * cm, 1.8 * cm, 4.4 * cm, 2.4 * cm, 2.2 * cm, 2.8 * cm])

    # Where a path stops, and the record that would continue it. Never "the money stopped".
    unresolved_paths = [[p_["hop_count"], " → ".join(p_["accounts"]), p_.get("status"),
                         p_.get("unresolved_reason") or "—", p_.get("resolution_hint") or "—"]
                        for p_ in report["fund_paths"] if p_.get("status") != "complete"][:25]
    table("Unresolved path ends and the record that would resolve each",
          ["Hops", "Accounts", "Status", "Why it stops", "What would resolve it"], unresolved_paths,
          [1.2 * cm, 6 * cm, 2 * cm, 4.4 * cm, 5 * cm])

    table("Information request drafts (drafted by this system; never transmitted by it)",
          ["Custodian", "Target", "Records requested", "Window", "Status", "Legal authority"],
          [[r_["custodian_type"], r_["target_entity"] or r_["target_record"],
            "; ".join(r_["records_requested"])[:120] or "—",
            f"{r_['window_from'] or '?'} → {r_['window_to'] or '?'}", r_["status"], r_["legal_authority"]]
           for r_ in (report.get("evidence_requests") or [])[:30]],
          [2.4 * cm, 3.4 * cm, 4.6 * cm, 3.4 * cm, 2 * cm, 2.8 * cm])

    u = report["unresolved"]
    story.append(Paragraph(f"<b>Unresolved gaps</b>: {u['relationships_requiring_review']} relationships await review; {len(u['parser_warnings'])} parser warnings.", ss["BodyText"]))
    table("Parser warnings", ["File", "Warning"], [[g["file"], g["warning"]] for g in u["parser_warnings"][:80]], [6 * cm, 12 * cm])
    story.append(Paragraph("<b>Limitations</b>", ss["Heading3"]))
    for line in report.get("limitations") or [report["disclaimer"]]:
        story.append(Paragraph(f"• {line}", small))
    story.append(Spacer(1, 10))
    story.append(Paragraph(report["disclaimer"], small))
    doc.build(story)
    return buf.getvalue()


def simple_table_pdf(title: str, banners: list[str], sections: list[tuple[str, list[str], list[list]]]) -> bytes:
    """Generic deterministic PDF: a title, banner lines and (heading, header, rows) sections. Used by claims and cooperation packs."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.5 * cm, rightMargin=1.5 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm, title=title)
    ss = getSampleStyleSheet()
    small = ss["BodyText"]
    small.fontSize = 8
    small.leading = 10
    story = [Paragraph(title, ss["Title"])]
    for b in banners:
        story.append(Paragraph(f"<font color='#8a1c1c'><b>{b}</b></font>" if b.isupper() else b, small))
    story.append(Spacer(1, 8))
    for heading, header, rows in sections:
        story.append(Paragraph(f"<b>{heading}</b>", ss["Heading3"]))
        data = [header] + (rows or [["(none)"] + [""] * (len(header) - 1)])
        data = [[Paragraph(str(x)[:300], small) for x in r] for r in data]
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(t)
        story.append(Spacer(1, 6))
    story.append(Paragraph(DISCLAIMER, small))
    doc.build(story)
    return buf.getvalue()
