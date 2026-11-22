# TraceWeave specification: status and traceability

Branch `feat/ps05-digital-twin`, merged into `main`. Status values are used as the specification defines them:
`COMPLETE` (implemented, tested and verified in the target environment) · `PARTIAL` · `UNVERIFIED` · `BLOCKED_EXTERNAL` ·
`NOT_IMPLEMENTED`. A route that loads or a unit test that passes is not promoted to `COMPLETE`.

This document covers only what has actually been worked on against this specification. Everything not listed here is
untouched by this pass and keeps the status recorded in `docs/FEATURE_MATRIX.md`.

## Defects named in the specification

| Defect | Status | Code | Tests | Evidence |
|---|---|---|---|---|
| **A. Scoped tokens are not enforced** | COMPLETE | `apps/api/app/core/scopes.py`, `app/core/deps.py` | `tests/test_token_scopes.py` (11) | Default-deny by route path template; upload and download tokens reach only their listed routes; unknown scopes, expiry, malformed and wrongly signed tokens refused; scope cannot widen case access. One pre-existing test asserted the insecure behaviour and was corrected. |
| **B. Inconsistent result counts** | COMPLETE | `apps/api/app/services/counts.py`, `routers/cases.py`, `reports/builder.py`, `apps/web/app/cases/[id]/results/page.tsx` | `tests/test_count_consistency.py` (5) | One service, each count carrying its definition. Overview, `/counts`, graph, paths, report and the results page agree; same seed yields identical counts. Root causes: the results page read a field name the report never emitted (always 0 paths), and the report table drops `DOCUMENTS` edges (85 vs 80). |
| **C. Cold-start and loading reliability** | PARTIAL | `apps/web/lib/apiState.ts`, `components/Shell.tsx`, `components/ui.tsx` | none automated | Seven explicit states (checking, waking, ready, degraded, authentication required, timed out, unavailable), elapsed seconds, bounded exponential backoff with jitter, one probe in flight, retry that preserves the page. **Missing for COMPLETE:** browser tests for 401/403/404/409/413/422/429/500 responses, and per-subsystem health probes beyond database and migrations. |
| **D. OCR not production-enabled** | BLOCKED_EXTERNAL | unchanged | existing OCR tests | The engine chain and its unavailable state are implemented and tested locally. OCR stays off on the live instance because the runtime exceeds the 512 MiB free plan (observed OOM kill). Enabling it needs a paid instance or a separate worker. Labelled honestly in the UI and `docs/LIMITATIONS.md`. |
| **E. Evidence storage is ephemeral** | BLOCKED_EXTERNAL | unchanged | storage adapter tests | The S3-compatible adapter exists and is unit-tested; the live service still uses the ephemeral disk because no bucket credentials are available. Not claimed as production-ready. |
| **F. Dependency and tooling issues** | PARTIAL | `apps/web` lint fixes | lint clean | The three unused-variable warnings are gone and `next lint` reports no warnings or errors. **Not done:** the npm audit findings (one high in the PostCSS chain, one moderate, two low), the Python dependency audit, the `next lint` deprecation, the multipart deprecation warning, and dependency scanning in CI. |
| **G. Current versus historical evidence boundaries** | COMPLETE (pre-existing) | `services/twin.py`, connectors | existing tests | Current-only observations are labelled, collection time is stored separately from validity, and current DNS/RDAP never enters a historical relationship. Connectors remain `not_configured`. |

## Authorisation matrix (token scope)

| Scope | May reach | Everything else |
|---|---|---|
| `full` | every route, subject to role and case membership | — |
| `upload` | `POST /api/cases/{case_id}/upload`, `POST /api/cases/{case_id}/payment-instructions/decode-image` | 403 |
| `download` | the twelve export routes listed in `app/core/scopes.py` | 403 |
| anything else | nothing | 403 |

Scope is a restriction, never a grant: role checks and `get_case_or_404` run unchanged for every token.

## Canonical counts

`GET /api/cases/{case_id}/counts` returns files, transactions (total, with amount, duplicates, excluding duplicates),
entities by type, relationships (total, in graph, in report tables, awaiting review, by evidence level, by review
status), indicators, parser warnings and paths (total, resolved, unresolved), each with a definition. Candidate and
stale relationships are counted and labelled, never dropped.

## Tests executed

| Command | Result |
|---|---|
| `cd apps/api; python -m pytest -q` | **119 passed** (103 before this pass) |
| `cd apps/api; ruff check app tests --select E,F,W --ignore E501,E731,E741` | clean |
| `cd apps/web; npx tsc --noEmit` | clean |
| `cd apps/web; npx next lint` | no warnings or errors |
| `cd apps/web; npx next build` | succeeds |
| `cd apps/web; node --experimental-strip-types scripts/check-nav.mjs` | 7 groups, 74 feature routes, 3 utility, 0 problems |

## Second pass: tokens, authorization matrix, cold-start recovery

| Requirement | Status | Code | Tests |
|---|---|---|---|
| Issuer, audience and not-before validation (Part B §4) | COMPLETE | `app/core/security.py` | `test_token_scopes.py`: tokens minted for another issuer or audience, or with none, are refused; a not-yet-valid token is refused |
| Resource-bound temporary tokens (Part B §5) | COMPLETE | `app/core/security.py`, `app/core/deps.py`, `app/routers/auth.py`, `apps/web/lib/api.ts` | A short token is now bound to the case it was issued for; an upload or download token is refused on any other case, including one its holder may access. The browser binds automatically from the request path. |
| Automated authorization matrix (Part B §6) | COMPLETE | `tests/test_authorization_matrix.py` | Walks the application's own route table, so a route added later is covered the moment it exists. Asserts anonymous, malformed, wrongly signed, expired and unknown-scope callers are refused on every route, that upload and download tokens reach only their listed routes, and that a non-member gets 404 on case-scoped routes. Two endpoints are deliberately public and are justified in the test: the service banner and the synthetic scenario options, both static with no case data. |
| Cold-start recovery, no bare 504 (Part C §10) | PARTIAL | `apps/web/app/api/proxy/[...path]/route.ts`, `apps/web/lib/api.ts` | The proxy waits a bounded 25 s and answers 503 with a reason and retry-after instead of letting the platform emit a bodyless 504; the client retries reads with jittered backoff inside a 70 s budget. **Not yet observed against a real cold start in production.** |

Still outstanding from the completion prompt, unchanged: CSRF tokens, shared multi-worker rate limiting, JWT
revocation, the browser end-to-end matrix, accessibility and large-graph performance checks, property-based
fund-conservation tests, dependency audits in CI, durable storage, production OCR, backup and restore, retention and
legal hold, and the independent clean-checkout reproduction.

### Keeping the API awake

The API sleeps after about fifteen minutes idle, which is what produced the waiting states and 504s. The application
pings it every ten minutes while a tab is open. A scheduled external ping (for example a GitHub Actions workflow on a
ten-minute cron hitting `/api/health/live`) would keep it awake when nobody has the app open; that was not added here
because creating a scheduled workflow was refused by this environment's permission policy, so it is left for the
repository owner to add if wanted.

## Live verification (https://ps05x-api.onrender.com, https://rph-ps05x.vercel.app)

Run against the deployed API with a fresh synthetic demo session and a generated Operation Desert Mirage case:

Counts, one case, every surface queried separately:

| Question | counts endpoint | overview | graph | paths endpoint | report |
|---|---|---|---|---|---|
| relationships | 86 | 86 | 86 edges (in_graph 86) | — | 86 |
| paths | 28 | — | — | 28 | 28 |

Token scope:

| Token | Route | Result |
|---|---|---|
| download | `GET /api/cases/{id}` | 403 |
| download | `POST /api/cases` | 403 |
| download | `GET /api/cases/{id}/report.pdf` | 200 |
| upload | `GET /api/cases/{id}/report.pdf` | 403 |
| full | `GET /api/cases/{id}` | 200 |

The API readiness pill was confirmed showing its state on the live web application.

## Live verification, second pass

Against the deployed API and web application, after both tiers were redeployed:

| Check | Result |
|---|---|
| download token bound to case A, on case A `report.pdf` | 200 |
| same token on case B `report.pdf` | 403 |
| same token on an ordinary case read | 403 |
| token signed with another key and issuer | 401 |
| no token | 401 |
| browser: short token minted with `case_id`, own case vs other case | 200 vs 403 |
| browser: one-click demo to workspace | reaches `/overview`, no error alerts, readiness pill shows ready |

Backend suite after this pass: **131 passed** (119 before). Web typecheck, lint and build clean; navigation check
7 groups, 74 feature routes, 3 utility, 0 problems.

Not yet observed live: recovery from a genuine cold start. The code path (proxy answers 503 with a reason after 25 s,
client retries reads with jittered backoff inside 70 s) is implemented and deployed, but the instance did not sleep
during this session, so it is recorded as PARTIAL rather than claimed.

## Not addressed in this pass

The specification is much larger than these defects. Untouched here, and therefore unchanged in status: the full
browser end-to-end matrix, CSRF tokens for state-changing browser routes, a shared multi-worker rate limiter, JWT
revocation strategy, issuer/audience validation, property-based fund-conservation tests, graph accessibility and
large-graph performance tests, the storage retention and legal-hold policy, backup and restore procedures, and the
clean-checkout reproduction by an independent party. None of these should be read as complete.

## v3.0 specification, phases 1–3

| Requirement | Status | Code | Tests | Evidence and limits |
|---|---|---|---|---|
| **PDF bank statements into the transaction schema** | PARTIAL | `apps/api/app/parsers/pdf_statement.py`, `app/services/ingestion.py` | `tests/test_pdf_statement.py` (7) | A PDF whose pages carry a statement table is parsed into the same `Transaction` rows as CSV and XLSX, through the same mapping, normalisation and warning path. Two extractions are scored against each other (PyMuPDF `find_tables` and a word-clustering fallback) because `find_tables` splits amount cells on some layouts; the better-scoring one is used and its confidence recorded as a parser warning. Low and medium confidence adds `pdf_statement_low_confidence_needs_review`. **Not COMPLETE:** verified only against the synthetic statement PDFs generated in this repository, not against real bank PDF layouts, and scanned (image-only) statements still need OCR, which is `BLOCKED_EXTERNAL`. |
| **Explainable mule typologies** | COMPLETE | `apps/api/app/services/typologies.py`, `routers/intel.py`, `apps/web/app/cases/[id]/typologies/page.tsx` | `tests/test_typologies.py` (9) | Seven typologies (rapid in/out, many small credits, round-figure layering, dormant reactivation, repeated counterparties, split and merge, pass-through). Every typology is reported whether or not it triggered; each carries observed values, the published threshold and why that threshold, the transactions that triggered it, the ordinary explanations that fit the same records, and what it cannot see. Dormancy returns `not_enough_history` rather than a result when the statements span less than 90 days. A pass-through ratio above 100% states that money left which did not arrive in the supplied window. No person is labelled, and the account identifier is masked for display. Verified in the browser against a generated case. |
| **Money trail from the victim's own UTR** | COMPLETE | `apps/api/app/services/utr_trace.py`, `routers/intel.py`, `apps/web/app/cases/[id]/utr-trace/page.tsx` | `tests/test_utr_trace.py` (11) | Search normalises references across spacing, case and separators, and returns every candidate with the file and cell behind it. An ambiguous reference is never resolved automatically: each candidate is shown and the investigator chooses. The trail follows a hop only into an account whose own statement is in the case; every stop is listed with the record that would continue it. Verified in the browser: a messy reference (` syn5-JRF6E8X279K `) matched the row, the trace returned one hop with its source file and row, and one unresolved end naming the statement needed to continue. |

### Not implemented from the v3.0 specification

`NOT_IMPLEMENTED`, and not claimed otherwise anywhere in the product: domain, DNS, RDAP, IP, certificate and
subdomain intelligence as a v3.0 subsystem (the existing connectors remain `not_configured`); unified correlation
across the financial and infrastructure sides; combined PDF and Excel reports spanning both; lawful request drafting
templates; an end-to-end synthetic scenario that exercises PDF and XLSX ingestion together; browser end-to-end tests,
accessibility checks and performance budgets as automated gates.

### A note on the local development database

A local SQLite database created by `create_all` carries no Alembic stamp, and `create_all` never alters a table that
already exists. Such a database can therefore be missing a column added by a later migration (here `users.token_epoch`)
while the test suite passes, because the suite builds its schema from the models each run. The local file was brought
to head and stamped. This affects development only: the live PostgreSQL database is built by `alembic upgrade head`
in the start command.
