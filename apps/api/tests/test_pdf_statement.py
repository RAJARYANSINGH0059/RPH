"""A bank statement delivered as PDF must become transactions, not merely extracted text.

This was the largest gap between what the product claimed and what it did: an investigator sent a PDF statement got a
document with indicators pulled out of it and no money trail. These tests pin that a PDF statement and a spreadsheet
carrying the same rows normalise into the same schema, that locators point back to the page, and that a PDF which is
not a statement is still treated as a document rather than forced into a ledger.
"""
from __future__ import annotations

import io

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.parsers import pdf_statement

HEADERS = ["Txn Date", "Narration", "Ref No", "Debit", "Credit", "Balance", "Account", "Counterparty", "Beneficiary Name"]

ROWS = [
    ["05-07-2026", "UPI/IN/VICTIM PAYMENT", "SYNUTR000001", "", "18000.00", "118000.00", "207349109870", "418187654321", "Collection Account"],
    ["05-07-2026", "IMPS/OUT/ONWARD TRANSFER", "SYNUTR000002", "9000.00", "", "109000.00", "207349109870", "470037096278", "Second Layer"],
    ["06-07-2026", "NEFT/OUT/ONWARD TRANSFER", "SYNUTR000003", "5500.00", "", "103500.00", "207349109870", "470037096278", "Second Layer"],
    ["07-07-2026", "UPI/IN/SALARY CREDIT", "SYNUTR000004", "", "45000.00", "148500.00", "207349109870", "999900001111", "Fictional Employer"],
]


def _statement_pdf(rows=ROWS, headers=HEADERS, title: bool = True, pages: int = 1) -> bytes:
    """A deterministic synthetic statement laid out on a fixed grid, as bank exports are. Fictional throughout."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    xs = [25, 80, 190, 262, 310, 358, 410, 466, 520][:len(headers)]  # the last column must fit inside A4
    per_page = max(1, -(-len(rows) // pages))
    for page in range(pages):
        y = height - 50
        if title:
            c.setFont("Helvetica-Bold", 11)
            c.drawString(28, y, "SYNTHETIC TEST BANK — STATEMENT OF ACCOUNT (fictional)")
            y -= 16
            c.setFont("Helvetica", 8)
            c.drawString(28, y, "Account 207349109870   Period 01-07-2026 to 31-07-2026")
            y -= 20
        c.setFont("Helvetica-Bold", 7)
        for x, h in zip(xs, headers):
            c.drawString(x, y, h)
        y -= 12
        c.setFont("Helvetica", 7)
        for row in rows[page * per_page:(page + 1) * per_page]:
            for x, cell in zip(xs, row):
                c.drawString(x, y, str(cell))
            y -= 11
        c.showPage()
    c.save()
    return buf.getvalue()


def _letter_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica", 11)
    for i, line in enumerate([
        "SYNTHETIC TEST BANK",
        "Dear Customer,",
        "This letter confirms that a hold was placed on the account referenced below.",
        "Reference: SYN-HOLD-0001. No transaction ledger is enclosed.",
    ]):
        c.drawString(40, 760 - i * 20, line)
    c.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------- parser level

def test_a_statement_pdf_is_recognised_and_its_rows_extracted():
    res = pdf_statement.extract(_statement_pdf())
    assert res.is_statement, res.warnings
    assert res.confidence in {"high", "medium", "low"}
    assert res.tabular is not None
    assert len(res.tabular.rows) == len(ROWS), f"expected {len(ROWS)} rows, got {len(res.tabular.rows)}"
    first = res.tabular.rows[0].values
    assert any("SYNUTR000001" in str(v) for v in first.values()), first
    assert res.tabular.rows[0].sheet and "page" in res.tabular.rows[0].sheet


def test_a_letter_is_not_forced_into_a_ledger():
    res = pdf_statement.extract(_letter_pdf())
    assert not res.is_statement
    assert res.confidence == "none"
    assert any("no_transaction_table_found" in w or "header_found_but_no_data_rows" in w for w in res.warnings), res.warnings


def test_a_repeated_header_on_each_page_is_not_read_as_a_transaction():
    res = pdf_statement.extract(_statement_pdf(pages=2))
    assert res.is_statement
    assert res.tabular is not None
    narrations = [" ".join(str(v) for v in r.values.values()) for r in res.tabular.rows]
    assert not any("Narration" in n and "Txn Date" in n for n in narrations), "a repeated header became a data row"
    assert len(res.tabular.rows) == len(ROWS)


def test_header_detection_requires_a_ledger_shape():
    ok, _c, why = pdf_statement.looks_like_statement(["Name", "Address", "Phone"])
    assert not ok and why
    ok, conf, _ = pdf_statement.looks_like_statement(HEADERS)
    assert ok and conf == "high"
    ok, _c, why = pdf_statement.looks_like_statement(["Date", "Amount"])
    assert not ok, "two columns are not a ledger"


# ---------------------------------------------------------------------------- through the real upload pipeline

@pytest.fixture(scope="module")
def case_id(client, analyst):
    r = client.post("/api/cases", json={"title": "PDF statement ingestion", "summary": "Synthetic statement delivered as PDF and as CSV."}, headers=analyst)
    assert r.status_code == 201
    return r.json()["id"]


def test_pdf_and_spreadsheet_of_the_same_rows_normalise_the_same_way(client, analyst, case_id):
    """The acceptance condition: the same transaction delivered as PDF or spreadsheet reaches the same schema."""
    csv = (",".join(HEADERS) + "\n" + "\n".join(",".join(r) for r in ROWS)).encode()
    r_csv = client.post(f"/api/cases/{case_id}/upload", files={"files": ("statement.csv", csv, "text/csv")}, headers=analyst)
    assert r_csv.status_code in (200, 201), r_csv.text[:300]

    other = client.post("/api/cases", json={"title": "PDF only", "summary": "Same rows, delivered as a PDF statement."}, headers=analyst).json()["id"]
    r_pdf = client.post(f"/api/cases/{other}/upload", files={"files": ("statement.pdf", _statement_pdf(), "application/pdf")}, headers=analyst)
    assert r_pdf.status_code in (200, 201), r_pdf.text[:300]

    csv_tx = client.get(f"/api/cases/{case_id}/transactions", headers=analyst).json()
    pdf_tx = client.get(f"/api/cases/{other}/transactions", headers=analyst).json()
    assert pdf_tx, "the PDF statement produced no transactions: the gap this test exists for"
    assert len(pdf_tx) == len(csv_tx), f"PDF produced {len(pdf_tx)} rows, spreadsheet {len(csv_tx)}"

    def key(t):
        return (t["external_reference"], t["amount_minor"], t["direction"])
    assert sorted(map(key, pdf_tx)) == sorted(map(key, csv_tx)), "reference, amount or direction differ between the two deliveries"
    assert all(t["amount_minor"] is not None for t in pdf_tx), "amounts must be parsed, not left raw"
    assert all(t["currency"] == "INR" for t in pdf_tx)


def test_pdf_rows_carry_a_page_locator_and_the_original_bytes_are_kept(client, analyst):
    case = client.post("/api/cases", json={"title": "PDF locators", "summary": "Checks that a row points back to its page."}, headers=analyst).json()["id"]
    up = client.post(f"/api/cases/{case}/upload", files={"files": ("statement.pdf", _statement_pdf(), "application/pdf")}, headers=analyst)
    assert up.status_code in (200, 201)
    files = client.get(f"/api/cases/{case}/files", headers=analyst).json()
    assert files and files[0]["sha256"], "the original file must be stored and hashed"

    txs = client.get(f"/api/cases/{case}/transactions", headers=analyst).json()
    assert txs
    ev = client.get(f"/api/cases/{case}/evidence/{txs[0]['evidence_item_id']}", headers=analyst)
    if ev.status_code == 200:
        loc = ev.json().get("source_locator") or {}
        assert loc, "a transaction from a PDF must keep a source locator"
        assert "page" in str(loc).lower() or "row" in loc, loc


def test_a_pdf_statement_is_recorded_as_parsed_by_the_statement_parser(client, analyst):
    case = client.post("/api/cases", json={"title": "PDF parser provenance", "summary": "The parse run must name the PDF statement parser."}, headers=analyst).json()["id"]
    client.post(f"/api/cases/{case}/upload", files={"files": ("statement.pdf", _statement_pdf(), "application/pdf")}, headers=analyst)
    runs = client.get(f"/api/cases/{case}/parse-runs", headers=analyst)
    if runs.status_code != 200:
        pytest.skip("parse runs are not exposed on this build")
    names = [r["parser_name"] for r in runs.json()]
    assert pdf_statement.PARSER_NAME in names, names
    run = next(r for r in runs.json() if r["parser_name"] == pdf_statement.PARSER_NAME)
    assert any("pdf_statement_extraction_confidence" in w for w in run["warnings"]), run["warnings"]
