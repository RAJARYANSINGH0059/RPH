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

### Live verification of phases 1–3 (2026-11-22)

Deployed from this machine: API `dep-dc1bkd6c6qcc73add1n0` live with `migrations: applied`, web deployment
`rph-inwu3e768`. `/api/health/ready` reports `degraded`, which is correct and deliberate: storage and OCR are
optional subsystems and remain unavailable on the free instance.

Against `https://ps05x-api.onrender.com` on a freshly generated case:

- **Typologies** — twelve accounts examined, seven thresholds published, the top account showing three patterns and
  labelled `possible_mule_pattern_requires_review`.
- **UTR search** — an unknown reference returns `not_found` and names the record that would establish it. A real
  reference written messily (lowercase prefix, inserted hyphen, surrounding spaces) returned `exact_single` with the
  source file `statement_5067_victim.csv` and locator `{row: 4}`.
- **Trace** — one hop, one unresolved end naming the statement of the receiving account, accounts masked
  (`11******5067`, `12******6855`).
- **PDF statement** — a synthetic statement PDF uploaded to the live API was parsed by `pdf_statement`, producing
  four transactions with a derived column mapping, a recorded extraction confidence of `medium`, the
  `pdf_statement_low_confidence_needs_review` warning, and file status `needs_review`. This first run also exposed a
  warning recorded twice, which was fixed and re-verified live: the parse run now carries three distinct warnings.

Both new pages were driven in a browser against a local case: the typologies page expanded each pattern with its
observed values, threshold, triggering transactions, alternatives and limits; the trace page searched, listed the
candidate with its source cell, and traced from it. Page load on the warmed production alias: typologies 617 ms,
UTR trace 436 ms.

Badges on both pages were corrected during verification. They had borrowed the evidence-level vocabulary, so a
debit displayed as `CONTRADICTED`, an exact reference match as `CORROBORATED`, and an observed pattern as
corroborated evidence. Each badge now states what it means. A precision badge also fired on every row, because the
vocabulary is `second|minute|day|month|unknown|ambiguous` and the check compared against a non-existent `exact`;
it now flags only genuinely imprecise timestamps.

## v6 specification, Phase 4 — infrastructure intelligence

Branch `feat/ps05-infra-intelligence`, cut from `main` at `f5df682`. Baseline before the work: 189 backend tests
passing, clean web build, clean working tree.

### What the audit said, verified against the source on this branch

Both findings were confirmed by reading the code, not carried over from the audit text:

- `DnsConnector._fetch_one` queried `A` and only `A`, while the adapter's own attribution string promised
  "A/AAAA/CNAME". The screen offered DNS intelligence and the code asked one question.
- `RdapConnector` asked `rdap.org`, which answers with a redirect to the authoritative server, and the fixed host
  allowlist could not follow it. A real lookup therefore returned `redirect_not_followed` and no registration
  data at all. Expiry, registrar name and IANA ID were never extracted.

| Requirement | Status | Code | Tests | Evidence and limits |
|---|---|---|---|---|
| **Full DNS record coverage** (`A`, `AAAA`, `CNAME`, `MX`, `NS`, `TXT`) | COMPLETE | `app/connectors/dns_records.py`, `connectors/adapters.py` | `tests/test_infra_intelligence.py` | Every requested type is reported, including the ones that returned nothing. `nodata`, `nxdomain`, `timeout`, `no_nameservers` and `resolver_error` are kept distinct and each carries a meaning the UI quotes, because "no MX record" and "the resolver timed out" must never look the same to a reader. Each record type is read on its own terms: an MX preference is kept, and a TXT record's several strings are not joined. TTL bounds reuse from the observation time and is labelled as that, not as a validity proof. |
| **Reverse DNS (PTR), both families** | COMPLETE | `dns_records.query_ptr`, `services/infra_graph.py` | same | `in-addr.arpa` and `ip6.arpa` names are built for IPv4 and IPv6; the result is filed against the address, not the domain. Carries the limitation that a PTR name is published by whoever holds the address block. |
| **IPv6 indicators** | COMPLETE | `app/parsers/indicators.py` | same | Addresses of both families are extracted from free text, including bracketed forms with a port. Candidates are validated by the standard library rather than by a regex that would accept a time or a ratio. `2001:db8::/32` is recognised as the IPv6 documentation range, so synthetic fixtures are never looked up. A pre-existing ordering bug was fixed in passing: `is_private` was tested before `is_link_local`, which made the narrower label unreachable and reported "private" for every link-local address. |
| **RDAP registration** | COMPLETE | `app/connectors/rdap_bootstrap.py` | same | The IANA bootstrap registry (RFC 7484) names the authoritative server for a TLD, so the request goes straight there and `redirect_not_followed` is gone. Registration, expiry, last-changed, registrar name, registrar IANA ID, status, nameservers, delegation signing and redaction state are extracted; a field the registry does not supply stays absent, and a withheld registrant is reported as withheld. |
| **IP allocation and ASN** | COMPLETE | `rdap_bootstrap.ip_fields`, `IpRdapConnector` | same | The most specific block in the registry decides which RIR is asked. Prefix, network name and type, country, allocation dates, holding organisation and the originating AS where the registry supplies it. Every result says the holder of a range is not the subscriber and not a person's location. |
| **Certificate Transparency and SAN subdomains** | PARTIAL | `app/connectors/certs.py` | same | Issuer, common name, SANs, validity window, serial and log entry time are parsed, and validity state is computed from the certificate's own window. SAN names inside the domain become candidate `HAS_SUBDOMAIN` edges labelled as discovered names that this system has not resolved; names outside it become candidate `SHARES_CERTIFICATE` edges carrying the ordinary platform and CDN explanations. A wildcard stays a wildcard rather than being expanded into names nobody observed. This source supplies no SHA-256 fingerprint, so none is invented and the field says so. **Not COMPLETE:** `ENABLE_CT` is off and no live request has been made, so the adapter is `not_configured` rather than verified against the provider. |
| **Historical passive DNS** | BLOCKED_EXTERNAL | `PassiveDnsConnector`, `parsers/technical_json.py`, `services/infra_graph.py` | same | The adapter, its request shape and its normalised result exist and the mapping is tested, but it needs a licensed provider: with no `PASSIVE_DNS_URL` and key it reports `not_configured` and says what configuring it would take. Dated historical observations enter through the supplied-observation path instead, which now accepts `passive_dns` / `historical_dns` and keeps the provider's own first-seen and last-seen as the relationship's validity window. Nothing is ever reconstructed from a current lookup. |
| **VPN / proxy / Tor indicators** | PARTIAL | `NetworkClassificationConnector` | same | The Tor Project publishes its exit list for this purpose, so that check is implemented behind `ENABLE_TOR_EXIT_LIST`, off by default. A listing is recorded as a statement about the address, with the limitation that an exit node carries other people's traffic by design and a negative result means only that the list did not contain the address when read. No VPN or proxy provider is configured and the adapter says so rather than leaving a blank. |
| **Typed relationships per record type** | COMPLETE | `app/services/infra_graph.py` | same | A record becomes the edge it means: `RESOLVES_TO` for an address record, `ALIAS_OF` for a CNAME, `MAIL_EXCHANGE` for an MX, `USES_NAMESERVER` for an NS, `REVERSE_DNS` for a PTR, `ALLOCATED_TO` and `ANNOUNCED_BY` for allocation, `REGISTERED_WITH` for registration, `NAMED_IN_CERTIFICATE`, `HAS_SUBDOMAIN` and `SHARES_CERTIFICATE` for certificates. A TXT record names no second entity and creates no edge. A record type that did not answer creates no edge at all. Shared nameservers, autonomous systems, registrars and certificates arrive as candidates with their alternatives; no path in this code can produce `COMMON_OPERATOR`, which remains confined to the benchmark baseline. |
| **Supplied observations for the same shapes** | COMPLETE | `app/parsers/technical_json.py`, `services/ingestion.py` | same | `certificate`, `ptr`, `asn`, `passive_dns`, `historical_dns` and `subdomain` are accepted, and a `dns` observation that names a record type other than `A` is now read as that type instead of as a resolution. Supplied and fetched observations go through one mapping, so they become the same kind of edge with the same limitations. The evidence records both the type the file declared and the shape it was read as. |
| **Infrastructure workspace** | COMPLETE | `GET /api/cases/{id}/infrastructure`, `app/services/infra_view.py`, `apps/web/app/cases/[id]/infra/records/page.tsx` | same | Built from stored evidence rather than recomputed, so the page, the graph and the report agree. Per domain: which record types were asked, which answered, which were never asked, the values, TTL, read time, reuse window and resolver, plus registration and certificate-derived names. Per address: allocation, reverse DNS, hosting, classification and the domains seen there. Current and dated historical observations are shown in separate places. Providers that are not configured are listed as such. The earlier observation shapes a case already holds are read too, so the page is not blank for cases recorded before this work. |

### Outbound safety, unchanged in substance

The bootstrap registry replaces the fixed allowlist for RDAP, not the address checks. A host named by the registry
is still resolved and still refused if it points anywhere private, loopback, link-local, multicast, reserved or at
cloud metadata, and so is every redirect hop: `follow_redirects` stays off and each hop is validated before it is
requested, with a cap of three. A redirected POST is not replayed as a POST. Tests cover a redirect towards a
private address and an endless chain. Reserved names (`.test`, `.example`, `.invalid`, `.localhost`, `.local`,
and `example.com`) and both families' documentation ranges are never looked up, which is where every synthetic
fixture lives.

### Tests

`python -m pytest -q` from `apps/api`: **226 passed** (189 before this phase, 37 added). `npx tsc --noEmit` clean.
`node --experimental-strip-types scripts/check-nav.mjs`: 7 groups, 77 feature routes, 0 problems.

Verified in a browser against an existing synthetic case: the page read that case's own observations, showed its
single domain with the `A` record answered and the other five record types marked not asked, the address with its
documentation classification, all ten providers as `not_configured` or `mock`, and the relationship counts the
graph actually holds.

### What Phase 4 does not claim

No provider was exercised live, so nothing in this phase is verified against a real registry, resolver or log.
Every adapter reports `not_configured`, which is the honest state: `live` means a real request succeeded in this
process, and none has. The record parsing, the bootstrap selection, the field extraction, the typed mapping and
the address checks are tested against fixtures and a fake resolver, which proves the logic and not the providers.

### Live verification of Phase 4 (2026-11-22)

Deployed from this machine: API `dep-dc1c97uc6qcc73af4sj0` live with `migrations: applied`; web deployment
`rph-dsk38daou`. `GET /api/cases/{id}/infrastructure` on a freshly generated case returned three domains and
three addresses read from that case's own observations, the six record types named with `AAAA`, `CNAME`, `MX`,
`NS` and `TXT` reported as **not asked** rather than as absent, relationship counts of `RESOLVES_TO` 7,
`HOSTED_ON` 3 and `SHARED_INFRASTRUCTURE` 1 (candidate, with counter-evidence), nine providers reported
`not_configured`, **no provider reporting `live`**, and six limitations attached. Warmed production page load:
`/cases/{id}/infra/records` 751 ms.

## v6 specification, Phase 5 — the combined case report

The brief names three things the 24-hour final must demonstrate, and the third is *"Domain and IP lookup for the
sample indicators **with a combined case report**"*. The product could emit JSON, PDF and a transactions CSV but
had no workbook, so this was the only must-have it did not fully meet.

| Requirement | Status | Code | Tests | Evidence and limits |
|---|---|---|---|---|
| **Case workbook (XLSX)** | COMPLETE | `apps/api/app/reports/workbook.py`, `routers/reports.py`, `core/scopes.py`, `apps/web/app/cases/[id]/reports/page.tsx` | `tests/test_case_workbook.py` (26) | `GET /api/cases/{case_id}/report.xlsx`, case-membership checked and audited, served with the OOXML media type and a filename built from the case id and date rather than from the case title. All eleven sheets the specification names: Read Me, Summary, Transactions, Account Triage, Money Paths, Infrastructure, Relationships, Counter Evidence, Evidence Requests, Evidence Index, Limitations. Frozen header rows and autofilters throughout. |
| **Counts agree across every export** | COMPLETE | `services/counts.py` consumed by `reports/builder.py`, read by the workbook | same | The workbook recomputes nothing: it is built from the canonical report, which carries the canonical counts. Tests assert the Summary sheet against `GET /counts` field by field, that the Transactions sheet carries exactly the transaction ids the case holds, and that the JSON export and the workbook agree on the same case. |
| **Formula-injection sanitising** | COMPLETE | `workbook._clean` | same | A cell beginning with `=`, `+`, `-` or `@` is prefixed with an apostrophe. The test uploads a statement whose narrations are `=HYPERLINK(...)`, `+SUM(1+1)`, `-2+3` and whose references include `=cmd\|'/c calc'!A1`, `@SUM(1+1)` and `DDE\|x`, then asserts that no cell in any sheet would execute — **and** that the hostile text is still present, prefixed rather than discarded, because it is evidence. |
| **Integer money preserved** | COMPLETE | `workbook._rupees` | same | `amount_minor` is written as a whole number of paise and is named in the Read Me as the authoritative column. The rupee column beside it is rendered by integer arithmetic, never by floating-point division, so the export cannot introduce a rounding the case did not have. |
| **Absence written as a word** | COMPLETE | `workbook._clean` | same | No cell is left blank: an empty value becomes `not supplied`. A blank in a spreadsheet reads as nothing to report, which is exactly the wrong reading for a missing record. |
| **PDF report extended to the same sections** | COMPLETE | `reports/builder.report_pdf` | same | Added: a Summary quoting the canonical counts and naming the counts version; Account behaviour patterns with the threshold each was judged against, the rows behind it and the ordinary explanations that fit the same records; Unresolved path ends with why each stops and what would resolve it; Information request drafts stating that the system never transmits them; and a Limitations block before the closing disclaimer. |
| **JSON export carries the same additions** | COMPLETE | `reports/builder.build_report` | same | `typologies`, `evidence_requests` and `limitations` were added to the canonical report, so the three exports are presentations of one model rather than three analyses. `transmitted_by_this_system` is `false` on every request row. |

### Authorisation

`report.xlsx` was added to `DOWNLOAD_ROUTES`, so a scoped download token reaches it exactly as it reaches the
other exports and nothing else. Tested: a download token may fetch the workbook but not `/auth/me`; an upload
token may not fetch it; another member's case returns 404; an unauthenticated request is refused.

### Tests

`python -m pytest -q` from `apps/api`: **255 passed** (229 before this phase, 26 added). `npx tsc --noEmit`
clean.

### What this phase does not claim

The workbook is verified against synthetic cases generated by this repository, not against R4C's sample data,
which has not been seen. The sheets are built from what the case holds: a case with no infrastructure evidence
produces an Infrastructure sheet carrying its limitations and nothing else, which is the honest result rather
than a defect.

## Ingestion rehearsal against unfamiliar layouts

Recorded in full in `docs/INGESTION_REHEARSAL.md`. Ten layouts the synthetic factory does not produce were put
through the real upload pipeline; eleven of eighteen checks failed on the first run, five of them genuine
defects in the product.

| Defect | Status | Code | Tests |
|---|---|---|---|
| A tab-separated statement parsed as one column per line, because `csv.Sniffer` read the preamble rather than the body | FIXED | `parsers/tabular._sniff_delimiter` | `tests/test_statement_rehearsal.py` (18) |
| A branch line above the header was read as the header | FIXED | `parsers/tabular._header_score` | same |
| Trailer lines such as `*** End of Statement ***` became transactions with no date, amount or reference | FIXED | `services/ingestion._ingest_statement` | same |
| A statement behind a cover sheet was discarded, with only a `multiple_sheets` warning | FIXED | `parsers/tabular.parse_xlsx_all_sheets`, `looks_like_statement` | same |
| A workbook holding one account per worksheet collapsed into a single inferred statement holder | FIXED | `services/ingestion` — the worksheet is part of the inferred identity | same |

Four further failures were incorrect expectations rather than defects, and the reasoning is recorded rather than
quietly adjusted: a date with no time is midnight in the source's zone, so `01/05/26` is `2026-04-30T18:30Z`; a
two-digit year is reported `ambiguous` while a four-digit `dd/mm` is read day-first and says `day_first_assumed`;
unquoted commas inside an amount make the file malformed CSV, which the parser correctly reported; and a file
with unreadable headers keeps its rows while normalising none of them.

**Tests:** `python -m pytest -q` from `apps/api`: **273 passed** (255 before, 18 added). Verified on the deployed
API: all five previously-failing layouts produce the expected transactions, and the two-account workbook now
produces two distinct statement holders where it previously produced one.

**What this does not establish:** that R4C's sample data will parse. These layouts were written by the same
person who wrote the parser, which is weaker than an export nobody here has seen. The analyst remapping path
exists for the layout that defeats automatic mapping, and the rehearsal pins that it keeps the original file's
bytes and hash while recording a new parse run.
