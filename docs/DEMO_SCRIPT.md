# Demo script

## A. Operation Desert Mirage (12 steps, ~10 minutes) — current recommended demo

All data is synthetic; banners say so on every screen. Nothing in this sequence contacts a bank, portal or provider, and nothing is frozen or notified.

1. **Landing → SIGN IN** (one click). An isolated `demo_analyst` workspace is created with a 4-hour expiry; the badge says *SYNTHETIC DEMO*. Open the **Overview** and the 15-step **Guided walkthrough** card.
2. **Synthetic Case Factory** → *Operation Desert Mirage*, seed 1001, generate. Three complaints (Jaipur, Jodhpur, Udaipur), a QR PNG and a `upi://` link, statements in different layouts (one without a balance column, one with a missing period), an OCR-corrupted screenshot, a job advert, a rotated domain with current-only DNS, a simulated hold notice.
3. **Case workspace**: evidence health, coverage summary (PARTIAL_COVERAGE for the gapped statement, NOT_SUPPLIED for the second-layer account), “what to ask for next”.
4. **Fraud Operation Twin**: layers on one time axis; hover REPORTED_BEFORE / INSTRUCTS_PAYMENT_TO links; switch to **Victim Journey** for one complaint and show the consistency checks; **Investigation Replay** compares the case before and after the second statement arrived.
5. **Payment Instruction Bridge**: the QR decodes to a VPA + amount; the match is EXACT_IDENTIFIER_AMOUNT to a statement row with its locator; the OCR-corrupted VPA stays CANDIDATE_PARTIAL_MATCH; the message-export link with no currency warns `currency_missing_not_assumed`.
6. **Multi-Hop Fund Path → Proof certificate**: download `proof.json`; in a terminal run `python scripts/verify_proof.py proof.json --files <downloaded originals>` → PASS; edit one cell in a CSV → FAIL with the hop and file named.
7. **Bounded Fund Provenance**: min/max victim-origin per hop; the commingled salary credit widens the band; beyond the account without a statement the status is UNDETERMINED with the statement named; toggle the FIFO scenario and note it is labelled an assumption.
8. **Operation Lifecycle & Dependencies** (FATF attribution shown): S2 recruitment is CANDIDATE from the job advert; S5 collection corroborated; the shared CDN provider is a dependency object, not a criminal; leverage label only on the two-victim collection account, with its reason.
9. **Account Involvement vs Human Attribution**: P1 supported from records, P3–P8 unassessed; try to mark P6 supported without evidence → refused; add an alleged role claim and show the **control timeline** with holder ≠ controller and UNKNOWN initiator lanes.
10. **CounterProof / Evidence Adversary**: the SHARED_INFRASTRUCTURE edge is CANDIDATE with alternatives; record a dissent on a hypothesis as the independent reviewer; **Counterfactual Lab** runs *missing statement* (result changes) and *stale DNS* (result stable).
11. **IVOI & Evidence Acquisition**: the next-best record is the second-layer statement; draft the request (custodian, scope, identifiers, legal fields flagged *requires validation*); advance identified → draft → under review; the draft PDF says *DRAFT — not transmitted*; the **Preservation desk** shows deadlines only where retention is verified.
12. **Chokepoints → Network Adaptation → Intervention Impact** (acknowledge the hypothetical notice; see unrelated activity on the account), then **Blind Challenge**: submit a hypothesis, the submission locks, and only then does the reveal score it. Close on `docs/BENCHMARK_V2.md`: perfect synthetic scores show internal consistency, not field accuracy.

## B. Original 5–7 minute script (still valid)

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
