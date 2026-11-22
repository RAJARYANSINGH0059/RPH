# PS05 v6 roadmap — remaining phases, with the two new workstreams in place

The v6 master prompt (22 November 2026) adds two deliverables to the specification this project was already
working through, and one engineering contract that governs both. This document places them in the remaining
phase sequence so nothing is lost, and records what each phase owes.

Phases 1–3 are finished and live, verified against the deployed API and in a browser: PDF bank statements into
the canonical transaction schema, seven explainable account typologies, and a money trail rooted in the victim's
own transaction reference. `docs/TRACEWEAVE_STATUS.md` holds that evidence.

## The three workstreams

| | Workstream | Where it lives | Rule |
|---|---|---|---|
| **A** | The existing application | `RAJARYANSINGH0059/RPH` | Additive, tested, reversible. Nothing working is removed, no destructive Git, no migration deleted. Feature branch from the newest `main`, merged forward only when verified. |
| **B** | Standalone HTML submission prototype | **Outside** the repository, in a sibling directory | One self-contained file, opens from `file://` with no server, no build and no network. Never committed, never deployed over the live site, never depended on by the application. |
| **C** | Competition intelligence and submission artefacts | Outside the repository | Event brief, portal fields, judging criteria, competitor and prior-art audit, scorecards, pitch, 24-hour playbook, wireframe PDF, action-plan deck. |

Workstreams A and B stay physically separate. Neither imports the other. The research in C informs both and
merges into neither.

## Deadline reality, stated plainly

The action-plan submission is due **24 November 2026, 23:59 IST** — two days from this roadmap. The wireframe
and the HTML prototype are *that* submission's artefacts, not the final's. Workstream A's remaining phases
improve the product for the 28–29 November final, but they do not produce a single thing the action plan needs.

So the honest ordering is: B and C are deadline-critical and A is not. This roadmap runs Phase 4 first because
that is what was asked for, and every B and C item carries the date it is actually needed by. If the action-plan
deadline matters more than Phase 4 depth, B4 and C4 should be pulled ahead of Phase 5.

## Phase 4 — Infrastructure intelligence (Workstream A) · in progress

The connector framework exists and is SSRF-safe, but its coverage is materially narrower than the UI implies.
Verified against the current source on this branch:

- `DnsConnector._fetch_one` queries **`A` only**. The adapter's own attribution text claims "A/AAAA/CNAME".
- `RdapConnector` goes through `rdap.org` and cannot follow the redirect to the authoritative server, so a real
  lookup returns `redirect_not_followed`. Expiry, registrar name and IANA ID are not extracted.
- No PTR, no IPv6 indicator extraction, no IP allocation or ASN enrichment, no Certificate Transparency, no
  passive-DNS adapter.

Phase 4 delivers: the full record set (`A`, `AAAA`, `MX`, `NS`, `TXT`, `CNAME`) with `NODATA`, `NXDOMAIN`,
timeout and resolver-failure kept distinct; PTR reverse lookups for IPv4 and IPv6; RDAP through the IANA
bootstrap registry with redirects validated against the resolved host; registration, expiry, last-changed,
registrar name and IANA ID, status and redaction state; IP allocation and ASN from the RIR RDAP servers;
Certificate Transparency with SAN-derived candidate subdomains; passive-DNS and network-classification adapters
that report `not_configured` honestly rather than pretending; typed entities and relationships for each record
type; and the supplied-observation JSON path extended to the same shapes so a case without any provider key can
still carry dated historical evidence.

Standing constraints, unchanged: current DNS is never relabelled historical, shared IP/ASN/CDN/registrar never
creates a common-owner finding, `live` means a real request succeeded in this process, and no active scanning.

## Phase 5 — Reports and evidence output (Workstream A)

A case XLSX workbook (`Read Me`, `Summary`, `Transactions`, `Account Triage`, `Money Paths`, `Infrastructure`,
`Relationships`, `Counter Evidence`, `Evidence Requests`, `Evidence Index`, `Limitations`), built from the
canonical counts service so no export computes its own totals, with formula-injection sanitising on every
user-derived cell. The PDF report extended to the same sections.

## B4 / C4 — Submission artefacts (needed by 24 November)

**C4 first**, because it decides what B4 shows: re-verify the live event page and the actual portal fields,
capture the PS05 brief in full, locate the published judging criteria or record plainly that none was found,
then build the competitor and prior-art audit and the two scorecards (Top 25 screening, and the final).

**B4**: the standalone HTML prototype — one file, outside the repository, synthetic and internally consistent
across every screen, with working UTR exact/ambiguous/no-match handling, a real hop inspector, typology detail
including dormancy that stays not-assessable, infrastructure tabs that state `SYNTHETIC FIXTURE` or
`NOT_CONFIGURED` rather than faking a lookup, a request composer with no send function, and exports that
produce genuine bytes. Then the wireframe PDF, and the action-plan deck if the portal asks for one.

## Phase 6 — Unified correlation (Workstream A)

Typed relationships for every new observation, a time window control on the graph and timeline, dynamic-IP,
CDN, NAT and reassignment alternatives shown rather than resolved, and cross-case links that stay
permission-aware and never merge identities.

## Phase 7 — Lawful requests and quality (Workstream A)

Request templates per custodian category tied to the specific missing record, with the legal-authority field
never invented by the application and no automatic transmission. Field-level parser disagreement surfaced as
review items instead of averaged away. Cross-statement reversal pairing that keeps both rows.

## Phase 8 — Hardening (Workstream A)

Browser end-to-end coverage of the real flow and the error states, accessibility checks, performance budgets,
dependency audit in CI, migration verification against PostgreSQL, backup and restore, retention and legal
hold. Durable storage and production OCR remain `BLOCKED_EXTERNAL` until a paid instance or bucket exists.

## Phase 9 — One complete synthetic investigation (Workstream A)

A single deterministic case carrying every planted scenario the specification lists — PDF and XLSX statements of
the same rows, an ambiguous reference, a split and a merge, a dormant account with coverage and another without,
a shared-CDN pair that must stay candidate, a CT-derived subdomain, a stale observation, a reversal, an
ambiguous date — run through the ordinary upload pipeline, not inserted into the database.

## Cross-artefact consistency gate (C)

Before submission, one register mapping every claim in the deck, the wireframe, the prototype and the live app
to the code, test or source that supports it. Each capability labelled `LIVE IN REPOSITORY`,
`WORKING IN STANDALONE PROTOTYPE`, `IMPLEMENTED BUT NOT DEPLOYED`, `PLANNED` or `EXTERNAL DEPENDENCY`.
Any mismatch is corrected or removed. No outcome is guaranteed anywhere in any artefact.
