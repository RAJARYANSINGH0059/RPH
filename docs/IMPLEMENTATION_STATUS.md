# Implementation status

Repository at start: empty git repository (`master`, no commits), no code. Everything below was built in this run.

## Existing assets reused

None in the repository. Installed tooling reused: Python 3.12 (FastAPI, SQLAlchemy, Alembic, pandas, NetworkX, scikit-learn already present), Node 24, npm.

## Blueprint section → implementation

| Blueprint section | Status | Where |
|---|---|---|
| §7 Evidence model, bitemporal, locators | Done | `apps/api/app/models`, `alembic/versions` |
| §8 Architecture (Next.js + FastAPI + Postgres + NetworkX) | Done | `apps/web`, `apps/api` |
| §9.1 Upload formats | CSV, XLSX, PDF(text), JSON, DOCX, TXT, PNG/JPG done; OCR guarded (engine not installed); XML/EML not included | `app/parsers` |
| §9.2 Unified transaction schema (paise, raw retained) | Done | `models.Transaction`, `services/ingestion.py` |
| §9.3–9.4 Connector framework, RDAP, DNS, URLhaus, ThreatFox, MISP interface | Done (all optional, status-labelled) | `app/connectors` |
| §9.7 SSRF controls | Done (allowlist, https only, resolved-IP blocklist, timeouts, size/content-type limits, no redirects) | `connectors/base.py` |
| §10 Synthetic Case Factory (truth→artefacts→chaos→public ingest; sealed truth) | Done, 6 scenarios × 4 difficulties × 3 sizes | `app/synthetic` |
| §11 ML triage (rules baseline, LR vs RF vs HGB, scenario split, retention rule) | Done; RF retained | `ml/`, `docs/MODEL_CARD.md` |
| §12 Benchmark (4 configurations, 10 metrics) | Smoke benchmark done (4 seeds) | `tests/benchmark`, `docs/BENCHMARK.md` |
| §13 UI (6 nav items, 11 screens, light theme, states, legend) | Done | `apps/web/app` |
| §14 Security (Argon2id, JWT, RBAC, case IDOR checks, magic bytes, immutable originals, audit) | Done | `core/`, `routers/` |
| §15 GitHub/Vercel/Render config, CI, live deployment | Done (see Deployment below) | `render.yaml`, `apps/web/vercel.json`, `.github/workflows/ci.yml`, `apps/api/Dockerfile` |
| §17 Tests | 38 backend tests + 3 inference tests + benchmark runner | `apps/api/tests`, `tests/e2e` |
| Reports (PDF/JSON/CSV with disclaimer) | Done | `app/reports` |

## Build order followed

1. Credit preflight → 2. models/auth/migrations → 3. parsers + ingestion → 4. graph engine + rules → 5. connectors → 6. synthetic factory + sealed store → 7. reports + routers → 8. tests → 9. ML training → 10. benchmark → 11. frontend → 12. deploy config + docs.

## Gap-closure increment (2026-11-21, branch feat/ps05-cross-case-restitution)

| Gap | Status | Where |
|---|---|---|
| P0-A cross-case correlation | Done (service, API, membership management, UI, 7 tests) | `app/services/crosscase.py`, `app/routers/crosscase.py`, `apps/web/app/crosscase`, `apps/web/components/CrossCase.tsx` |
| P0-B OCR | Done (engine chain, metadata, candidate gating, Dockerfile tesseract eng+hin, 7 tests); Render native runtime uses RapidOCR | `app/parsers/ocr.py`, `app/parsers/documents.py` |
| P0-C path reconstruction | Done (v2 algorithm + 6 new metrics + held-out range); recall limits documented | `app/graph/engine.py`, `tests/benchmark/run_benchmark.py` |
| P1-A victim claims | Done (models, migration, reconciliation, approvals, packs, UI, 2 tests) | `app/services/claims.py`, `app/routers/claims.py`, `apps/web/app/cases/[id]/claims` |
| P1-B cooperation pack | Done (validation, endorsement gate, ZIP export, UI, 1 test) | `app/routers/cooperation.py`, `apps/web/app/cases/[id]/cooperation` |
| P1-C durable storage | Adapter done and unit-tested; not yet enabled on Render (needs bucket + secrets) | `app/services/storage.py` |
| P2 scam-artifact intake | Deferred | — |
| Phase 3 UI | Done (tokens, shell, sign-in, all pages restyled, new screens) | `apps/web` |

## Deployment (2026-11-21)

- GitHub: https://github.com/RAJARYANSINGH0059/RPH (`main`)
- Render API: https://ps05x-api.onrender.com (service `srv-dc0noo67bikc73bbqjug`, Postgres `ps05x-db`), deployed via `scripts/render_deploy.py`; health checks 200.
- Vercel web: https://ps05x-web.vercel.app (project `ps05x-web`), deployed via `vercel deploy --prod` after upgrading Next.js to 15.5.x (Vercel refuses 15.1.x as vulnerable).

## Access blockers

- The folder initially sat inside a stray, commit-less git repository rooted at the user's home directory (`C:/Users/rajar/.git`). A dedicated repository was initialised in the project folder on `main` so that only project files are tracked; the stray home-directory repository was left untouched for the user to remove.

- `gh`, `docker` and `psql` are not installed. Render CLI was installed with winget; both Render and Vercel CLIs were authenticated by the user through browser device flows, and deployment ran from the terminal.
- No Tesseract binary → OCR fallback inactive (flagged, not silent).
- Official PS05 expanded brief/sample data not re-checked in a browser during this run (blueprint §2.1 still applies).
