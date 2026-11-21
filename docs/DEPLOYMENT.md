# Deployment: GitHub → Render (API + Postgres) → Vercel (web)

Two ways: **from your terminal** (what this repository's scripts do) or through the dashboards. Both use the same configuration files.

## A. From the terminal (Windows PowerShell)

Prerequisites once per machine: Git with Credential Manager, Node 20+, Python 3.12, `npm i -g vercel`, `winget install Render.CLI`.

### 1. Push

```powershell
git push origin main
```

### 2. Render: Postgres + API

```powershell
render login
```
```powershell
python scripts/render_deploy.py
```

`scripts/render_deploy.py` uses the Render REST API with the key stored by `render login` (or `RENDER_API_KEY`). It is idempotent:

- creates `rph-db` (PostgreSQL 16, free plan, Singapore) if missing and waits until it is available;
- generates `JWT_SECRET` and three demo passwords once and stores them in `DEPLOY_SECRETS.local.md` (gitignored, never printed);
- creates the `rph` web service from `https://github.com/RAJARYANSINGH0059/RPH` (root `apps/api`, build `pip install -r requirements.txt`, start `alembic upgrade head && uvicorn …`, health `/api/health/live`, auto-deploy on push) or, if it exists, updates its environment and triggers a deploy;
- waits for the deploy to go live and prints the `/api/health/live` and `/api/health/ready` results.

Re-run it any time to rotate nothing and redeploy; delete `DEPLOY_SECRETS.local.md` first if you want fresh secrets.

### 3. Vercel: frontend

```powershell
cd apps/web; vercel login
```
```powershell
cd apps/web; vercel link --yes --project rph
```
```powershell
cd apps/web; "https://ps05x-api.onrender.com" | vercel env add NEXT_PUBLIC_API_BASE_URL production
```
```powershell
cd apps/web; vercel deploy --prod --yes
```

The web app's BFF routes (`/api/session/*`, `/api/proxy/*`) call the API server-side using `API_BASE_URL` (falls back to `NEXT_PUBLIC_API_BASE_URL`); the browser only ever holds an HttpOnly cookie. Direct uploads/downloads use the public base with 10-minute scoped tokens. The demo-session endpoint checks the `Origin` header against `CORS_ORIGINS`/`CORS_ORIGIN_REGEX`, so the Vercel origin must be covered by one of them.

The API allows any `https://*.vercel.app` origin through `CORS_ORIGIN_REGEX`, so production and preview deployments work without editing the API after each Vercel deploy. For a custom domain add it to `CORS_ORIGINS` on Render.

If you later connect the Vercel project to the GitHub repo for automatic deploys, set **Root Directory = `apps/web`** in the Vercel project settings.

## B. From the dashboards

- Render → New → Blueprint → select the repo; `render.yaml` defines the service and database. Set `DEMO_*_PASSWORD` values in the service environment.
- Vercel → Add New Project → import the repo → Root Directory `apps/web` → env `NEXT_PUBLIC_API_BASE_URL` = the Render URL.

## Migrations in this increment

`2222d8017e5e_digital_twin_tables_and_demo_users` adds nine tables (investigation_events, payment_instructions, hypotheses, independent_reviews, evidence_requests, role_reviews, analysis_branches, analysis_runs, candidate_rules), `users.is_demo` / `users.expires_at`, and on PostgreSQL extends the `role` enum with `demo_analyst`. It runs from the Render start command (`alembic upgrade head`). Rollback: `alembic downgrade 7e960fbc555c` drops the nine tables and the two columns after deleting demo users (the enum value stays; PostgreSQL cannot drop enum values in place). Back up the database before downgrading. Locally, a SQLite database created by `create_all` before this increment has no Alembic stamp: either run `alembic stamp 7e960fbc555c` then `alembic upgrade head`, or move the old file aside (the local DB is disposable; synthetic cases regenerate). `requirements.txt` gained `qrcode==8.0`.

Optional keyed features: `PROOF_SIGNING_KEY` (+ `PROOF_SIGNING_KEY_VERSION`) adds an HMAC to proof manifests; `CROSSCASE_TOKEN_KEY` enables keyed-token privacy matching. Both are off when unset and the UI says so. Never commit them.

## Post-deploy acceptance checklist

- [ ] `/api/health/live` and `/api/health/ready` → 200
- [ ] Press **SIGN IN** on the landing page → demo workspace opens (cookie `ps05x_session`, no token in localStorage)
- [ ] Staff sign-in at `/staff/login` with a demo account (credentials in `DEPLOY_SECRETS.local.md` on the machine that deployed)
- [ ] Synthetic Case Factory → generate (seed 42, messy, small) → files parsed
- [ ] Upload the generated CSV again into a new case → same SHA-256 and parse stats
- [ ] Graph loads; click a SHARED_INFRASTRUCTURE edge → counter-evidence visible
- [ ] Timeline shows ambiguous-date badges
- [ ] Download PDF and JSON report
- [ ] Restart the API service → cases still listed (Postgres persistence)
- [ ] `/api/connectors/status` shows `not_configured` for unset providers
- [ ] Desert Mirage case: Twin, Payment Bridge, Bounded Fund Provenance, CounterProof, Lifecycle, Roles, IVOI, Resilience, Intervention, Challenge render; `proof.json` downloads and `scripts/verify_proof.py` passes against the downloaded originals
- [ ] `GET /api/synthetic/cases/{id}/challenge/reveal` is refused before a submission

## Names and URLs

Render project **RPH** → service `rph` (URL stays `https://ps05x-api.onrender.com`; Render keeps the original subdomain after a rename) and database `rph-db`. Vercel project **rph** → `https://rph-ps05x.vercel.app` and `https://ps05x-web.vercel.app` (`rph.vercel.app` belongs to another team). Any `*.vercel.app` origin is allowed by the API's CORS regex.

## Notes and limits

- OCR: keep `OCR_ENGINE=off` on 512 MiB instances (the OCR runtime triggers an OOM kill). On >=1 GB set `OCR_ENGINE=auto`; the Docker image adds Tesseract with English and Hindi.
- Durable storage: set `STORAGE_BACKEND=s3` plus `S3_*` secrets (R2/S3/MinIO) for evidence that must survive redeploys; `/api/health/live` reports the active backend.

- Free-plan web services sleep after inactivity; the first request after a pause takes 30–60 s. Free Postgres expires after 90 days unless upgraded.
- Uploaded files live on the service's ephemeral disk; synthetic cases regenerate on demand. Attach a Render disk at `STORAGE_DIR` or implement the S3 adapter in `services/storage.py` for durable evidence storage.
- Migrations run in the start command because free-plan services have no pre-deploy hook.

## Local development

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1
```

Requires `apps/api/.env` (copy `.env.example`, set `DEMO_*_PASSWORD`) and `apps/web/.env.local` with `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` (and optionally `API_BASE_URL`). SQLite runs in WAL mode with a 30 s busy timeout so the dashboard's parallel reads do not lock uploads.
