"""The combined case workbook: one XLSX built from the canonical report, not from a second analysis.

PS05 names a combined case report among the three things the final must demonstrate, and the product could emit
JSON, PDF and a transactions CSV but not a workbook. This is that workbook.

The rule that matters most here is that it recomputes nothing. Every number comes from `build_report`, which
already carries the canonical counts, so a total in this file cannot disagree with the same total on the screen
or in the PDF. Hand-rolling a second set of sums per export is exactly how two parts of one case come to say
different things.

Three details that are easy to get wrong and expensive to get wrong:

Money stays an integer. `amount_minor` is the authoritative column and is written as a whole number of paise; the
rupee column beside it is a rendering for people reading the sheet, and the Read Me says so. A workbook that
stored money as a float would quietly change the evidence.

A cell that begins with `=`, `+`, `-` or `@` is prefixed with an apostrophe. Spreadsheet applications treat such
a value as a formula, so a narration or a filename out of an untrusted statement could otherwise execute when
the file is opened.

Absence is written as a word, never as an empty cell or a zero. A blank in a spreadsheet reads as nothing to
report; "not supplied" and "not assessable" read as what they are.
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timezone

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Case, EvidenceItem, SourceFile, Transaction
from app.models.twin import EvidenceRequest
from app.reports.builder import build_report
from app.services import infra_view, typologies

WORKBOOK_VERSION = "1.0.0"
MAX_ROWS_PER_SHEET = 50_000          # a bound, so one enormous case cannot exhaust memory mid-export

_FORMULA = re.compile(r"^[=+\-@]")
_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

HEADER_FILL = PatternFill("solid", fgColor="0E2238")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=9)
TITLE_FONT = Font(bold=True, size=12)
THIN = Side(style="thin", color="D9D2C5")
BORDER = Border(bottom=THIN)

NOT_SUPPLIED = "not supplied"


def _clean(value):
    """Make one Python value safe and legible in a cell.

    Integers stay integers so money keeps its precision. Everything else becomes text, because a spreadsheet
    guessing at a type is how a reference like 0012345 loses its leading zeros.
    """
    if value is None or value == "":
        return NOT_SUPPLIED
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple, set)):
        joined = " · ".join(str(v) for v in value)
        return joined or "none"
    if isinstance(value, dict):
        return " · ".join(f"{k}={v}" for k, v in value.items()) or "none"
    text = _ILLEGAL.sub("", str(value))
    if _FORMULA.match(text):
        text = "'" + text           # a value, never a formula
    return text


def _rupees(minor) -> str:
    """Rupees rendered from the integer, by integer arithmetic. `amount_minor` remains the authoritative column."""
    if minor is None:
        return NOT_SUPPLIED
    sign = "-" if minor < 0 else ""
    whole, paise = divmod(abs(int(minor)), 100)
    return f"{sign}{whole:,}.{paise:02d}"


class _Sheet:
    """A sheet with a header row that freezes, filters and does not need re-styling at each call site."""

    def __init__(self, wb: Workbook, name: str, headers: list[str] | None = None, widths: list[int] | None = None):
        self.ws = wb.create_sheet(title=name[:31])
        self.row = 1
        self.cols = len(headers or [])
        if headers:
            for i, h in enumerate(headers, start=1):
                cell = self.ws.cell(row=1, column=i, value=h)
                cell.fill, cell.font = HEADER_FILL, HEADER_FONT
                cell.alignment = Alignment(vertical="center", wrap_text=False)
            self.ws.freeze_panes = "A2"
            self.ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"
            self.row = 2
            for i, w in enumerate(widths or [], start=1):
                self.ws.column_dimensions[get_column_letter(i)].width = w

    def add(self, values: list):
        if self.row > MAX_ROWS_PER_SHEET:
            return False
        for i, v in enumerate(values, start=1):
            self.ws.cell(row=self.row, column=i, value=_clean(v))
        self.row += 1
        return True

    def note(self, text: str, bold: bool = False):
        cell = self.ws.cell(row=self.row, column=1, value=_clean(text))
        if bold:
            cell.font = TITLE_FONT
        self.row += 1
        return cell

    def blank(self):
        self.row += 1


# --------------------------------------------------------------------------------------------- sheets

def _read_me(wb: Workbook, case: Case, report: dict) -> None:
    sh = _Sheet(wb, "Read Me")
    sh.ws.column_dimensions["A"].width = 34
    sh.ws.column_dimensions["B"].width = 96
    sh.note("PS05-X combined case workbook", bold=True)
    sh.blank()
    for k, v in [
        ("Case", f"{case.title} ({case.id})"),
        ("Internal reference", case.internal_ref or NOT_SUPPLIED),
        ("Data status", report["case"]["data_status"]),
        ("Live connections", report["case"]["live_connections"]),
        ("Generated at", report["generated_at"]),
        ("Generator", report["generator"]),
        ("Report version", report["report_version"]),
        ("Workbook version", WORKBOOK_VERSION),
        ("Counts version", report["counts"]["version"]),
    ]:
        sh.ws.cell(row=sh.row, column=1, value=k).font = Font(bold=True, size=9)
        sh.ws.cell(row=sh.row, column=2, value=_clean(v))
        sh.row += 1
    sh.blank()
    sh.note("What this workbook is", bold=True)
    for line in [
        "Every sheet is built from one canonical report, so a total here cannot disagree with the same total on "
        "screen, in the PDF or in the JSON export.",
        "Each sheet carries the evidence behind its rows: the source file, and the page, sheet or row inside it.",
    ]:
        sh.note(line)
    sh.blank()
    sh.note("What this workbook is not", bold=True)
    for line in [
        report["disclaimer"],
        "No account is labelled and no person is named. No figure here expresses a probability of criminal "
        "involvement.",
        "Subscriber, login and KYC records are not publicly discoverable and are not presented as such. They can "
        "only be obtained through the applicable lawful process.",
    ]:
        sh.note(line)
    sh.blank()
    sh.note("Definitions used throughout", bold=True)
    for k, v in [
        ("amount_minor", "The authoritative amount, as a whole number of paise. Money is never stored as a "
                         "decimal number. The rupee column beside it is a rendering for readers."),
        ("directly observed", "Read from a supplied record."),
        ("corroborated", "The same fact observed in two independent records. Counted once, not twice."),
        ("derived", "Computed by this system from other evidence, with the method named."),
        ("candidate", "A link worth knowing about that does not support a conclusion on its own."),
        ("contradicted", "Evidence that conflicts with another observation; both are kept."),
        ("stale", "An observation whose validity window has passed."),
        ("not supplied / unknown", "No record covers this. It is not a finding of zero."),
        ("not assessable", "The evidence does not cover the period needed to judge the question."),
        ("unresolved end", "A trail stop caused by a missing record, with the record that would continue it."),
    ]:
        sh.ws.cell(row=sh.row, column=1, value=k).font = Font(bold=True, size=9)
        sh.ws.cell(row=sh.row, column=2, value=_clean(v)).alignment = Alignment(wrap_text=True, vertical="top")
        sh.row += 1


def _summary(wb: Workbook, report: dict, infra: dict, profiles: dict) -> None:
    counts = report["counts"]
    sh = _Sheet(wb, "Summary", ["Measure", "Value", "Definition or note"], [42, 16, 92])
    tx, rel, paths = counts["transactions"], counts["relationships"], counts.get("paths") or {}
    defs = counts.get("definitions") or {}
    rows = [
        ("Evidence files", counts["files"]["total"], defs.get("files", "Files supplied to this case.")),
        ("Transactions, total", tx["total"], defs.get("transactions", "Parsed statement rows.")),
        ("Transactions excluding duplicates", tx["excluding_duplicates"],
         "Duplicate rows are kept as evidence and excluded from this figure, never deleted."),
        ("Transactions with an amount", tx["with_amount"], "A row whose amount could not be parsed is still kept."),
        ("Duplicate candidates", tx["duplicates"], "Flagged, not removed."),
        ("Entities", counts["entities"]["total"], "Accounts, identifiers, domains, addresses and files."),
        ("Relationships, total", rel["total"], defs.get("relationships", "")),
        ("Relationships in the graph", rel.get("in_graph"), "Both endpoints are entities in this case."),
        ("Relationships in report tables", rel.get("in_report_tables"),
         "Document-link edges are excluded from presentation; this is why the two figures differ."),
        ("Relationships awaiting review", rel.get("awaiting_review"),
         "Candidate, stale or contradicted and not yet reviewed by a person."),
        ("Parser warnings", counts.get("parser_warnings"), "Things for a person to check, not errors."),
        ("Fund paths reconstructed", paths.get("total"), "Multi-hop paths across the supplied statements."),
        ("Paths resolved", paths.get("resolved"), "The last account's own statement is in the case."),
        ("Paths unresolved", paths.get("unresolved"),
         "A statement is missing. Unknown, never a finding that the money stopped."),
        ("Accounts examined for patterns", profiles.get("accounts_examined"),
         "Every account with movement in the supplied statements."),
        ("Accounts showing a pattern", profiles.get("accounts_with_a_pattern"),
         "Each needs a human decision. No account is labelled."),
        ("Domains", infra["coverage_summary"]["domains"], "Named or observed in this case."),
        ("Domains with registration read", infra["coverage_summary"]["domains_with_registration"], ""),
        ("Addresses", infra["coverage_summary"]["addresses"], "IPv4 and IPv6."),
        ("Certificates", infra["coverage_summary"]["certificates"], "Issuance records, not proof of service."),
        ("Historical observation sources", infra["coverage_summary"]["historical_observation_sources"],
         "Dated observations, kept apart from current lookups."),
        ("Providers not configured", infra["coverage_summary"]["providers_not_configured"],
         "A provider reports live only after a real request has succeeded."),
    ]
    for r in rows:
        sh.add(list(r))
    sh.blank()
    sh.note("Relationships by evidence level", bold=True)
    for level, n in (rel.get("by_level") or {}).items():
        sh.add([level, n, ""])


def _transactions(wb: Workbook, db: Session, case: Case, report: dict) -> int:
    # Amount and currency are separate columns, and the source timezone comes from the evidence item: a
    # transaction row records the instant, while the item records how the source expressed it.
    sh = _Sheet(wb, "Transactions",
                ["transaction_id", "reference", "account", "counterparty", "counterparty_name", "direction",
                 "amount_inr", "amount_minor", "currency", "balance_after_minor", "event_time_utc", "time_raw",
                 "time_precision", "source_timezone", "channel", "narration", "quality_label", "duplicate_of",
                 "warnings", "evidence_item_id", "source_file", "source_sha256", "source_locator"],
                [36, 20, 18, 18, 24, 10, 14, 14, 10, 16, 22, 18, 12, 14, 10, 40, 14, 36, 30, 36, 30, 18, 26])
    files = {f.id: f for f in db.execute(select(SourceFile).where(SourceFile.case_id == case.id)).scalars()}
    items = {e.id: e for e in db.execute(select(EvidenceItem).where(EvidenceItem.case_id == case.id)).scalars()}
    rows = db.execute(select(Transaction).where(Transaction.case_id == case.id)
                      .order_by(Transaction.datetime_utc, Transaction.id)).scalars().all()
    written = 0
    for t in rows:
        item = items.get(t.evidence_item_id)
        sf = files.get(item.source_file_id) if item else None
        if not sh.add([t.id, t.external_reference, t.account_ref, t.counterparty_ref, t.counterparty_name_raw,
                       t.direction, _rupees(t.amount_minor), t.amount_minor, t.currency, t.balance_after_minor,
                       t.datetime_utc, t.datetime_raw, t.time_precision,
                       item.source_timezone if item else None, t.channel, t.narration_raw, t.quality_label,
                       t.duplicate_of, t.warnings, t.evidence_item_id,
                       sf.original_name if sf else None, sf.sha256[:16] if sf else None,
                       item.source_locator if item else None]):
            break
        written += 1
    if written < len(rows):
        sh.note(f"Truncated: {written} of {len(rows)} rows written, at the {MAX_ROWS_PER_SHEET} row bound.")
    return written


def _account_triage(wb: Workbook, report: dict, profiles: dict) -> None:
    sh = _Sheet(wb, "Account Triage",
                ["account", "masked_account", "assessment", "patterns_observed", "heuristic_score_not_probability",
                 "typology", "state", "triggered", "observed_values", "threshold", "why_this_threshold",
                 "supporting_transactions", "ordinary_explanations", "what_it_cannot_show",
                 "has_own_statement", "credits", "debits", "rule_version"],
                [20, 18, 34, 10, 14, 24, 16, 10, 48, 40, 48, 40, 60, 60, 12, 10, 10, 12])
    by_account = {row["account"]: row for row in report.get("account_triage") or []}
    for profile in profiles.get("profiles") or []:
        ref = profile["account_ref"]
        triage = by_account.get(ref, {})
        coverage = profile.get("evidence_coverage") or {}
        for t in profile.get("typologies") or []:
            sh.add([ref, profile.get("masked_account_ref"), profile.get("label"),
                    profile.get("patterns_observed"),
                    (profile.get("rules_triage") or {}).get("heuristic_score", triage.get("heuristic_score")),
                    t.get("type"), t.get("status"), t.get("triggered"),
                    t.get("observed_values"), {k: v for k, v in (t.get("thresholds") or {}).items() if k != "why"},
                    (t.get("thresholds") or {}).get("why"),
                    t.get("supporting_transactions"), t.get("alternatives"), t.get("limitations"),
                    coverage.get("has_own_statement"), coverage.get("transactions_in"),
                    coverage.get("transactions_out"), profiles.get("typology_version")])
    sh.blank()
    sh.note("A score here is a ranking signal for review. It is not a probability of criminal involvement, and no "
            "account or person is labelled.", bold=True)


def _money_paths(wb: Workbook, report: dict) -> None:
    sh = _Sheet(wb, "Money Paths",
                ["path", "hop", "from_account", "to_account", "amount_inr", "amount_minor", "reference",
                 "event_time", "time_precision", "hop_class", "path_class", "status", "flags",
                 "conservation_ratio", "unresolved_reason", "what_would_resolve_it", "evidence_item_id",
                 "algorithm_version"],
                [8, 6, 20, 20, 14, 14, 20, 22, 12, 16, 14, 14, 22, 14, 52, 52, 36, 12])
    for i, p in enumerate(report.get("fund_paths") or [], start=1):
        for h in p.get("hops") or []:
            sh.add([i, h.get("hop") or h.get("index"), h.get("src"), h.get("dst"),
                    _rupees(h.get("amount_minor")), h.get("amount_minor"), h.get("reference"),
                    h.get("time"), h.get("precision"), h.get("class"),
                    p.get("path_class"), p.get("status"), p.get("flags"), p.get("conservation_ratio"),
                    p.get("unresolved_reason"), p.get("resolution_hint"), h.get("evidence_item_id"),
                    p.get("algorithm_version")])
    sh.blank()
    sh.note("An unresolved path means a statement is missing, not that the money stopped or was recovered. The "
            "resolution hint names the record that would continue it.", bold=True)


def _infrastructure(wb: Workbook, infra: dict) -> None:
    sh = _Sheet(wb, "Infrastructure",
                ["kind", "subject", "record_or_field", "value", "state", "observed_or_window", "provider",
                 "evidence_item_id", "limitation"],
                [18, 34, 22, 48, 22, 30, 34, 36, 70])
    for d in infra.get("domains") or []:
        for record, rows in (d.get("records") or {}).items():
            for r in rows:
                values = []
                for v in r.get("values") or []:
                    values.append(v.get("ip") or v.get("target") or v.get("exchange") or v.get("nameserver")
                                  or v.get("hostname") or (" ".join(v.get("strings") or []) or v.get("raw")))
                sh.add(["DNS", d["domain"], record, values or r.get("status_meaning"), r.get("status"),
                        r.get("observed_at"), r.get("resolver") or r.get("provider"), r.get("evidence_item_id"),
                        "Current lookup; describes the observation time only."])
        if d.get("record_types_not_asked"):
            sh.add(["DNS", d["domain"], "not asked", d["record_types_not_asked"], "never queried", "", "", "",
                    "A record type nobody asked for is not an absent record."])
        reg = d.get("registration")
        if reg:
            sh.add(["Registration", d["domain"], "registrar",
                    f'{reg.get("registrar_name") or NOT_SUPPLIED} (IANA {reg.get("registrar_iana_id") or NOT_SUPPLIED})',
                    reg.get("status"), f'{reg.get("registered") or "?"} → {reg.get("expires") or "?"}',
                    reg.get("provider"), reg.get("evidence_item_id"),
                    "Current registration, not historical ownership. Registrant data is commonly withheld."])
            sh.add(["Registration", d["domain"], "registrant", reg.get("registrant_name"), reg.get("redaction"),
                    "", reg.get("provider"), reg.get("evidence_item_id"),
                    "A withheld field is reported as withheld and never filled in from elsewhere."])
        if d.get("discovered_names"):
            sh.add(["Discovered name", d["domain"], "certificate SAN", d["discovered_names"], "candidate", "", "",
                    "", "Certified, not observed serving, and not resolved by this system."])
    for a in infra.get("addresses") or []:
        alloc = a.get("allocation") or {}
        sh.add(["Address", a["ip"], "allocation", alloc.get("organisation") or alloc.get("network_name"),
                alloc.get("status") or "not supplied", alloc.get("allocated"), alloc.get("provider"),
                alloc.get("evidence_item_id"),
                "The organisation holding a range is not the subscriber and not a person's location."])
        ptr = a.get("reverse_dns") or {}
        sh.add(["Address", a["ip"], "reverse DNS", ptr.get("hostname"), ptr.get("status") or "not read",
                ptr.get("observed_at"), ptr.get("provider"), ptr.get("evidence_item_id"),
                "A PTR name is published by the address-block holder, not by whoever used the address."])
        netclass = a.get("network_classification") or {}
        sh.add(["Address", a["ip"], "VPN / proxy / Tor", netclass.get("classification") or "not checked",
                netclass.get("classification") and "checked" or "not configured", netclass.get("list_read_at"),
                netclass.get("provider"), netclass.get("evidence_item_id"),
                "A network classification describes the address, never the identity of whoever used it."])
    for c in infra.get("certificates") or []:
        sh.add(["Certificate", c.get("domain"), c.get("certificate_key"), c.get("san_names"),
                c.get("validity_state"), f'{c.get("not_before") or "?"} → {c.get("not_after") or "?"}',
                c.get("issuer_name"), c.get("evidence_item_id"),
                "A log entry records issuance. It does not establish that a site was serving."])
    for h in infra.get("historical_observations") or []:
        for r in h.get("records") or []:
            sh.add(["Historical", r.get("name"), r.get("record"), r.get("value"), "dated observation",
                    f'{r.get("first_seen") or "?"} → {r.get("last_seen") or "?"}', h.get("provider"),
                    h.get("evidence_item_id"),
                    "Dated evidence, kept apart from current lookups. The window is the observer's sighting range."])
    sh.blank()
    for line in infra.get("limitations") or []:
        sh.note(line)


def _relationships(wb: Workbook, report: dict) -> None:
    sh = _Sheet(wb, "Relationships",
                ["relationship_id", "type", "source", "source_type", "target", "target_type", "evidence_level",
                 "review_status", "method", "observed_at", "valid_from", "valid_to",
                 "heuristic_score_not_probability", "limitations", "source_file", "source_locator"],
                [36, 24, 28, 14, 28, 14, 18, 16, 28, 22, 22, 22, 14, 60, 30, 30])
    for r in report.get("relationships") or []:
        src = (r.get("sources") or [{}])[0]
        sh.add([r.get("id"), r.get("type"), r.get("source"), r.get("source_type"), r.get("target"),
                r.get("target_type"), r.get("evidence_level"), r.get("review_status"), r.get("method"),
                r.get("observed_at"), r.get("valid_from"), r.get("valid_to"),
                r.get("heuristic_score_not_probability"), r.get("limitations"),
                src.get("file"), src.get("locator")])


def _counter_evidence(wb: Workbook, report: dict, infra: dict) -> None:
    sh = _Sheet(wb, "Counter Evidence",
                ["subject", "kind", "severity", "what_weakens_the_reading", "what_would_resolve_it"],
                [40, 28, 12, 90, 70])
    for c in report.get("counter_evidence") or []:
        sh.add([c.get("relationship_id"), c.get("kind"), c.get("severity"), c.get("description"), ""])
    for s in infra.get("shared_certificate_names") or []:
        for n in (s.get("names") or [])[:50]:
            sh.add([f'{s.get("domain")} ↔ {n.get("name")}', "shared certificate", "medium",
                    n.get("alternatives"),
                    "A dated observation showing the name resolving and serving during the transaction window."])
    for f in infra.get("lookup_failures") or []:
        sh.add([f.get("name"), f"lookup {f.get('about')}", "low",
                f.get("status_meaning") or f.get("error"),
                "Repeating the lookup, or a dated observation from a provider."])
    sh.blank()
    sh.note("Counter-evidence is kept, not resolved away. Where two records conflict, both remain in this "
            "workbook and a person decides.", bold=True)


def _evidence_requests(wb: Workbook, db: Session, case: Case) -> None:
    sh = _Sheet(wb, "Evidence Requests",
                ["reference", "title", "custodian_type", "target_entity", "target_record", "window_from",
                 "window_to", "records_requested", "status", "legal_authority", "requesting_officer",
                 "rationale", "could_resolve", "would_not_establish", "transmitted_by_this_system"],
                [36, 40, 18, 28, 32, 22, 22, 50, 20, 28, 24, 60, 50, 50, 24])
    rows = db.execute(select(EvidenceRequest).where(EvidenceRequest.case_id == case.id)
                      .order_by(EvidenceRequest.id)).scalars().all()
    for r in rows:
        sh.add([r.id, r.title, r.organisation_type, r.target_entity, r.target_record, r.window_from, r.window_to,
                r.required_fields, r.status, r.legal_authority or "to be completed by an authorised officer",
                r.requesting_officer or "to be completed by an authorised officer", r.rationale,
                r.could_resolve, r.would_not_establish, "no"])
    sh.blank()
    sh.note("This system drafts requests and never transmits them. A status of dispatch_recorded is set by a "
            "person recording an actual dispatch.", bold=True)
    sh.note("Subscriber, login, access and KYC records are not publicly discoverable and are sought only through "
            "the applicable lawful process.")


def _evidence_index(wb: Workbook, db: Session, case: Case, report: dict) -> None:
    sh = _Sheet(wb, "Evidence Index",
                ["source_file", "sha256", "detected_kind", "size_bytes", "uploaded_at", "file_status",
                 "synthetic", "evidence_item_id", "source_type", "extraction_method", "parser",
                 "locator", "quality_flags"],
                [34, 66, 14, 12, 22, 14, 10, 36, 20, 22, 28, 30, 40])
    files = {f.id: f for f in db.execute(select(SourceFile).where(SourceFile.case_id == case.id)).scalars()}
    items = db.execute(select(EvidenceItem).where(EvidenceItem.case_id == case.id)
                       .order_by(EvidenceItem.id)).scalars().all()
    for e in items:
        f = files.get(e.source_file_id)
        if not sh.add([f.original_name if f else "(no file)", f.sha256 if f else None,
                       f.detected_kind if f else None, f.size_bytes if f else None,
                       f.uploaded_at if f else None, f.status if f else None, f.is_synthetic if f else None,
                       e.id, e.source_type, e.extraction_method, f"{e.parser_name}@{e.parser_version}",
                       e.source_locator, e.quality_flags]):
            break
    for f in files.values():
        if not any(e.source_file_id == f.id for e in items):
            sh.add([f.original_name, f.sha256, f.detected_kind, f.size_bytes, f.uploaded_at, f.status,
                    f.is_synthetic, "(no evidence item)", "", "", "", "", ""])
    sh.blank()
    sh.note("Every row above resolves to the original bytes by SHA-256, and to the exact page, sheet or row "
            "inside the file.", bold=True)


def _limitations(wb: Workbook, report: dict, infra: dict, profiles: dict) -> None:
    sh = _Sheet(wb, "Limitations", ["area", "limitation"], [28, 120])
    sh.add(["Report", report["disclaimer"]])
    for line in profiles.get("limitations") or []:
        sh.add(["Account patterns", line])
    for line in infra.get("limitations") or []:
        sh.add(["Infrastructure", line])
    gaps = (report.get("unresolved") or {}).get("parser_warnings") or []
    for g in gaps[:200]:
        sh.add(["Parsing", f'{g.get("file")}: {g.get("warning")}'])
    for line in [
        "A missing statement is reported as unknown. It is never evidence that no transaction occurred.",
        "Duplicate rows are kept as evidence and excluded from totals, never deleted.",
        "Timestamps carry their precision. Where a source gave no time zone, none is assumed.",
        "Heuristic scores rank accounts for review and are not calibrated probabilities.",
        "Any machine-learning output is advisory and never makes a decision.",
        "This workbook is an investigative aid. It is not a legal determination and makes no claim of court "
        "admissibility.",
    ]:
        sh.add(["General", line])
    unreviewed = (report.get("unresolved") or {}).get("relationships_requiring_review")
    if unreviewed:
        sh.add(["Review", f"{unreviewed} relationship(s) are candidate, stale or contradicted and have not yet "
                          f"been reviewed by a person."])


# --------------------------------------------------------------------------------------------- entry point

def case_workbook(db: Session, case: Case, report: dict | None = None) -> bytes:
    """Build the combined workbook for one case.

    `report` may be supplied by a caller that has already built it, so a route serving several formats does not
    reconstruct the case twice.
    """
    report = report or build_report(db, case)
    infra = infra_view.report(db, case)
    # The report already carries the profiles, so the workbook reads them rather than computing a second set
    # that could drift from the PDF's.
    profiles = report.get("typologies") or typologies.case_profiles(db, case)

    wb = Workbook()
    wb.remove(wb.active)                       # openpyxl creates a default sheet we do not want
    wb.properties.title = f"PS05-X case workbook — {case.title}"
    wb.properties.creator = report["generator"]
    wb.properties.description = ("Combined investigation workbook. Synthetic or uploaded case data; an "
                                 "investigative aid, not a legal determination.")

    _read_me(wb, case, report)
    _summary(wb, report, infra, profiles)
    _transactions(wb, db, case, report)
    _account_triage(wb, report, profiles)
    _money_paths(wb, report)
    _infrastructure(wb, infra)
    _relationships(wb, report)
    _counter_evidence(wb, report, infra)
    _evidence_requests(wb, db, case)
    _evidence_index(wb, db, case, report)
    _limitations(wb, report, infra, profiles)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def workbook_filename(case: Case) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"ps05x_case_workbook_{case.id[:8]}_{stamp}.xlsx"
