# Demo script (5–7 minutes)

Banners on every screen: **SYNTHETIC DATA** · **NO LIVE POLICE/BANK CONNECTION** · *Investigative aid; human verification required*.

1. **Sign in** as the demo analyst. Point out that no credentials are built in; the operator sets them by environment variable.
2. **Cases → Synthetic Case Factory.** Choose *multi victim network*, *adversarial*, *small*, seed **42**. Generate.
   - Show the bundle table: statements in three different column layouts (CSV and XLSX), a complaint PDF, a technical-observations JSON, a noisy screenshot. Each has a SHA-256 and parser warnings (duplicates, ambiguous dates, balance mismatch, OCR unavailable → manual review).
3. **Open case → Upload Evidence.** Show the parse runs and, for a statement, the column-mapping editor. Say: *these files went through exactly the same endpoint a user's upload goes through; the answer key is sealed elsewhere.*
4. **Transactions.** Show raw date strings next to UTC values with the *ambiguous* badge; duplicate rows highlighted but kept; balance reconciliation mismatch; the reconstructed multi-hop path victim → first-layer → second-layer account; the rules triage signals with their reasons (and the ML triage cue if the model is loaded).
5. **Investigation Graph.** Start with the default small view. Legend: solid = observed, dashed = candidate/stale, thick = corroborated.
   - Click a **TRANSFERRED_TO** edge: statement row locator (sheet/row/cell), raw row, parser version, event time precision.
   - Click a **SAME_ACCOUNT_IDENTIFIER** edge: the VPA in the victim's statement and the account number in the mule's statement are bridged by matching reference + amount — derived, not merged.
   - **The key moment:** two unrelated `.test` domains share a CDN IP with the campaign domain. Click the **SHARED_INFRASTRUCTURE** edge: level *candidate*, limitation *shared IP is not proof of common control*, counter-evidence *multi-tenant infrastructure*. The system refuses to call them commonly operated.
   - Click the **stale** RESOLVES_TO edge: observation outside the transaction window → counter-evidence; current DNS is never shown as historical.
   - Try **Supported** on the candidate edge as an analyst → refused (supervisor required). Record *Needs more evidence* with a reason → audit log.
6. **Timeline.** Filter to dns + transaction; show uncertain timestamps marked.
7. **Reports.** Download the PDF: sources with hashes, parsing warnings, transaction trail, infrastructure observations with times, relationship table with locators, counter-evidence, unresolved gaps, disclaimer.
8. **Data Sources.** All connectors *not configured* or *mock*; explain that *live* appears only after an authenticated request succeeds.
9. **Related cases.** Open *Related cases* in the case tools. Generate a second case that received the same mule statement (or upload it), correlate the two: the account and reference bridges are corroborated with file hashes and row locators; a decoy case with a similar name appears only under *Not asserted*; a shared CDN IP stays a candidate.
10. **Victim claims.** On a multi-victim case, record three claims, link their source transactions, record the simulated bank hold from the generated notice: traced inflow exceeds the documented hold, so the account is flagged oversubscribed and nothing is allocated. Advance one claim through investigator → supervisor → export-ready and download the readiness pack.
11. **Cooperation pack.** Fill the request fields, watch the validation checklist, attach the FIR PDF and endorsement, endorse as supervisor, export the ZIP and open manifest.json to show the hashes.
12. **OCR.** Upload the generated screenshot: the preview shows engine, confidence and the “needs human verification” state; the extracted VPA/URL become candidate mentions until corroborated.
13. **Reproducibility.** Generate seed 42 again → identical file hashes. Change the seed → a new case.
14. **Benchmark slide** (docs/BENCHMARK.md): full layer = 0 false links across all cases vs. 144 without safeguards; counter-evidence recall 0.87 vs 0.63.
