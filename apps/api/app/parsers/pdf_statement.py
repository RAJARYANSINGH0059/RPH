"""Bank statements delivered as PDF.

A PDF statement used to enter the generic document pipeline: its text was extracted, indicators were pulled out of it,
and the transactions inside it never became transactions. An investigator who was sent a PDF statement therefore had
no money trail from it, which is the single largest gap between what the product claimed and what it did.

This module turns a PDF statement into exactly the structure the spreadsheet path already produces, so everything
downstream is shared: column mapping, money and date parsing, duplicate detection, balance reconciliation, source
locators, evidence items and the graph. The same transaction delivered as PDF or as XLSX ends up in the same schema.

What it does:

* uses the embedded table structure when the PDF has one, and falls back to clustering words by their x positions
  when it does not, which is how most bank exports without table markup are laid out;
* carries the page number into every locator, so a row points back at the page it came from;
* stitches a row that continues onto the next page, and drops the header when it repeats on each page;
* refuses to claim a table is a statement unless the headers look like one, so a letter or a notice stays a document.

What it does not do: decide that an extraction is correct. Low-confidence pages are flagged for review, and the
existing analyst mapping and correction workflow applies unchanged.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import fitz

from app.parsers.tabular import TabularResult, TabularRow

PARSER_NAME = "pdf_statement"
PARSER_VERSION = "0.1.0"

# A header set is a statement when it has something date-like, something amount-like, and either a direction pair or a
# running balance. Anything less is a table in a document, not a ledger.
_DATE_HINTS = ("date", "txn date", "transaction date", "value date", "posting date", "dt")
_AMOUNT_HINTS = ("amount", "amt", "debit", "credit", "withdrawal", "deposit", "dr", "cr", "withdrawl")
_BALANCE_HINTS = ("balance", "bal", "closing balance", "running balance")
_DIRECTION_HINTS = ("debit", "credit", "withdrawal", "deposit", "dr", "cr", "type")
_REFERENCE_HINTS = ("ref", "utr", "rrn", "cheque", "chq", "transaction id", "reference")
_NARRATION_HINTS = ("narration", "description", "particulars", "remarks", "details")

_MIN_COLUMNS = 3


@dataclass
class PdfStatementResult:
    tabular: TabularResult | None
    is_statement: bool
    confidence: str                       # high | medium | low | none
    pages_examined: int
    warnings: list[str] = field(default_factory=list)
    account_hints: dict = field(default_factory=dict)


def _norm(h: object) -> str:
    return re.sub(r"\s+", " ", str(h or "").strip().lower())


def _any_hint(header: str, hints: tuple[str, ...]) -> bool:
    return any(hint in header for hint in hints)


def looks_like_statement(headers: list[str]) -> tuple[bool, str, list[str]]:
    """Decide whether a header row belongs to a transaction ledger, and say how sure that is."""
    norm = [_norm(h) for h in headers if _norm(h)]
    if len(norm) < _MIN_COLUMNS:
        return False, "none", ["fewer than three named columns"]
    has_date = any(_any_hint(h, _DATE_HINTS) for h in norm)
    has_amount = any(_any_hint(h, _AMOUNT_HINTS) for h in norm)
    has_balance = any(_any_hint(h, _BALANCE_HINTS) for h in norm)
    has_direction = any(_any_hint(h, _DIRECTION_HINTS) for h in norm)
    has_reference = any(_any_hint(h, _REFERENCE_HINTS) for h in norm)
    has_narration = any(_any_hint(h, _NARRATION_HINTS) for h in norm)

    reasons = []
    if not has_date:
        reasons.append("no date-like column")
    if not has_amount:
        reasons.append("no amount-like column")
    if not (has_balance or has_direction):
        reasons.append("neither a running balance nor a debit/credit distinction")
    if reasons:
        return False, "none", reasons

    strength = sum([has_balance, has_direction, has_reference, has_narration])
    confidence = "high" if strength >= 3 else "medium" if strength == 2 else "low"
    return True, confidence, []


def _clean(cell: object) -> str:
    """Cell text with internal line breaks collapsed: a wrapped cell is still one value."""
    return re.sub(r"\s+", " ", str(cell or "")).strip()


def _rows_from_table(table) -> list[list[str]]:
    try:
        return [[_clean(c) for c in row] for row in table.extract()]
    except Exception:
        return []


_MONEY = re.compile(r"^[₹$]?\s*-?\d{1,3}(?:,\d{2,3})*(?:\.\d{2})\s*(?:cr|dr)?$|^[₹$]?\s*-?\d+\.\d{2}\s*(?:cr|dr)?$", re.I)
_BROKEN = re.compile(r"(^\.$)|(\s\.$)|(\.\s*$)|(^\s*\.)")


def _quality(rows: list[list[str]]) -> float:
    """How well an extraction holds together: the share of rows carrying at least one intact money value.

    Table detection on a statement without ruling lines can split an amount across a column boundary, turning
    "18,000.00" into two fragments. Scoring both candidate extractions and keeping the better one avoids trusting a
    structure that happens to exist over text positions that are actually right.
    """
    data = [r for r in rows[1:] if any(c.strip() for c in r)]
    if not data:
        return 0.0
    good = sum(1 for r in data if any(_MONEY.match(c.strip()) for c in r if c.strip()))
    broken = sum(1 for r in data for c in r if c.strip() and _BROKEN.search(c.strip()))
    # An amount split across a column boundary leaves a fragment such as "18000" and ". 00"; penalise those so a
    # structure that happens to exist cannot beat text positions that are actually right.
    return (good - broken) / len(data)


def _rows_from_words(page) -> list[list[str]]:
    """Reconstruct rows when the PDF has no table markup.

    Words are grouped into lines by their vertical position, then into columns by clustering the x position of the
    first word of each cell across the page. Bank exports are laid out on a fixed grid, so this recovers them without
    guessing at content.
    """
    words = page.get_text("words")  # x0, y0, x1, y1, word, block, line, word_no
    if not words:
        return []
    lines: dict[int, list[tuple[float, str]]] = {}
    for x0, y0, _x1, _y1, word, *_rest in words:
        key = round(y0 / 3.0)            # tolerate sub-point jitter within a line
        lines.setdefault(key, []).append((x0, word))
    ordered = [sorted(ws, key=lambda w: w[0]) for _, ws in sorted(lines.items())]

    # Column boundaries: the x positions where words repeatedly start, across the whole page.
    starts: dict[int, int] = {}
    for ws in ordered:
        last_x = None
        for x, _w in ws:
            if last_x is None or x - last_x > 12:   # a gap wide enough to be a new cell
                starts[int(x // 6)] = starts.get(int(x // 6), 0) + 1
            last_x = x
    common = sorted(k * 6 for k, n in starts.items() if n >= max(3, len(ordered) // 4))
    if len(common) < _MIN_COLUMNS:
        return []

    rows: list[list[str]] = []
    for ws in ordered:
        cells = [""] * len(common)
        for x, w in ws:
            idx = 0
            for i, edge in enumerate(common):
                if x >= edge - 6:
                    idx = i
            cells[idx] = (cells[idx] + " " + w).strip()
        if any(c for c in cells):
            rows.append(cells)
    return rows


_DATEISH = re.compile(r"^\s*\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4}")


def _is_transaction_row(cells: list[str], date_col: int | None) -> bool:
    """A statement page repeats the bank's letterhead and the account summary. Those are not transactions.

    A row counts as one only if it carries a date where the date column is, or an amount somewhere. This keeps
    continuation pages from contributing headings as if they were movements of money.
    """
    if date_col is not None and date_col < len(cells) and _DATEISH.match(cells[date_col] or ""):
        return True
    return any(_MONEY.match(c.strip()) for c in cells if c.strip())


def _dedupe_header(rows: list[list[str]], header: list[str]) -> list[list[str]]:
    """Drop the header when a bank repeats it at the top of every page."""
    norm_header = [_norm(h) for h in header]
    return [r for r in rows if [_norm(c) for c in r] != norm_header]


def _looks_like_continuation(cells: list[str], date_col: int | None) -> bool:
    """A row with no date and only narration text is the tail of the row above, wrapped onto the next line."""
    if date_col is None or date_col >= len(cells):
        return False
    if cells[date_col].strip():
        return False
    filled = [c for c in cells if c.strip()]
    return len(filled) == 1


def extract(data: bytes, max_pages: int = 50) -> PdfStatementResult:
    """Extract a transaction table from a PDF statement, or report that this PDF is not one."""
    warnings: list[str] = []
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        return PdfStatementResult(None, False, "none", 0, [f"pdf_open_failed:{type(exc).__name__}"])

    header: list[str] | None = None
    header_page = 0
    body: list[tuple[int, list[str]]] = []    # (page number, cells)
    pages = min(doc.page_count, max_pages)
    if doc.page_count > max_pages:
        warnings.append(f"only_first_{max_pages}_pages_examined_of_{doc.page_count}")
    used_fallback = False

    for pno in range(pages):
        page = doc[pno]
        # Two candidate extractions, scored against each other: the embedded table structure, and the words'
        # own positions. Whichever keeps amounts intact wins.
        table_rows: list[list[str]] = []
        try:
            found = page.find_tables()
            for t in list(getattr(found, "tables", []) or []):
                rows = _rows_from_table(t)
                if len(rows) >= 2:
                    table_rows = rows
                    break
        except Exception:
            table_rows = []
        word_rows = _rows_from_words(page)

        if _quality(word_rows) > _quality(table_rows):
            page_rows, from_words = word_rows, True
        else:
            page_rows, from_words = table_rows, False
        if not page_rows:
            continue
        used_fallback = used_fallback or from_words

        if header is None:
            ok, _conf, _why = looks_like_statement(page_rows[0])
            if ok:
                header = [_clean(c) for c in page_rows[0]]
                header_page = pno + 1
                body.extend((pno + 1, r) for r in page_rows[1:])
                continue
            # a page whose first row is not a header may still hold the ledger further down
            for i, row in enumerate(page_rows[:10]):
                ok, _conf, _why = looks_like_statement(row)
                if ok:
                    header = [_clean(c) for c in row]
                    header_page = pno + 1
                    body.extend((pno + 1, r) for r in page_rows[i + 1:])
                    break
        else:
            body.extend((pno + 1, r) for r in _dedupe_header(page_rows, header))

    doc.close()

    if header is None:
        return PdfStatementResult(None, False, "none", pages,
                                  warnings + ["no_transaction_table_found: this PDF is treated as a document"])

    ok, confidence, _why = looks_like_statement(header)
    width = len(header)
    date_col = next((i for i, h in enumerate(header) if _any_hint(_norm(h), _DATE_HINTS)), None)

    rows: list[TabularRow] = []
    index = 0
    skipped = 0
    for pno, cells in body:
        cells = [_clean(c) for c in cells][:width]
        cells += [""] * (width - len(cells))
        if not any(cells):
            continue
        if not _is_transaction_row(cells, date_col):
            if _looks_like_continuation(cells, date_col) and rows:
                pass          # a wrapped tail is handled below
            else:
                skipped += 1
                continue
        if _looks_like_continuation(cells, date_col) and rows:
            # stitch the wrapped tail onto the previous row's longest text cell rather than inventing a transaction
            tail = next((c for c in cells if c.strip()), "")
            prev = rows[-1]
            longest = max(prev.values, key=lambda k: len(str(prev.values.get(k) or "")))
            prev.values[longest] = f"{prev.values.get(longest, '')} {tail}".strip()
            continue
        index += 1
        rows.append(TabularRow(row_index=index, sheet=f"page {pno}",
                               values={h: cells[i] for i, h in enumerate(header)},
                               raw_line=" | ".join(cells)))

    if skipped:
        warnings.append(f"skipped_{skipped}_non_transaction_lines (headings, account summaries, page furniture)")
    if used_fallback:
        warnings.append("rows_reconstructed_from_text_positions_rather_than_table_markup")
        confidence = "medium" if confidence == "high" else confidence
    if not rows:
        return PdfStatementResult(None, False, "none", pages, warnings + ["header_found_but_no_data_rows"])

    result = TabularResult(headers=header, rows=rows, sheet=f"page {header_page}",
                           warnings=warnings, header_row_index=1)
    return PdfStatementResult(result, True, confidence, pages, warnings,
                              account_hints={"header_page": header_page, "rows": len(rows)})
