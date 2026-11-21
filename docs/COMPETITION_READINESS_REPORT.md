# Competition readiness report — PS05-X (2026-11-21)

Repository: https://github.com/RAJARYANSINGH0059/RPH · branch `feat/ps05-cross-case-restitution`, fast-forwarded into `main`.
Scope: gap-closure run on top of the existing FastAPI + Next.js + SQLAlchemy/Alembic + NetworkX architecture (nothing rebuilt).

## 1. Completed work

| Area | Delivered | Evidence |
|---|---|---|
| Cross-case money-trail correlation (P0-A) | Permission-aware query-time service; classes exact / corroborated / derived / candidate / stale; provenance per link (source case, file SHA-256, locator, method/version, event/observed time, quality flags, limitations, counter-evidence); similar names reported under *not asserted*; membership grant/revoke; `/crosscase` workspace and per-case *Related cases* panel with accessible tables | `apps/api/app/services/crosscase.py`, `routers/crosscase.py`, `tests/test_crosscase.py` (7 tests), `apps/web/components/CrossCase.tsx` |
| OCR (P0-B) | Engine chain Tesseract (eng+hin, Dockerfile) → RapidOCR (pure Python) → explicit unavailable warning; engine, version, confidence, quality and boxes stored on evidence; low-confidence mentions are graph candidates; OCR preview in Upload with “needs human verification” | `parsers/ocr.py`, `parsers/documents.py`, `tests/test_ocr_and_storage.py` (7 OCR tests, incl. engine-absent) |
| Path reconstruction v2 (P0-C) | Hop classes (observed / corroborated / uncertain_time), split/merge flags, explicit unresolved hops with the statement that would resolve them, alternatives, no invented accounts; benchmark adds coverage, false-path rate, amount conservation, temporal consistency, unresolved-hop rate, runtime with bootstrap 95% CIs; frozen held-out seed range and held-out typology | `graph/engine.py`, `tests/benchmark/run_benchmark.py`, `docs/BENCHMARK.md` |
| Victim claims & restitution readiness (P1-A) | New tables + Alembic migration `7e960fbc555c`; claimed / traced / documented-held / restored / unresolved kept apart; distinct-transaction counting; competing and duplicate detection; hold/restoration records require a non-statement source document; simulated holds labelled; approval states draft → investigator → supervisor → export ready; PDF/JSON pack; audit on every action; synthetic multi-victim scenario now ships a simulated hold notice | `services/claims.py`, `routers/claims.py`, `tests/test_claims_and_cooperation.py`, `apps/web/app/cases/[id]/claims` |
| Cross-state cooperation pack (P1-B) | Required-field and 10–500 character validation, FIR + supervisor-endorsement attachments, supervisor endorsement gate, ZIP with manifest.json (hashes), summary PDF, attachments and money/infra trace; no portal automation | `routers/cooperation.py`, `apps/web/app/cases/[id]/cooperation` |
| Durable storage (P1-C) | S3-compatible adapter (private bucket, server-side credentials, hash verification on write/read, signed URLs ≤15 min, size limit, visible fallback); health reports backend | `services/storage.py` |
| UI/UX | Light-mode “operations room” design tokens, navy rail, sandstone canvas, breadcrumbs, environment pills (synthetic / uploaded / no live connection), skeleton and retry states, all pages restyled, three new screens; mobile navigation; no insignia; label “PS05-X · Investigative prototype” | `docs/UI_UX_REDESIGN.md` |
| Latency | gzip middleware, bounded OCR threads, OCR off on the 512 MiB instance (the OCR runtime caused an OOM kill) | `app/main.py`, `parsers/ocr.py`, Render env |

Deferred: P2 scam-artifact intake, Hindi UI labels, 600-case benchmark, S3 enabled on the live service (see `docs/REMAINING_BLOCKERS.md`).

## 2. Tests and checks (actually run)

| Check | Command | Result |
|---|---|---|
| Backend unit / integration / security / determinism / migration / cross-case / OCR / claims / cooperation / storage | `cd apps/api; python -m pytest -q` | **58 passed** |
| Backend lint | `ruff check app tests --select E,F,W --ignore E501,E731,E741` | clean |
| Frontend | `npx tsc --noEmit`, `npx next lint`, `npx next build` | clean; 16 routes built |
| GitHub Actions on `6f1abf0` (feature branch) | https://github.com/RAJARYANSINGH0059/RPH/actions/runs/44902132758 | **success**: backend tests + PostgreSQL migration up/down + 2-seed benchmark + inference test; frontend lint/build/typecheck; gitleaks |
| Visual inspection (browser pane) | 1366×900: sign-in, cases, case overview, graph with selected edge + evidence panel, claims, cross-case correlation; 375×812: cases (no horizontal overflow) | screens render; one defect fixed (graph canvas first paint) |

## 3. Benchmark (synthetic only; F1 is not accuracy)

Smoke (seeds 500–503, 384 runs) and frozen held-out (seeds 700–703, 384 runs, `fake_customer_care` as held-out typology), configuration D = full verification layer:

| Metric | Smoke | Held-out |
|---|---|---|
| Transaction edge F1 | 0.550 | 0.551 |
| Entity resolution F1 | 0.993 | 0.992 |
| False links asserted from shared hosting | **0** (vs 144 without safeguards) | **0** (vs 144) |
| Counter-evidence recall | 0.871 | 0.851 |
| Path coverage (95% CI) | 0.977 (0.956–0.995) | 0.958 (0.932–0.979) |
| False-path rate (multi-hop) | 0.227 (0.193–0.266) | 0.220 (0.179–0.267) |
| Amount conservation | 0.728 | 0.722 |
| Temporal consistency | 0.879 | 0.853 |
| Unresolved-hop rate | 1.000 (bundles contain no second-layer statements; v2 names the missing statement) | 1.000 |
| Held-out typology `fake_customer_care` edge F1 | — | 0.539 (other families 0.524–0.577) |

Held-out numbers match the development seeds within the intervals, so no tuning leakage is apparent. Raw per-case rows: `tests/benchmark/results/benchmark_summary.json`, `heldout_summary.json`.

## 4. Deployment (verified live)

| Target | URL | Verified |
|---|---|---|
| Render API (project RPH, service `rph`, `srv-dc0noo67bikc73bbqjug`, Singapore, free) | https://ps05x-api.onrender.com | `/api/health/live` and `/api/health/ready` 200 on commit `6f1abf0`; migration `7e960fbc555c` applied; from the terminal: sign-in, multi-victim synthetic case (3.8 s), cross-case correlation of two cases (0.4 s; 17 corroborated / 4 exact / 30 derived / 1 stale), claim + link + simulated hold → reconciliation, readiness pack PDF, cooperation pack validation → supervisor endorsement → ZIP export, paths with resolution hints, gzip responses, no COMMON_OPERATOR edges |
| Vercel web (project `rph`) | https://rph-ps05x.vercel.app and https://ps05x-web.vercel.app | 200; redesigned UI served; reports “API ready” when the API is awake |
| Local | http://localhost:3000, http://localhost:8000 | running during this session; `scripts/run_local.ps1` restarts both |

Render did not auto-deploy on pushes; deploys were triggered with `python scripts/render_deploy.py`. One incident: the first live OCR request was OOM-killed on the 512 MiB instance; `OCR_ENGINE=off` was set and the service redeployed (RapidOCR remains active locally and in tests).

## 5. Unavailable credentials / integrations

- No GitHub token usable for the REST API from this machine, so the pull request was not opened automatically. Open it here: https://github.com/RAJARYANSINGH0059/RPH/pull/new/feat/ps05-cross-case-restitution (the branch is pushed; `main` already contains it by fast-forward).
- No S3/R2 bucket credentials: live uploads stay on the ephemeral disk.
- No external connector keys (RDAP/DNS/URLhaus/ThreatFox/MISP remain `not_configured`); no police/bank/NCRP/CFCFRMS/MRM access, by design.

## 6. Known gaps

See `docs/REMAINING_BLOCKERS.md` and `docs/LIMITATIONS.md`. Headlines: OCR off on the free instance; Hindi OCR only via the Docker image; edge F1 under noise ~0.43–0.49; benchmark is a smoke-sized run; cooperation-process page not re-verified; official PS05 expanded brief to be checked manually before submission.

## 7. Recommended demo sequence (8 minutes)

1. Sign in → cases registry → **One-click demo case** (multi-victim, messy).
2. Upload: show parser warnings and, locally, the OCR preview with confidence and “needs human verification”.
3. Transactions: raw strings, ambiguous-date badges, duplicates, reconstructed paths with the unresolved hop and the statement it asks for.
4. Graph (Money trail focus): click a corroborated transfer, then a dashed SHARED_INFRASTRUCTURE edge → counter-evidence; show that “Supported” is refused for an analyst.
5. Related cases → correlate with a second case: corroborated bridges with hashes/locators; *Not asserted* similar names.
6. Victim claims: record three claims, link transactions, record the simulated hold → oversubscribed flag, no allocation; advance to export-ready; download the readiness pack.
7. Cooperation pack: validation checklist → supervisor endorsement → ZIP with manifest hashes.
8. Reports + benchmark slide: 0 false links with safeguards vs 144 without; coverage 0.96–0.98 with explicit unresolved hops.

## 8. Usage

Official plan panel at the start of this run: 5-hour window 49% used, weekly 20% used. Final figures are reported in the closing message of the session, not estimated here.
