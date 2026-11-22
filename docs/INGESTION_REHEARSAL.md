# Ingestion rehearsal — reading statements this repository did not write

**Run on 22 November 2026, against `main`.**

R4C supplies its own sample statements on the day of the final. Until then every statement this product has ever
parsed was produced by its own synthetic factory, in the shape its own parser expects. A suite built on that
proves the parser agrees with itself, which is not the same as proving it can read a bank's export.

This rehearsal put ten unfamiliar layouts through the real upload pipeline — the same route an investigator
uses — and measured what happened. The layouts are in `apps/api/tests/statement_shapes.py` and the measurements
are `apps/api/tests/test_statement_rehearsal.py`, so the rehearsal is repeatable rather than a one-off.

## The layouts

| Shape | What makes it awkward |
|---|---|
| HDFC-like CSV | Three preamble lines, `Chq./Ref.No.` and `Withdrawal Amt.` as column names, `01/05/26` two-digit-year dates, Indian digit grouping, and a `*** End of Statement ***` trailer |
| SBI-like | **Tab**-separated, a preamble, `Txn Date` beside a separate `Value Date`, `Ref No./Cheque No.` |
| Single signed amount | One `Amount` column carrying the direction as a suffix: `1,80,000.00 Dr` |
| Rupee symbol, ISO dates | `₹ 1,80,000.00` in the cell, `2026-05-01T09:12:00` timestamps, a separate `Type` column of DR/CR |
| Ambiguous dates | `05/01/2026`, `06/02/2026` and `13/02/2026` in one file, and rows with no reference at all |
| Preamble trap | `Branch Name,Branch Code,IFSC` above the real header — three text cells that look like a header |
| Unmappable columns | `Col1`…`Col5`. Nothing a parser should guess at |
| Titled worksheet | Title rows above the header on the first sheet |
| Statement behind a cover sheet | The workbook opens on a cover page; the statement is on sheet two |
| Two accounts, two sheets | One workbook, one account per worksheet |

## What the first run found

Eleven of eighteen checks failed. Five were defects in the product, and they are fixed:

| # | Defect | Why it mattered | Fix |
|---|---|---|---|
| 1 | **A tab-separated statement parsed as one column per line** | `csv.Sniffer` reads the first lines, and in a bank export those are the preamble. It chose a delimiter for the wrong part of the file, and every value in an SBI-style export was lost — the file still "ingested", with a mapping of one field. | `_sniff_delimiter` scores candidate delimiters across the body of the file by how consistently they split it, rather than sniffing the preamble |
| 2 | **A branch line above the header was read as the header** | `_find_header_row` took the first row with three text cells. `Branch Name,Branch Code,IFSC` qualifies, so the real header became a data row and the whole statement was mis-parsed. | `_header_score` ranks each candidate row against the column names a statement actually uses, so the row naming dates and amounts wins. The old shape test remains as a fallback |
| 3 | **`*** End of Statement ***` became a transaction** | Trailer lines sit below the table, so they arrive as rows. Each became a transaction with no date, no amount and no reference — rows of nothing entering the evidence and every count derived from it. | A row with no parseable date, no amount and no reference creates no transaction. The file keeps the line; the count of withheld rows is reported as `non_transaction_rows`, so the omission is visible |
| 4 | **A statement behind a cover sheet was silently discarded** | `parse_xlsx_bytes` read the first worksheet and warned `multiple_sheets`. A workbook that opens on a cover page lost its entire statement. A warning is not a substitute for the evidence. | `parse_xlsx_all_sheets` parses every worksheet, `looks_like_statement` identifies the ones carrying a ledger, and ingestion processes each |
| 5 | **One workbook holding two accounts yielded one** | The same defect, with a worse consequence: an entire account's statement absent from the trail, and nothing in the case saying so. | As above. Both accounts now arrive, and each row keeps its sheet in the locator |

## What the first run found that was **not** a defect

Four failures were my expectations being wrong about correct behaviour. They are recorded because the reasoning
matters more than the result:

- **`01/05/26` normalised to `2026-04-30T18:30:00Z`.** That is midnight on 1 May in Asia/Kolkata, expressed in
  UTC. Asserting a `2026-05` prefix on the UTC value would have been asserting that the product ignores the
  timezone. The test now checks the window.
- **A two-digit-year date is reported as `ambiguous`** with `ambiguous_date_dd_mm_vs_mm_dd`, while a four-digit
  `dd/mm` where both parts could be a month is read day-first and says so with `day_first_assumed`. Two cases,
  two names, both visible. The test asserts the names rather than one word.
- **Unquoted commas inside `₹ 1,80,000.00` split the field.** The file was malformed CSV; the parser reported it
  as a column-count mismatch, which is right. The fixture now quotes the amounts, as a real export does.
- **A file with unreadable column names still keeps its rows.** It normalises nothing — no amount, no date — and
  warns `mapping_incomplete_transactions_not_normalised`. Keeping the rows preserves what was supplied;
  normalising them would invent data. The test now asserts that nothing was normalised rather than that nothing
  was kept.

## Where the answer is a person, not a cleverer guess

`Col1…Col5` is not a parsing problem. The parser maps nothing, normalises nothing and says so, and the analyst
names the columns through `POST /api/cases/{case_id}/files/{file_id}/remap`. The rehearsal exercises that path
end to end and pins two properties: the remap produces the transactions, and the original file keeps its bytes
and its SHA-256 while the re-parse is recorded as a **new** parse run rather than overwriting the first.

This is the fallback for the final. If R4C's layout defeats automatic mapping, remapping by hand is a feature to
demonstrate rather than a failure to apologise for.

## Result

Eighteen checks, all passing. The five defects above were real, and all five would have cost evidence on the day:
two silently, by discarding a statement.

## What this rehearsal does not establish

It does not establish that R4C's sample data will parse. These are layouts modelled on how Indian bank exports
are commonly shaped, written by the same person who wrote the parser, and that is a weaker test than an export
nobody here has seen. The 24-hour plan allows the first three hours for exactly this, and the remapping path
exists because some layout will eventually need it.

Scanned statements remain outside this rehearsal: they need OCR, which is implemented and tested locally but
disabled on the free deployment after it exceeded the memory limit.

## Live verification (22 November 2026)

The five layouts that exposed a defect were uploaded to the deployed API, through the same route an
investigator uses, after the fixes were released:

| Layout | What it exercises | Transactions expected | Produced | Statement holders |
|---|---|---:|---:|---:|
| `sbi_style.csv` | Tab-separated with a preamble | 3 | 3 | 1 |
| `hdfc_style.csv` | Preamble, dotted column names, trailer lines | 3 | 3 | 1 |
| `preamble_trap.csv` | A branch line sitting above the real header | 2 | 2 | 1 |
| `statement_on_second_sheet.xlsx` | A statement behind a cover sheet | 3 | 3 | 1 |
| `two_accounts_two_sheets.xlsx` | One account per worksheet | 5 | 5 | **2** |

The last row is the one worth reading twice. Before this rehearsal the file produced three transactions and one
account; it now produces five across two distinct holders, which is what the workbook actually contains.
