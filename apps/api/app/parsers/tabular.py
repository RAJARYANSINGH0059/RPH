"""CSV / XLSX statement parsing with exact source locators (sheet/row/column)."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

import openpyxl

PARSER_NAME_CSV = "csv_statement"
PARSER_NAME_XLSX = "xlsx_statement"


@dataclass
class TabularRow:
    row_index: int  # 1-based data row (header excluded), as in the sheet/file for locators
    sheet: str | None
    values: dict[str, object]  # header -> raw cell value
    raw_line: str | None = None


@dataclass
class TabularResult:
    headers: list[str]
    rows: list[TabularRow]
    sheet: str | None
    warnings: list[str] = field(default_factory=list)
    header_row_index: int = 1


def _header_score(row: list[object]) -> int:
    """How much this row reads like the header of a statement rather than a line of the preamble.

    A bank export often carries a branch or address line of three or more words above the real header, and
    "first row with three text cells" picks that line instead. Scoring against the column names a statement
    actually uses finds the right row: a preamble line names a branch, a header names dates and amounts.
    """
    from app.parsers.common import HEADER_SYNONYMS

    cells = [re.sub(r"[^a-z0-9/ ]", " ", str(c).lower()).strip() for c in row if c is not None and str(c).strip()]
    if len(cells) < 3:
        return 0
    score = 0
    for field, syns in HEADER_SYNONYMS.items():
        for cell in cells:
            if cell in syns or any(re.search(rf"(^|\s){re.escape(syn)}(\s|$)", cell) for syn in syns):
                score += 1
                break
    return score


def _find_header_row(rows: list[list[object]]) -> int:
    """Pick the row that best reads like a statement header, falling back to the old shape test.

    A statement header has to name a date and some notion of an amount; a row scoring below that is a title or
    an address line. Only when nothing scores does this fall back to "first row of three text cells", which is
    what a file with entirely unrecognisable column names deserves.
    """
    best_i, best_score = None, 0
    for i, r in enumerate(rows[:30]):
        score = _header_score(r)
        if score > best_score:
            best_i, best_score = i, score
    if best_i is not None and best_score >= 2:
        return best_i
    for i, r in enumerate(rows[:30]):
        non_empty = [c for c in r if c is not None and str(c).strip() != ""]
        texty = [c for c in non_empty if not _looks_numeric(c)]
        if len(non_empty) >= 3 and len(texty) >= 3:
            return i
    return 0


def _looks_numeric(v) -> bool:
    try:
        float(str(v).replace(",", ""))
        return True
    except ValueError:
        return False


def _sniff_delimiter(lines: list[str]) -> str:
    """Pick the delimiter that splits the body of the file most consistently.

    `csv.Sniffer` reads the first lines, and in a bank export those are the preamble: an address, a period, a
    blank. Sniffing them chooses a delimiter for the wrong part of the file, and a tab-separated statement then
    arrives as one column per line, which loses every value in it. Scoring candidates across the whole file
    instead asks the question that matters: which character actually divides these rows into the same number of
    fields, more than once?
    """
    candidates = [",", "\t", ";", "|"]
    sample = [ln for ln in lines[:200] if ln.strip()]
    best, best_score = ",", 0
    for d in candidates:
        counts = [ln.count(d) for ln in sample if ln.count(d) > 0]
        if len(counts) < 2:
            continue
        common = max(set(counts), key=counts.count)
        agreeing = counts.count(common)
        score = agreeing * common          # reward both consistency and the number of fields it yields
        if score > best_score:
            best, best_score = d, score
    return best


def parse_csv_bytes(data: bytes) -> TabularResult:
    warnings: list[str] = []
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
        warnings.append("decoded_as_latin1")
    lines = text.splitlines()
    delimiter = _sniff_delimiter(lines)
    if delimiter != ",":
        warnings.append(f"delimiter_detected:{'tab' if delimiter == chr(9) else delimiter}")
    reader = list(csv.reader(lines, delimiter=delimiter))
    if not reader:
        return TabularResult([], [], None, ["empty_file"])
    hdr_idx = _find_header_row(reader)
    if hdr_idx > 0:
        warnings.append(f"header_detected_at_line_{hdr_idx + 1}")
    headers = [str(h).strip() or f"column_{i+1}" for i, h in enumerate(reader[hdr_idx])]
    rows: list[TabularRow] = []
    for i, raw in enumerate(reader[hdr_idx + 1:], start=hdr_idx + 2):
        if not any(str(c).strip() for c in raw):
            continue
        if len(raw) != len(headers):
            warnings.append(f"row_{i}_column_count_mismatch")
        values = {headers[j]: (raw[j] if j < len(raw) else None) for j in range(len(headers))}
        rows.append(TabularRow(row_index=i, sheet=None, values=values, raw_line=lines[i - 1] if i - 1 < len(lines) else None))
    return TabularResult(headers, rows, None, warnings, header_row_index=hdr_idx + 1)


def parse_xlsx_bytes(data: bytes, sheet_name: str | None = None, max_rows: int = 50000) -> TabularResult:
    warnings: list[str] = []
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb[wb.sheetnames[0]]
    if len(wb.sheetnames) > 1:
        warnings.append(f"multiple_sheets:{','.join(wb.sheetnames)}")
    all_rows = []
    for i, r in enumerate(ws.iter_rows(values_only=True)):
        if i >= max_rows:
            warnings.append("row_limit_reached")
            break
        all_rows.append(list(r))
    if not all_rows:
        return TabularResult([], [], ws.title, ["empty_sheet"])
    hdr_idx = _find_header_row(all_rows)
    if hdr_idx > 0:
        warnings.append(f"header_detected_at_row_{hdr_idx + 1}")
    headers = [str(h).strip() if h is not None and str(h).strip() else f"column_{i+1}" for i, h in enumerate(all_rows[hdr_idx])]
    rows: list[TabularRow] = []
    for i, raw in enumerate(all_rows[hdr_idx + 1:], start=hdr_idx + 2):
        if not any(c is not None and str(c).strip() for c in raw):
            continue
        values = {headers[j]: (raw[j] if j < len(raw) else None) for j in range(len(headers))}
        rows.append(TabularRow(row_index=i, sheet=ws.title, values=values))
    return TabularResult(headers, rows, ws.title, warnings, header_row_index=hdr_idx + 1)


def parse_xlsx_all_sheets(data: bytes, max_rows: int = 50000) -> list[TabularResult]:
    """Parse every worksheet, so a statement behind a cover sheet is not silently discarded.

    Reading only the first sheet and warning `multiple_sheets` meant a workbook that opens on a cover page lost
    its entire statement, and a workbook holding one account per sheet lost all but one account. A warning is
    not a substitute for the evidence.
    """
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out: list[TabularResult] = []
    for name in wb.sheetnames:
        try:
            out.append(parse_xlsx_bytes(data, sheet_name=name, max_rows=max_rows))
        except Exception as exc:                                  # one unreadable sheet must not lose the others
            out.append(TabularResult([], [], name, [f"sheet_unreadable:{type(exc).__name__}"]))
    return out


def looks_like_statement(result: "TabularResult") -> bool:
    """Whether a parsed sheet carries a transaction ledger, judged by the columns it actually has."""
    from app.parsers.common import guess_column_mapping

    if not result.rows:
        return False
    mapping, _ = guess_column_mapping(result.headers)
    has_amount = bool({"amount", "debit", "credit"} & set(mapping))
    return "datetime" in mapping and has_amount


def column_letter(idx: int) -> str:
    s = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s
