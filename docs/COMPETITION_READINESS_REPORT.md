# Competition readiness report and handover — PS05-X (2026-11-22)

Repository: https://github.com/RAJARYANSINGH0059/RPH · branch `feat/ps05-digital-twin` (starting commit `3db7f83` on `main`; increment commits `02387f8`, `1df8f65` and the next-wave gap-closure commit that follows this report).
Scope: the Global Research Integrated Master Prompt, the Claude Implementation Prompt and the Next-Wave Implementation Prompt, implemented inside the existing FastAPI + Next.js + SQLAlchemy/Alembic + NetworkX architecture. Nothing was rebuilt; the gap-closure increment of 2026-11-21 remains intact (its report is in the git history of this file at commit `3db7f83`).

## 1. Preservation check

- All 58 pre-existing backend tests still pass unchanged (cross-case, OCR chain, claims, cooperation, storage adapter, migrations, RBAC, parsers, determinism, sealed-truth non-exposure).
- Every pre-existing route is still registered (122 routes in total); response contracts were extended, never changed.
- Regressions found and fixed during the increment: SQLite "database is locked" under parallel dashboard reads (WAL + 30 s busy timeout); plain-text captures mis-detected as CSV (`detect_kind` tightened); a generator artefact that perturbed a duplicated row so a planted balance break was unobservable (generator 0.4.1).
- Local databases created before the increment have no Alembic stamp; the documented recovery is `alembic stamp 7e960fbc555c` then `alembic upgrade head` (or move the disposable file aside).

## 2. Feature status (definitions: `docs/FEATURE_MATRIX.md`)

Implemented and verified (API + UI + permissions + persistence + tests executed): payment-instruction bridge; fraud-operation digital twin, victim journey, investigation replay; evidence coverage; proof-carrying money trail with offline verifier; temporal evidence fusion; FATF-attributed lifecycle and dependency map; role-sensitive review and account-control timeline; missing-evidence map, Evidence Acquisition with custodian catalogue, lifecycle, manual dispatch record, draft PDF and **response attachment with preserved remainder**; IVOI; preservation desk; completeness; bounded fund provenance with gap modelling, FIFO/LIFO scenarios and **reversal gross-vs-net**; Evidence Adversary / CounterProof with actions and dissent; hypotheses and independent blind review; counterfactual lab; branches; chokepoints and network-adaptation simulator; intervention impact with acknowledgement gate; statement forensics and PDF metadata leads; campaign DNA and rotation; keyed-token privacy matching (off without key); prevention-rule compiler; one-click demo sessions via BFF cookie; blind challenge with **graph-only baseline comparison**; **proof-carrying investigation package**; adversary alternatives on cross-case links; single left navigation registry; benchmark v2.

Implemented, verification incomplete: graph workbench interactions and motion scenes (typecheck/lint/build pass, visual checks at 1366×900 and 375×812, no automated interaction test).

Partially implemented: field-level extraction disagreement (no second tabular parser); cross-statement reversal pairing.

Blocked: Hindi OCR on the live 512 MiB instance; historical passive DNS (no provider); durable S3 storage on the live API (no bucket credentials).

Not implemented: geospatial map (deliberately, while IP geolocation is the only candidate source); STIX/TAXII export; APK intake; Hindi UI labels.

## 3. Files and modules changed (why)

Backend: `models/twin.py` + migration `2222d8017e5e` (nine additive tables, demo users); `parsers/qr.py`, `services/payment_bridge.py` (bridge); `services/{twin,coverage,proof,temporal,lifecycle,roles,dependencies,bounded_flow,campaign,adversary,integrity,resilience,intervention,counterfactual,privacy_tokens,completeness,rulecompiler,contract,package,baseline}.py`; routers `intel.py`, `intel_global.py`, `benchmark.py`, `auth.py` (demo-session, short-token, logout), `synthetic.py` (challenge); `core/deps.py` (demo restrictions, expiry), `core/security.py` (scoped tokens); `synthetic/{mirage,generator,artifacts,challenge}.py` (0.4.1); `db/session.py` (WAL); `parsers/common.py`; `scripts/verify_proof.py`; `requirements.txt` (`qrcode`).
Frontend: `lib/{api,server,nav,guide}.ts`, `app/api/session/*`, `app/api/proxy/[...path]`, `components/{Shell,ui,motion,CasePage,ListPage,icons,CrossCase}.tsx`, 12 hand-written and 50 generated feature pages, graph page workbench, `scripts/check-nav.mjs`.
Benchmark and CI: `tests/benchmark/run_benchmark_v2.py`, results JSON, CI steps (benchmark v2 smoke, verifier help, nav check).
Docs: this report plus GLOBAL_COMPETITIVE_LANDSCAPE, RAJASTHAN_OPERATIONAL_FIT, OPERATION_LIFECYCLE_AND_DEPENDENCY_MODEL, ROLE_SENSITIVE_REVIEW_SAFEGUARDS, PROOF_CERTIFICATE_SPEC, BOUNDED_FUND_ATTRIBUTION_SPEC, BENCHMARK_V2, FEATURE_MATRIX; README, ARCHITECTURE, DEPLOYMENT, DEMO_SCRIPT, LIMITATIONS, REMAINING_BLOCKERS, IMPLEMENTATION_STATUS updated.

## 4. Database migration and rollback

`2222d8017e5e_digital_twin_tables_and_demo_users` (additive; runs in the Render start command). Rollback: `alembic downgrade 7e960fbc555c` drops the nine tables and `users.is_demo` / `users.expires_at` after deleting demo users; the PostgreSQL enum value `demo_analyst` remains (enum values cannot be dropped in place). Back up before downgrading. No data migration touches uploaded bytes, hashes, locators or memberships.

## 5. New APIs and permission boundaries

Case-scoped (`/api/cases/{id}/…`, membership enforced by `get_case_or_404`, non-members receive 404): twin, twin/journey, twin/replay, twin/events; payment-instructions (list, register, decode-image, match, report.pdf); coverage; integrity; temporal; paths/{i}/proof.json|pdf; files/{id}/download; lifecycle; roles/{acct} (+decision supervisor/admin, control-timeline); dependencies; ivoi; preservation; requests (+status with supervisor gate for authorised/sent_manual, +response, draft.pdf); bounded-flow; intervention/{acct} (acknowledgement required); chokepoints; resilience/simulate|scenarios; lab/profiles|run|runs; branches (+compare); hypotheses (+update, review-view, reviews); adversary (+edge, action); completeness; views; role-reviews; package.zip.
Global: campaign/compare, campaign/fingerprint/{id}, privacy/status|match|reveal (audited; disabled without key), rules list/compile/decision (approval gate), benchmark/results, benchmark/model-card, audit/mine.
Auth: `POST /api/auth/demo-session` (origin check, per-IP limit, 240-min expiry, synthetic-only demo principal), `POST /api/auth/short-token` (upload/download scope, 10 min), `POST /api/auth/logout`. Demo users cannot see, join or create non-synthetic cases (tested). Sealed truth is served only by `challenge/reveal` after a locked submission, synthetic cases only (tested); the package builder refuses sealed-truth keys (tested).

## 6. Tests and checks (actually run, 2026-11-22)

| Check | Command | Result |
|---|---|---|
| Backend | `cd apps/api; python -m pytest -q` | **103 passed** (58 pre-existing + 45 new across 6 files) |
| Backend lint | `ruff check app tests --select E,F,W --ignore E501,E731,E741` | clean |
| Frontend | `npx tsc --noEmit`, `npx next lint`, `npx next build` | typecheck clean; lint 2 pre-existing warnings (unused index variables); build OK |
| Navigation registry | `cd apps/web; node --experimental-strip-types scripts/check-nav.mjs` | 12 groups, 74 feature routes, 3 utility routes, 0 problems |
| Offline verifier | `python scripts/verify_proof.py <proof.json> --files <dir>` | PASS on originals; FAIL on a modified file and on a modified manifest (tested) |
| Browser (pane) | sign-in → overview → factory (Desert Mirage) → twin, bridge, bounded flow, counterproof, lifecycle, graph, roles, ivoi, resilience, intervention, challenge, requests; 375 px width | render with real data; no horizontal overflow |

Pre-existing failures: none. Skipped: none (one test skips only if the generated case has no path starting at a statement-less account).

## 7. Benchmark

Benchmark v1 (false-link safeguards) unchanged: 0 false links with safeguards vs 144 without; details in `docs/BENCHMARK.md`.
Benchmark v2 (`docs/BENCHMARK_V2.md`, 30 cases = 5 families × 6 seeds, generator 0.4.1): attribution coverage 1.00 (false-exact 0, width ratio 0.62), gap detected 1.00 / false observed-zero 0, balance-break recall 1.00, innocent triage flag rate 0.049, knowing participation auto-asserted 0, common-operator edges 0, proof verify / tamper 1.00 / 1.00, lab robustness 1.00, rotation recall 1.00 / benign false cluster 0. Graph-only baseline vs PS05-X on identical cases: baseline asserts 1.0 common-operator decoy pair per case, PS05-X 0; path recall 0.74 vs 0.75 (both bounded by missing statements); PS05-X does not label the unrelated counterparties it reaches, the baseline does. All synthetic; CIs and limitations in the document.

## 8. Deployment

Status at the time of writing: committed locally on `feat/ps05-digital-twin`; push, merge to `main`, Render (`python scripts/render_deploy.py`) and Vercel (`cd apps/web; vercel deploy --prod --yes`) deploys and live verification are performed after this report and recorded in the closing message of the session, not assumed here. Live URLs remain https://ps05x-api.onrender.com and https://rph-ps05x.vercel.app. Required live env additions: none mandatory (`PROOF_SIGNING_KEY`, `CROSSCASE_TOKEN_KEY` optional; `API_BASE_URL` optional for the BFF).

## 9. Unconfigured integrations and remaining dependencies

No bank, police, CFCFRMS/NCRP, I4C, telecom, registrar, passive-DNS or threat-intelligence connection exists or is claimed (connectors stay `not_configured`). No S3 bucket on the live API. Proof HMAC and privacy tokens are off on the live API until keys are set. GitHub PR creation needs a token on this machine. See `docs/REMAINING_BLOCKERS.md`.

## 10. Known limitations and next highest-value work

`docs/LIMITATIONS.md` (full list). Next: Playwright interaction smoke over the Desert Mirage pages; a second tabular parser for field-level disagreement; cross-statement reversal pairing; larger benchmark v2 sample; enabling S3 and OCR on a paid instance.

## 11. Claims policy

No claim of police adoption, bank integration, real-world accuracy, legal admissibility, recoveries, world-first status or competition outcome is made anywhere in the product or documentation. Synthetic metrics are labelled synthetic on every screen that shows them.

## 12. Demo

`docs/DEMO_SCRIPT.md` section A (Operation Desert Mirage, 12 steps, ~10 minutes).
