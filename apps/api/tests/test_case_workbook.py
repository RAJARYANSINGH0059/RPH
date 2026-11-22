"""The combined case workbook.

PS05 names a combined case report among the three things the final must demonstrate. These tests pin the four
properties that make a workbook trustworthy rather than merely present:

- it is a real workbook, with every sheet the specification names;
- its totals come from the canonical counts, so no sheet can disagree with the screen or the other exports;
- no cell can execute as a formula, however hostile the narration in a supplied statement;
- absence is written as a word, so an empty cell never reads as a finding of zero.
"""
from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook

from app.core.scopes import scope_permits
from app.reports.workbook import WORKBOOK_VERSION

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

REQUIRED_SHEETS = ["Read Me", "Summary", "Transactions", "Account Triage", "Money Paths", "Infrastructure",
                   "Relationships", "Counter Evidence", "Evidence Requests", "Evidence Index", "Limitations"]


@pytest.fixture(scope="module")
def case_id(client, analyst):
    r = client.post("/api/synthetic/generate",
                    json={"scenario_type": "desert_mirage", "difficulty": "messy", "size": "small", "seed": 8801},
                    headers=analyst)
    assert r.status_code == 201, r.text[:300]
    return r.json()["case"]["id"]


@pytest.fixture(scope="module")
def book(client, analyst, case_id):
    r = client.get(f"/api/cases/{case_id}/report.xlsx", headers=analyst)
    assert r.status_code == 200, r.text[:300]
    assert r.headers["content-type"].startswith(XLSX)
    return r


def _wb(resp):
    return load_workbook(io.BytesIO(resp.content))


def test_the_route_serves_a_real_workbook_as_an_attachment(book):
    assert book.content[:4] == b"PK\x03\x04", "an xlsx is a zip container; this must not be json with a new name"
    disp = book.headers["content-disposition"]
    assert disp.startswith("attachment;") and disp.endswith('.xlsx"')
    assert "ps05x_case_workbook_" in disp
    wb = _wb(book)
    assert wb.sheetnames, "the workbook opened but carries no sheet"


def test_every_sheet_the_specification_names_is_present(book):
    wb = _wb(book)
    missing = [s for s in REQUIRED_SHEETS if s not in wb.sheetnames]
    assert not missing, f"missing sheets: {missing}"


def test_the_filename_is_built_from_the_case_id_not_the_case_title(client, analyst):
    """A title is user input and has no business in a response header."""
    hostile = client.post("/api/cases", json={"title": 'Case "x"; filename=evil.exe', "summary": "Header safety."},
                          headers=analyst).json()["id"]
    r = client.get(f"/api/cases/{hostile}/report.xlsx", headers=analyst)
    assert r.status_code == 200
    disp = r.headers["content-disposition"]
    assert "evil.exe" not in disp and '"x"' not in disp
    assert hostile[:8] in disp


# ------------------------------------------------------------------ the property that matters most

def test_the_workbook_totals_are_the_canonical_counts(client, analyst, case_id, book):
    """One case, several exports, one set of numbers. A workbook that recomputed its own totals would be the
    defect this test exists to prevent."""
    counts = client.get(f"/api/cases/{case_id}/counts", headers=analyst).json()
    summary = {}
    for row in _wb(book)["Summary"].iter_rows(min_row=2, values_only=True):
        if row and row[0]:
            summary[str(row[0])] = row[1]

    assert summary["Evidence files"] == counts["files"]["total"]
    assert summary["Transactions, total"] == counts["transactions"]["total"]
    assert summary["Transactions excluding duplicates"] == counts["transactions"]["excluding_duplicates"]
    assert summary["Duplicate candidates"] == counts["transactions"]["duplicates"]
    assert summary["Entities"] == counts["entities"]["total"]
    assert summary["Relationships, total"] == counts["relationships"]["total"]
    assert summary["Relationships in report tables"] == counts["relationships"]["in_report_tables"]
    assert summary["Relationships awaiting review"] == counts["relationships"]["awaiting_review"]


def test_the_transactions_sheet_carries_every_parsed_row(client, analyst, case_id, book):
    txs = client.get(f"/api/cases/{case_id}/transactions", headers=analyst).json()
    ws = _wb(book)["Transactions"]
    ids = {r[0] for r in ws.iter_rows(min_row=2, max_col=1, values_only=True) if r[0]}
    assert len(ids) == len(txs), f"workbook has {len(ids)} rows, the case has {len(txs)}"
    assert {t["id"] for t in txs} == ids


def test_the_report_json_and_the_workbook_agree_on_the_same_case(client, analyst, case_id, book):
    rep = client.get(f"/api/cases/{case_id}/report.json", headers=analyst).json()
    summary = {str(r[0]): r[1] for r in _wb(book)["Summary"].iter_rows(min_row=2, values_only=True) if r and r[0]}
    assert summary["Transactions, total"] == rep["counts"]["transactions"]["total"]
    assert summary["Relationships, total"] == rep["counts"]["relationships"]["total"]


# ------------------------------------------------------------------ safety of the file itself

def test_no_cell_can_execute_as_a_formula(client, analyst):
    """A narration out of a supplied statement is untrusted text. If it survives into a cell beginning with an
    operator, opening the workbook executes it."""
    case = client.post("/api/cases", json={"title": "Formula injection", "summary": "Hostile statement content."},
                       headers=analyst).json()["id"]
    csv = (
        "Date,Narration,Ref No,Debit,Credit,Balance,Account,Counterparty\r\n"
        "01-05-2026,=HYPERLINK(\"http://attacker.example\";\"click\"),=cmd|'/c calc'!A1,1800.00,,42500.00,207349109870,418187654321\r\n"
        "02-05-2026,+SUM(1+1),@SUM(1+1),,4500.00,47000.00,207349109870,418187654321\r\n"
        "03-05-2026,-2+3,DDE|x,500.00,,46500.00,207349109870,418187654321\r\n"
    )
    up = client.post(f"/api/cases/{case}/upload", files={"files": ("hostile.csv", csv.encode(), "text/csv")},
                     headers=analyst)
    assert up.status_code in (200, 201), up.text[:300]

    r = client.get(f"/api/cases/{case}/report.xlsx", headers=analyst)
    assert r.status_code == 200
    wb = _wb(r)
    offenders = []
    for name in wb.sheetnames:
        for row in wb[name].iter_rows():
            for cell in row:
                v = cell.value
                if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
                    offenders.append((name, cell.coordinate, v[:40]))
    assert not offenders, f"cells that a spreadsheet would execute: {offenders[:5]}"

    # and the hostile text is still present, prefixed rather than discarded: it is evidence
    text = " ".join(str(c.value) for row in wb["Transactions"].iter_rows() for c in row if c.value)
    assert "HYPERLINK" in text, "the original narration must be preserved, not dropped"


def test_money_is_written_as_whole_paise_not_as_a_decimal(book):
    """Money is an integer everywhere in this product. A float in the workbook would change the evidence."""
    ws = _wb(book)["Transactions"]
    header = [c.value for c in ws[1]]
    minor_col = header.index("amount_minor") + 1
    rupee_col = header.index("amount_inr") + 1
    seen = 0
    for row in ws.iter_rows(min_row=2):
        v = row[minor_col - 1].value
        if isinstance(v, int):
            seen += 1
            assert not isinstance(v, float)
            rendered = row[rupee_col - 1].value
            assert isinstance(rendered, str) and rendered.endswith(f"{abs(v) % 100:02d}"), rendered
    assert seen, "no amounts were written at all"


def test_an_absence_is_written_as_a_word_rather_than_left_blank(book):
    wb = _wb(book)
    ws = wb["Transactions"]
    blanks = [c.coordinate for row in ws.iter_rows(min_row=2) for c in row if c.value is None]
    assert not blanks, f"blank cells read as nothing to report: {blanks[:5]}"
    joined = " ".join(str(c.value) for row in ws.iter_rows(min_row=2) for c in row if c.value)
    assert "not supplied" in joined


def test_headers_are_frozen_and_filterable(book):
    wb = _wb(book)
    for name in ["Transactions", "Summary", "Relationships", "Evidence Index"]:
        ws = wb[name]
        assert ws.freeze_panes == "A2", f"{name} header does not stay on screen"
        assert ws.auto_filter.ref, f"{name} cannot be filtered"


# ------------------------------------------------------------------ content the specification requires

def test_the_read_me_states_what_the_workbook_is_not(book):
    text = " ".join(str(c.value) for row in _wb(book)["Read Me"].iter_rows() for c in row if c.value).lower()
    assert "synthetic" in text
    assert "not" in text and ("admissibility" in text or "legal determination" in text)
    assert "amount_minor" in text, "the authoritative money column must be defined"
    assert "lawful process" in text
    assert WORKBOOK_VERSION in " ".join(
        str(c.value) for row in _wb(book)["Read Me"].iter_rows() for c in row if c.value)


def test_account_triage_carries_thresholds_rows_and_ordinary_explanations(book):
    ws = _wb(book)["Account Triage"]
    header = [c.value for c in ws[1]]
    for col in ("typology", "state", "threshold", "why_this_threshold", "supporting_transactions",
                "ordinary_explanations", "what_it_cannot_show"):
        assert col in header, f"the workbook drops {col}, which is what makes a pattern explainable"
    body = " ".join(str(c.value) for row in ws.iter_rows(min_row=2) for c in row if c.value)
    assert "rapid_in_out" in body or "pass_through" in body
    note = " ".join(str(c.value) for row in ws.iter_rows() for c in row if c.value).lower()
    assert "not a probability of criminal involvement" in note
    # Two engines assess an account and can disagree. A reader who is not told that reads it as a defect.
    assert "two independent assessments" in note
    assert "disagreement is information" in note
    assert "silence about a check is not an answer" in note


def test_money_paths_say_what_would_resolve_an_unresolved_end(book):
    ws = _wb(book)["Money Paths"]
    header = [c.value for c in ws[1]]
    assert "unresolved_reason" in header and "what_would_resolve_it" in header
    note = " ".join(str(c.value) for row in ws.iter_rows() for c in row if c.value).lower()
    assert "not that the money stopped" in note


def test_infrastructure_reports_record_types_that_were_never_asked(book):
    ws = _wb(book)["Infrastructure"]
    body = " ".join(str(c.value) for row in ws.iter_rows() for c in row if c.value)
    assert "not asked" in body or "DNS" in body
    assert "not a person's location" in body or "not the subscriber" in body


def test_evidence_requests_state_that_nothing_is_transmitted(book):
    ws = _wb(book)["Evidence Requests"]
    header = [c.value for c in ws[1]]
    assert "transmitted_by_this_system" in header
    body = " ".join(str(c.value) for row in ws.iter_rows() for c in row if c.value).lower()
    assert "never transmits" in body
    assert "lawful process" in body


def test_the_evidence_index_resolves_every_row_to_a_hash_and_a_locator(book):
    ws = _wb(book)["Evidence Index"]
    header = [c.value for c in ws[1]]
    for col in ("source_file", "sha256", "evidence_item_id", "locator", "extraction_method"):
        assert col in header
    rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if r[0] and r[0] != "not supplied"]
    assert rows, "no evidence rows at all"
    sha_col = header.index("sha256")
    assert any(isinstance(r[sha_col], str) and len(r[sha_col]) == 64 for r in rows), "no full file hash present"


def test_limitations_name_the_missing_statement_rule(book):
    body = " ".join(str(c.value) for row in _wb(book)["Limitations"].iter_rows() for c in row if c.value).lower()
    assert "never evidence that no transaction occurred" in body
    assert "not calibrated probabilities" in body or "rank accounts for review" in body


# ------------------------------------------------------------------ authorisation

def test_a_download_token_may_fetch_the_workbook_and_nothing_more():
    assert scope_permits("download", "GET", "/api/cases/{case_id}/report.xlsx")
    assert not scope_permits("download", "GET", "/api/auth/me")
    assert not scope_permits("upload", "GET", "/api/cases/{case_id}/report.xlsx")
    assert scope_permits("full", "GET", "/api/cases/{case_id}/report.xlsx")


def test_another_members_case_cannot_be_exported(client, supervisor, case_id):
    assert client.get(f"/api/cases/{case_id}/report.xlsx", headers=supervisor).status_code == 404


def test_an_unauthenticated_export_is_refused(client, case_id):
    assert client.get(f"/api/cases/{case_id}/report.xlsx").status_code in (401, 403)


def test_an_empty_case_still_produces_a_workbook_that_says_so(client, analyst):
    case = client.post("/api/cases", json={"title": "Empty case", "summary": "Nothing uploaded."},
                       headers=analyst).json()["id"]
    r = client.get(f"/api/cases/{case}/report.xlsx", headers=analyst)
    assert r.status_code == 200
    wb = _wb(r)
    assert all(s in wb.sheetnames for s in REQUIRED_SHEETS)
    summary = {str(x[0]): x[1] for x in wb["Summary"].iter_rows(min_row=2, values_only=True) if x and x[0]}
    assert summary["Transactions, total"] == 0
    body = " ".join(str(c.value) for row in wb["Limitations"].iter_rows() for c in row if c.value).lower()
    assert "never evidence that no transaction occurred" in body

# ------------------------------------------------------------------ the PDF carries the same story

def _pdf_text(content: bytes) -> str:
    import fitz

    import re

    with fitz.open(stream=content, filetype="pdf") as doc:
        raw = " ".join(page.get_text() for page in doc)
    # A heading that wraps puts a newline inside a phrase, so whitespace is collapsed before matching.
    return re.sub(r"\s+", " ", raw)


def test_the_pdf_report_carries_the_sections_the_specification_names(client, analyst, case_id):
    """The combined report is one of the three things PS05 asks the final to demonstrate, so the PDF has to carry
    the explanation and not only the findings."""
    r = client.get(f"/api/cases/{case_id}/report.pdf", headers=analyst)
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    text = _pdf_text(r.content)
    for heading in ["Summary", "Sources and hashes", "Parsing methods and warnings", "Transactions",
                    "Reconstructed fund paths", "Account behaviour patterns",
                    "Unresolved path ends", "Information request drafts", "Limitations"]:
        assert heading in text, f"the PDF has no {heading!r} section"


def test_the_pdf_summary_quotes_the_canonical_counts(client, analyst, case_id):
    counts = client.get(f"/api/cases/{case_id}/counts", headers=analyst).json()
    text = _pdf_text(client.get(f"/api/cases/{case_id}/report.pdf", headers=analyst).content)
    assert f"{counts['transactions']['total']} transaction" in text
    assert f"canonical counts service (v{counts['version']})" in text


def test_the_pdf_states_that_it_never_transmits_a_request(client, analyst, case_id):
    text = _pdf_text(client.get(f"/api/cases/{case_id}/report.pdf", headers=analyst).content)
    assert "never transmitted by it" in text
    assert "not a finding about any person" in text


def test_the_pdf_limitations_name_the_missing_statement_rule(client, analyst, case_id):
    text = _pdf_text(client.get(f"/api/cases/{case_id}/report.pdf", headers=analyst).content).lower()
    assert "never evidence that no transaction occurred" in text
    assert "not calibrated probabilities" in text


def test_the_json_export_carries_the_same_additions(client, analyst, case_id):
    rep = client.get(f"/api/cases/{case_id}/report.json", headers=analyst).json()
    assert "typologies" in rep and rep["typologies"]["profiles"]
    assert "evidence_requests" in rep
    assert "limitations" in rep and len(rep["limitations"]) >= 5
    assert all(r["transmitted_by_this_system"] is False for r in rep["evidence_requests"])
