"""Ingestion rehearsal against statement layouts this repository does not generate.

R4C supplies its own sample statements on the day of the final. A suite built only on our own synthetic factory
proves the parser agrees with itself, which is not the same as proving it can read a bank's export. These tests
put the shapes in `statement_shapes.py` through the real upload pipeline and pin what the parser must manage
without help, and what it must hand to an analyst rather than guess at.
"""
from __future__ import annotations

import pytest

from tests import statement_shapes as shapes

CSV = "text/csv"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _upload(client, analyst, name: str, data: bytes, title: str):
    case = client.post("/api/cases", json={"title": title, "summary": "Ingestion rehearsal."},
                       headers=analyst).json()["id"]
    kind = CSV if name.endswith(".csv") else XLSX
    r = client.post(f"/api/cases/{case}/upload", files={"files": (name, data, kind)}, headers=analyst)
    assert r.status_code in (200, 201), r.text[:300]
    body = r.json()[0] if isinstance(r.json(), list) else r.json()
    txs = client.get(f"/api/cases/{case}/transactions", headers=analyst).json()
    return case, body["parse_run"], txs


def _report(name, run, txs):
    """Printed on failure so a rehearsal tells you what happened, not merely that it did not pass."""
    return (f"{name}: mapping={sorted((run.get('column_mapping') or {}))} "
            f"rows={(run.get('stats') or {}).get('rows')} transactions={len(txs)} "
            f"warnings={run.get('warnings')}")


# --------------------------------------------------------------------------- the shapes that must just work

@pytest.mark.parametrize("name", ["hdfc_style.csv", "sbi_style.csv", "signed_amount_dr_cr.csv",
                                  "rupee_symbol_iso_dates.csv"])
def test_an_unfamiliar_layout_still_produces_transactions(client, analyst, name):
    """Column names differ between banks, but the shape of a statement does not. These must need no help."""
    _, run, txs = _upload(client, analyst, name, shapes.CSV_SHAPES[name](), f"rehearsal {name}")
    assert len(txs) == 3, _report(name, run, txs)
    mapping = run.get("column_mapping") or {}
    assert "datetime" in mapping, _report(name, run, txs)
    assert {"debit", "credit"} & set(mapping) or "amount" in mapping, _report(name, run, txs)
    assert all(t["amount_minor"] is not None for t in txs), _report(name, run, txs)


def test_a_preamble_is_not_mistaken_for_the_header(client, analyst):
    """Three text cells above the real header is a trap a naive detector falls into."""
    _, run, txs = _upload(client, analyst, "preamble_trap.csv", shapes.headerless_preamble_trap(),
                          "rehearsal preamble")
    mapping = run.get("column_mapping") or {}
    assert "Branch Name" not in mapping.values(), _report("preamble", run, txs)
    assert len(txs) == 2, _report("preamble", run, txs)


def test_indian_digit_grouping_and_a_currency_symbol_parse_to_exact_paise(client, analyst):
    _, run, txs = _upload(client, analyst, "hdfc_style.csv", shapes.hdfc_style(), "rehearsal grouping")
    amounts = sorted(t["amount_minor"] for t in txs)
    assert amounts == [900000, 4500000, 18000000], _report("grouping", run, txs)

    _, run2, txs2 = _upload(client, analyst, "rupee_symbol_iso_dates.csv", shapes.rupee_symbol_and_iso_dates(),
                            "rehearsal rupee symbol")
    assert sorted(t["amount_minor"] for t in txs2) == [900000, 4500000, 18000000], _report("rupee", run2, txs2)


def test_a_direction_carried_as_a_suffix_is_read_as_a_direction(client, analyst):
    """`1,80,000.00 Dr` is one column doing two jobs, and a statement that loses the direction is useless."""
    _, run, txs = _upload(client, analyst, "signed_amount_dr_cr.csv", shapes.signed_amount_with_dr_cr(),
                          "rehearsal dr cr")
    by_ref = {t["external_reference"]: t for t in txs}
    assert by_ref["SYNUTR2026000417"]["direction"] == "debit", _report("dr/cr", run, txs)
    assert by_ref["SYNREF00090003"]["direction"] == "credit", _report("dr/cr", run, txs)


def test_a_direction_column_is_read_as_a_direction(client, analyst):
    _, run, txs = _upload(client, analyst, "rupee_symbol_iso_dates.csv", shapes.rupee_symbol_and_iso_dates(),
                          "rehearsal direction column")
    by_ref = {t["external_reference"]: t for t in txs}
    assert by_ref["SYNUTR2026000417"]["direction"] == "debit", _report("direction", run, txs)
    assert by_ref["SYNREF00090004"]["direction"] == "credit", _report("direction", run, txs)


def test_four_date_conventions_all_normalise(client, analyst):
    for name, build in [("hdfc_style.csv", shapes.hdfc_style),            # 01/05/26
                        ("sbi_style.csv", shapes.sbi_style),              # 01-05-2026
                        ("signed_amount_dr_cr.csv", shapes.signed_amount_with_dr_cr),   # 01 May 2026
                        ("rupee_symbol_iso_dates.csv", shapes.rupee_symbol_and_iso_dates)]:   # ISO
        _, run, txs = _upload(client, analyst, name, build(), f"rehearsal dates {name}")
        dated = [t for t in txs if t["datetime_utc"]]
        assert len(dated) == len(txs), _report(name, run, txs)
        # A date with no time is midnight in the source's zone, and midnight in Asia/Kolkata is 18:30 the
        # previous day in UTC. Asserting a "2026-05" prefix on the UTC value would be asserting that the
        # product ignores the timezone, so the window is checked instead.
        for t in dated:
            assert "2026-04-30" <= t["datetime_utc"][:10] <= "2026-05-31", _report(name, run, txs)


def test_an_ambiguous_date_stays_ambiguous(client, analyst):
    """05/01/2026 could be either convention. The parser must say so rather than pick one silently."""
    _, run, txs = _upload(client, analyst, "ambiguous_dates.csv", shapes.ambiguous_dates_and_missing_reference(),
                          "rehearsal ambiguous")
    assert len(txs) == 3, _report("ambiguous", run, txs)
    # The parser distinguishes two cases and names both. A two-digit year is genuinely undecidable and gets
    # precision "ambiguous"; a four-digit dd/mm where both parts could be a month is read day-first, as Indian
    # statements are, and says so with `day_first_assumed`. Either way the reader is told.
    flags = {w for t in txs for w in (t["warnings"] or [])}
    precisions = {t["time_precision"] for t in txs}
    assert "ambiguous" in precisions or "day_first_assumed" in flags or \
        "ambiguous_date_dd_mm_vs_mm_dd" in flags, _report("ambiguous", run, txs)
    assert all(t["amount_minor"] is not None for t in txs), "an ambiguous date must not discard the row"


def test_a_two_digit_year_is_reported_as_undecidable(client, analyst):
    """01/05/26 cannot be resolved from the value alone, and the parser must not pretend otherwise."""
    _, run, txs = _upload(client, analyst, "hdfc_style.csv", shapes.hdfc_style(), "rehearsal two digit year")
    assert all(t["time_precision"] == "ambiguous" for t in txs), _report("two digit year", run, txs)
    assert all("ambiguous_date_dd_mm_vs_mm_dd" in (t["warnings"] or []) for t in txs), \
        _report("two digit year", run, txs)


def test_a_row_with_no_reference_is_kept(client, analyst):
    _, run, txs = _upload(client, analyst, "ambiguous_dates.csv", shapes.ambiguous_dates_and_missing_reference(),
                          "rehearsal missing reference")
    assert sum(1 for t in txs if not t["external_reference"]) == 2, _report("missing ref", run, txs)


# --------------------------------------------------------------------------- what must NOT be guessed

def test_columns_that_carry_no_meaning_are_not_guessed_at(client, analyst):
    """Col1..Col5 tells the parser nothing. Inventing a mapping here would silently mis-type every row."""
    case, run, txs = _upload(client, analyst, "unmappable_columns.csv", shapes.unmappable_columns(),
                             "rehearsal unmappable")
    mapping = run.get("column_mapping") or {}
    assert "datetime" not in mapping, _report("unmappable", run, txs)
    # The rows are kept, because the file is evidence and discarding it would lose what was supplied. What
    # matters is that nothing was normalised from columns the parser could not identify.
    assert all(t["amount_minor"] is None for t in txs), _report("unmappable", run, txs)
    assert all(t["datetime_utc"] is None for t in txs), _report("unmappable", run, txs)
    warnings = " ".join(run.get("warnings") or [])
    assert "mapping_incomplete" in warnings or "unmapped_columns" in warnings, _report("unmappable", run, txs)


def test_the_analyst_can_remap_those_columns_by_hand(client, analyst):
    """The answer to an unreadable header is a person naming the columns, not a cleverer guess."""
    case = client.post("/api/cases", json={"title": "rehearsal remap", "summary": "Analyst remapping."},
                       headers=analyst).json()["id"]
    up = client.post(f"/api/cases/{case}/upload",
                     files={"files": ("unmappable_columns.csv", shapes.unmappable_columns(), CSV)},
                     headers=analyst)
    assert up.status_code in (200, 201)
    body = up.json()[0] if isinstance(up.json(), list) else up.json()
    file_id = body["file"]["id"]

    r = client.post(f"/api/cases/{case}/files/{file_id}/remap",
                    json={"mapping": {"datetime": "Col1", "narration": "Col2", "reference": "Col3",
                                      "amount": "Col4", "balance": "Col5"}},
                    headers=analyst)
    assert r.status_code in (200, 201), r.text[:300]
    txs = client.get(f"/api/cases/{case}/transactions", headers=analyst).json()
    assert len(txs) == 2, f"remap produced {len(txs)} transactions: {r.text[:200]}"
    assert sorted(t["amount_minor"] for t in txs) == [4500000, 18000000]
    assert {t["external_reference"] for t in txs} == {"SYNUTR2026000417", "SYNREF00090007"}


def test_remapping_keeps_the_original_file_and_records_a_new_parse_run(client, analyst):
    case = client.post("/api/cases", json={"title": "rehearsal remap provenance", "summary": "Re-parse."},
                       headers=analyst).json()["id"]
    up = client.post(f"/api/cases/{case}/upload",
                     files={"files": ("unmappable_columns.csv", shapes.unmappable_columns(), CSV)},
                     headers=analyst)
    body = up.json()[0] if isinstance(up.json(), list) else up.json()
    file_id, sha_before = body["file"]["id"], body["file"]["sha256"]
    client.post(f"/api/cases/{case}/files/{file_id}/remap",
                json={"mapping": {"datetime": "Col1", "amount": "Col4", "reference": "Col3"}}, headers=analyst)
    files = client.get(f"/api/cases/{case}/files", headers=analyst).json()
    assert files[0]["sha256"] == sha_before, "a re-parse must never alter the original file"
    runs = client.get(f"/api/cases/{case}/parse-runs", headers=analyst)
    if runs.status_code == 200:
        assert len(runs.json()) >= 2, "a re-parse must create a new parse run, not overwrite the first"


# --------------------------------------------------------------------------- workbooks

def test_a_titled_worksheet_is_read_past_its_title_rows(client, analyst):
    _, run, txs = _upload(client, analyst, "titled_first_sheet.xlsx", shapes.xlsx_titled_first_sheet(),
                          "rehearsal titled sheet")
    assert len(txs) == 3, _report("titled", run, txs)
    assert sorted(t["amount_minor"] for t in txs) == [900000, 4500000, 18000000], _report("titled", run, txs)


def test_a_statement_behind_a_cover_sheet_is_not_lost(client, analyst):
    """A workbook that opens on a cover page is ordinary. Reading only the first sheet would silently discard
    the entire statement, which is the worst failure an ingestion pipeline can have."""
    _, run, txs = _upload(client, analyst, "statement_on_second_sheet.xlsx",
                          shapes.xlsx_statement_on_second_sheet(), "rehearsal second sheet")
    assert len(txs) == 3, _report("second sheet", run, txs)


def test_two_accounts_in_one_workbook_both_arrive(client, analyst):
    _, run, txs = _upload(client, analyst, "two_accounts_two_sheets.xlsx", shapes.xlsx_two_accounts_two_sheets(),
                          "rehearsal two sheets")
    assert len(txs) == 5, _report("two sheets", run, txs)
    # Neither sheet carries an account column, so the holder is inferred from the file. If the sheet were not
    # part of that identity, both accounts would collapse into one and the transfer between them would vanish.
    holders = {t["account_ref"] for t in txs}
    assert len(holders) == 2, f"two worksheets produced {len(holders)} statement holder(s): {holders}"
