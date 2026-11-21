"""CSV / XLSX statement parsing with exact source locators (sheet/row/column)."""
from __future__ import annotations

import csv
import io
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


def _find_header_row(rows: list[list[object]]) -> int:
    """Statements often have title lines before the header. Choose the first row with >=3 non-empty text cells."""
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


def parse_csv_bytes(data: bytes) -> TabularResult:
    warnings: list[str] = []
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
        warnings.append("decoded_as_latin1")
    lines = text.splitlines()
    try:
        dialect = csv.Sniffer().sniff("\n".join(lines[:20]), delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = list(csv.reader(lines, dialect))
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


def column_letter(idx: int) -> str:
    s = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s
