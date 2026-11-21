# Feature matrix (2026-11-22, branch `feat/ps05-digital-twin`)

Status vocabulary: **Implemented and verified** (API + UI + permissions + persistence + tests executed) · **Implemented, verification incomplete** · **Partially implemented** · **Blocked** · **Not implemented**. Every "verified" row names its test file.

| Feature | Status | Evidence |
|---|---|---|
| Money-trail graph, transactions, timeline, reports, cross-case, claims, cooperation, OCR chain, S3 adapter, connectors, ML triage | Implemented and verified (pre-existing, preserved) | 58 original tests still pass (103 total) |
| Payment-instruction bridge (QR decode, upi:// parse, field-level matching, graph edge, PDF) | Implemented and verified | `test_payment_bridge.py` (7) |
| Fraud-operation digital twin (events, layers, links, as-of replay, manual reported events) | Implemented and verified | `test_twin_coverage_proof.py` |
| Victim journey reconstruction with consistency checks | Implemented and verified | same |
| Investigation replay (as-of, compare two moments, audit timeline) | Implemented and verified | same |
| Evidence coverage / blind-spot states (OBSERVED_ZERO vs NOT_SUPPLIED, CURRENT_ONLY, gaps) | Implemented and verified | same |
| Proof-carrying money trail + standalone offline verifier (tamper detection) | Implemented and verified | same; benchmark v2 |
| Temporal evidence fusion (intervals, tolerance, current-only exclusion, window filter) | Implemented and verified | same |
| FATF-attributed operation lifecycle and dependency map | Implemented and verified | `test_lifecycle_roles_requests.py` |
| Role-sensitive review (9 propositions, guardrails, reviewer decision) | Implemented and verified | same |
| Account-control timeline (role claims, holder ≠ controller) | Implemented and verified | same |
| Missing-evidence dependency map + Evidence Acquisition (catalogue, custodians, lifecycle, manual dispatch record, draft PDF) | Implemented and verified | same |
| IVOI next-best-evidence ranking with component breakdown | Implemented and verified | same |
| Preservation desk (clock, volatility, verified-retention-only deadlines) | Implemented and verified | same |
| Investigation completeness checklist | Implemented and verified | same |
| Bounded fund provenance (LP, gaps as unknown movements, FIFO/LIFO scenarios) | Implemented and verified | `test_bounded_adversary_lab.py` |
| Evidence Adversary / CounterProof (challenge reports, states, actions, dissent) | Implemented and verified | same |
| Alternative hypotheses (versioned) + independent review (blind mode, dissent) | Implemented and verified | same |
| Counterfactual lab (14 perturbation profiles on an immutable copy) | Implemented and verified | same |
| Hypothesis branches with invariant comparison | Implemented and verified | same |
| Chokepoint map + network adaptation simulator (removal, substitution, saved scenarios) | Implemented and verified | same |
| Intervention impact (ledger, unrelated activity, four hypothetical scenarios, acknowledgement gate) | Implemented and verified | same |
| Evidence integrity and statement forensics (row-level breaks, duplicates, provenance class, PDF metadata leads, provisional edges) | Implemented and verified | same |
| Campaign DNA fingerprints, cross-case comparison, identifier rotation | Implemented and verified | same; benchmark v2 |
| Privacy-preserving keyed-token matching with audited reveal | Implemented and verified (disabled without a server key by design) | same |
| Prevention-rule compiler (held-out synthetic evaluation, approval gate) | Implemented and verified | same |
| One-click demo session (isolated demo principal, expiry, rate limit, origin check, BFF HttpOnly cookie, scoped short tokens) | Implemented and verified | `test_demo_isolation.py`; browser walk-through |
| Blind investigation challenge (submit → lock → reveal, scored) | Implemented and verified | same |
| Synthetic scenarios: Desert Mirage, identifier rotation, commingled funds, benign look-alike, compromised account; difficulties incomplete_evidence / identifier_rotation / temporal_conflict | Implemented and verified | `test_synthetic_and_sealed.py`, determinism check |
| Single left navigation registry (74 feature routes + 3 utility, duplicate check in CI) | Implemented and verified | `scripts/check-nav.mjs` |
| Graph workbench (shapes/line patterns, layers, clusters, time window, path replay, linked table/timeline, saved views, inspector links) | Implemented, verification incomplete | typecheck/build pass; desktop visual check; no automated interaction test |
| Motion scenes (9 scenes, reduced-motion static, off-screen pause) | Implemented, verification incomplete | visual check only |
| Benchmark v2 (next-wave metrics, CIs, graph-only baseline vs PS05-X on identical cases, sample size) | Implemented and verified | `tests/benchmark/run_benchmark_v2.py`, results JSON, `test_nextwave_gaps.py` |
| Evidence-request responses (attach returned record, partial response keeps the unresolved remainder, append-only history) | Implemented and verified | `test_nextwave_gaps.py` |
| Reversal / refund handling in bounded attribution (composition restored, gross vs net, never netted silently) | Implemented and verified | `test_nextwave_gaps.py` |
| Proof-carrying investigation package (ZIP: report, proof per path, analyses, hypotheses with dissent, requests with responses, role reviews, audit, SHA-256 manifest; sealed truth refused) | Implemented and verified | `test_nextwave_gaps.py` |
| Graph-only baseline comparison inside the blind-challenge reveal | Implemented and verified | `test_nextwave_gaps.py` |
| Adversary alternatives and challenge state on cross-case shared-infrastructure links | Implemented and verified | `test_nextwave_gaps.py` |
| Hindi OCR on the live free-tier API | Blocked | 512 MiB instance OOM; available in Docker image and locally |
| Historical passive DNS provider | Blocked (no credentials) | current-only labelled honestly |
| Durable S3 storage on the live API | Blocked (no bucket credentials) | adapter tested locally |
| Geospatial map view | Not implemented | no source-grounded geospatial events exist in the data model; IP geolocation deliberately excluded |
| Field-level extraction disagreement between two parsers of the same statement | Partially implemented | debit/credit conflicts and text-layer vs OCR disagreement handled; no second tabular parser exists |
| Reversal handling across accounts (a reversal recorded in the counterparty's statement) | Partially implemented | the receiving account's own reversal debit is handled by its LP; cross-statement pairing of the same reversal is not deduplicated |
| Standards-based STIX/TAXII export | Not implemented | roadmap |
