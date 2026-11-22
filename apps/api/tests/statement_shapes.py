"""Statement layouts this repository's own factory does not produce.

The synthetic case factory emits statements in the shape this parser already understands, so a suite built only
on it proves the parser agrees with itself. R4C supplies its own sample statements on the day, and the layouts
below are the shapes real Indian bank exports actually take: a preamble above the header, columns named
"Withdrawal Amt." rather than "debit", a single signed amount column with a Dr/Cr suffix, Indian digit grouping,
four different date conventions, and a workbook whose statement is not on the first sheet.

These are fixtures, not assertions. What the parser does with them is measured in `test_statement_rehearsal.py`.
Everything here is fictional and uses documentation-range identifiers.
"""
from __future__ import annotations

import io

import openpyxl

VICTIM = "418187654321"
COLLECTION = "207349109870"
LAYER2 = "470037096278"


# ------------------------------------------------------------------------------- CSV shapes

def hdfc_style() -> bytes:
    """Preamble lines, dotted abbreviations, separate withdrawal/deposit columns, dd/mm/yy dates."""
    return (
        "HDFC-LIKE SYNTHETIC BANK\r\n"
        "Account Holder : COMPLAINANT V1 (SYNTHETIC)\r\n"
        "Account No : 418187654321    Statement Period : 01/05/2026 to 31/05/2026\r\n"
        "\r\n"
        "Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance\r\n"
        "01/05/26,UPI-REFUND DESK-PAY@EXAMPLE-SYNUTR2026000417,SYNUTR2026000417,01/05/26,\"1,80,000.00\",,\"42,500.00\"\r\n"
        "02/05/26,SALARY CREDIT MAY,SYNREF00090001,02/05/26,,\"45,000.00\",\"87,500.00\"\r\n"
        "03/05/26,IMPS-207349109870-ONWARD,SYNUTR2026000418,03/05/26,\"9,000.00\",,\"78,500.00\"\r\n"
        "\r\n"
        "*** End of Statement ***\r\n"
        "Downloaded by: synthetic fixture\r\n"
    ).encode()


def sbi_style() -> bytes:
    """Tab-separated, 'Txn Date' plus a separate value date, and a Ref No./Cheque No. column."""
    return (
        "Account Name\t: COMPLAINANT V1\n"
        "Account Number\t: 418187654321\n"
        "\n"
        "Txn Date\tValue Date\tDescription\tRef No./Cheque No.\tDebit\tCredit\tBalance\n"
        "01-05-2026\t01-05-2026\tTO TRANSFER UPI/DR/SYNUTR2026000417/REFUNDDESK\tSYNUTR2026000417\t180000.00\t\t42500.00\n"
        "02-05-2026\t02-05-2026\tBY TRANSFER NEFT/CR/SALARY\tSYNREF00090002\t\t45000.00\t87500.00\n"
        "03-05-2026\t03-05-2026\tTO TRANSFER IMPS/DR/207349109870\tSYNUTR2026000418\t9000.00\t\t78500.00\n"
    ).encode()


def signed_amount_with_dr_cr() -> bytes:
    """One amount column carrying the direction as a suffix, which many exports do."""
    return (
        "Transaction Date,Particulars,Transaction ID,Amount,Balance,Mode\r\n"
        "01 May 2026,Payment to refund desk,SYNUTR2026000417,\"1,80,000.00 Dr\",\"42,500.00\",UPI\r\n"
        "02 May 2026,Salary credit,SYNREF00090003,\"45,000.00 Cr\",\"87,500.00\",NEFT\r\n"
        "03 May 2026,Onward transfer,SYNUTR2026000418,\"9,000.00 Dr\",\"78,500.00\",IMPS\r\n"
    ).encode()


def rupee_symbol_and_iso_dates() -> bytes:
    """A currency symbol in the cell, ISO dates, and a direction column rather than two amount columns."""
    return (
        "Posting Date,Remarks,UTR,Type,Amount,Running Balance,Beneficiary Account\r\n"
        # Amounts are quoted, as valid CSV must quote a field containing its own delimiter. A file that
        # does not is malformed, and the parser reports that separately as a column-count mismatch.
        "2026-05-01T09:12:00,Refund desk payment,SYNUTR2026000417,DR,\"₹ 1,80,000.00\",\"₹ 42,500.00\",207349109870\r\n"
        "2026-05-02T18:40:00,Salary,SYNREF00090004,CR,\"₹ 45,000.00\",\"₹ 87,500.00\",\r\n"
        "2026-05-03T11:48:00,Onward,SYNUTR2026000418,DR,\"₹ 9,000.00\",\"₹ 78,500.00\",470037096278\r\n"
    ).encode()


def ambiguous_dates_and_missing_reference() -> bytes:
    """Dates that could be read either way, and rows with no reference at all."""
    return (
        "Date,Details,Reference,Withdrawal,Deposit,Balance\r\n"
        "05/01/2026,Payment,,1800.00,,42500.00\r\n"
        "06/02/2026,Credit,,,4500.00,47000.00\r\n"
        "13/02/2026,Unambiguous because 13 cannot be a month,SYNREF00090005,500.00,,46500.00\r\n"
    ).encode()


def headerless_preamble_trap() -> bytes:
    """A preamble line of three text cells, which a naive header detector would mistake for the header."""
    return (
        "Branch Name,Branch Code,IFSC\r\n"
        "SYNTHETIC MAIN,00123,SYNB0000123\r\n"
        "\r\n"
        "Txn Date,Narration,UTR,Debit,Credit,Balance\r\n"
        "01/05/2026,Refund desk payment,SYNUTR2026000417,180000.00,,42500.00\r\n"
        "02/05/2026,Salary,SYNREF00090006,,45000.00,87500.00\r\n"
    ).encode()


def unmappable_columns() -> bytes:
    """Columns a parser should not guess at. The analyst remaps these by hand."""
    return (
        "Col1,Col2,Col3,Col4,Col5\r\n"
        "01/05/2026,Refund desk payment,SYNUTR2026000417,180000.00,42500.00\r\n"
        "02/05/2026,Salary,SYNREF00090007,-45000.00,87500.00\r\n"
    ).encode()


# ------------------------------------------------------------------------------- XLSX shapes

def _book(sheets: list[tuple[str, list[list]]]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets:
        ws = wb.create_sheet(title=name)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


ICICI_HEADERS = ["S No.", "Value Date", "Transaction Date", "Cheque Number", "Transaction Remarks",
                 "Withdrawal Amount (INR )", "Deposit Amount (INR )", "Balance (INR )"]
ICICI_ROWS = [
    [1, "01/05/2026", "01/05/2026", "SYNUTR2026000417", "UPI/REFUNDDESK/PAYMENT", 180000.00, None, 42500.00],
    [2, "02/05/2026", "02/05/2026", "SYNREF00090008", "NEFT/SALARY", None, 45000.00, 87500.00],
    [3, "03/05/2026", "03/05/2026", "SYNUTR2026000418", "IMPS/ONWARD/207349109870", 9000.00, None, 78500.00],
]


def xlsx_titled_first_sheet() -> bytes:
    """Title rows above the header, on the first sheet."""
    return _book([("Statement", [
        ["SYNTHETIC TEST BANK"],
        ["Account Number", "418187654321"],
        ["Period", "01-05-2026 to 31-05-2026"],
        [],
        ICICI_HEADERS,
        *ICICI_ROWS,
    ])])


def xlsx_statement_on_second_sheet() -> bytes:
    """The workbook opens on a cover sheet; the statement is behind it.

    This is the shape that silently loses an entire statement if a parser only reads the first worksheet.
    """
    return _book([
        ("Cover", [["SYNTHETIC TEST BANK"], ["Customer", "COMPLAINANT V1"], ["Generated", "2026-05-31"]]),
        ("Account Statement", [ICICI_HEADERS, *ICICI_ROWS]),
    ])


def xlsx_two_accounts_two_sheets() -> bytes:
    """Two accounts in one workbook, one sheet each: both are evidence."""
    second = [
        [1, "03/05/2026", "03/05/2026", "SYNUTR2026000418", "IMPS/IN/FROM VICTIM", None, 9000.00, 26310.00],
        [2, "03/05/2026", "03/05/2026", "SYNUTR2026000431", "NEFT/OUT/LAYER TWO", 5000.00, None, 21310.00],
    ]
    return _book([
        ("418187654321", [ICICI_HEADERS, *ICICI_ROWS]),
        ("207349109870", [ICICI_HEADERS, *second]),
    ])


CSV_SHAPES = {
    "hdfc_style.csv": hdfc_style,
    "sbi_style.csv": sbi_style,
    "signed_amount_dr_cr.csv": signed_amount_with_dr_cr,
    "rupee_symbol_iso_dates.csv": rupee_symbol_and_iso_dates,
    "ambiguous_dates.csv": ambiguous_dates_and_missing_reference,
    "preamble_trap.csv": headerless_preamble_trap,
    "unmappable_columns.csv": unmappable_columns,
}

XLSX_SHAPES = {
    "titled_first_sheet.xlsx": xlsx_titled_first_sheet,
    "statement_on_second_sheet.xlsx": xlsx_statement_on_second_sheet,
    "two_accounts_two_sheets.xlsx": xlsx_two_accounts_two_sheets,
}
