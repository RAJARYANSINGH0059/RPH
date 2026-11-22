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

## Not addressed in this pass

The specification is much larger than these defects. Untouched here, and therefore unchanged in status: the full
browser end-to-end matrix, CSRF tokens for state-changing browser routes, a shared multi-worker rate limiter, JWT
revocation strategy, issuer/audience validation, property-based fund-conservation tests, graph accessibility and
large-graph performance tests, the storage retention and legal-hold policy, backup and restore procedures, and the
clean-checkout reproduction by an independent party. None of these should be read as complete.
