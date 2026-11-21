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
| §15 GitHub/Vercel/Render config, CI | Done (deploy itself is manual per user instruction) | `render.yaml`, `apps/web/vercel.json`, `.github/workflows/ci.yml`, `apps/api/Dockerfile` |
| §17 Tests | 38 backend tests + 3 inference tests + benchmark runner | `apps/api/tests`, `tests/e2e` |
| Reports (PDF/JSON/CSV with disclaimer) | Done | `app/reports` |

## Build order followed

1. Credit preflight → 2. models/auth/migrations → 3. parsers + ingestion → 4. graph engine + rules → 5. connectors → 6. synthetic factory + sealed store → 7. reports + routers → 8. tests → 9. ML training → 10. benchmark → 11. frontend → 12. deploy config + docs.

## Deployment (2026-11-21)

- GitHub: https://github.com/RAJARYANSINGH0059/RPH (`main`)
- Render API: https://ps05x-api.onrender.com (service `srv-dc0noo67bikc73bbqjug`, Postgres `ps05x-db`), deployed via `scripts/render_deploy.py`; health checks 200.
- Vercel web: https://ps05x-web.vercel.app (project `ps05x-web`), deployed via `vercel deploy --prod` after upgrading Next.js to 15.5.x (Vercel refuses 15.1.x as vulnerable).

## Access blockers

- The folder initially sat inside a stray, commit-less git repository rooted at the user's home directory (`C:/Users/rajar/.git`). A dedicated repository was initialised in the project folder on `main` so that only project files are tracked; the stray home-directory repository was left untouched for the user to remove.

- Vercel CLI present but not authenticated; no `gh`, `render`, `docker`, `psql`. Per the user's instruction, push and deployment are manual.
- No Tesseract binary → OCR fallback inactive (flagged, not silent).
- Official PS05 expanded brief/sample data not re-checked in a browser during this run (blueprint §2.1 still applies).
