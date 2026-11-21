# Deployment: GitHub → Render (API + Postgres) → Vercel (web)

Everything below is configured in the repository. No deployment was performed from this build; the steps are manual.

## 0. Push to GitHub

```powershell
git remote add origin https://github.com/<you>/<repo>.git
```
```powershell
git push -u origin main
```

CI (`.github/workflows/ci.yml`) runs backend tests, a PostgreSQL migration up/down, a 2-seed smoke benchmark, the model inference test, frontend lint/typecheck/build and gitleaks secret scanning.

## 1. Render: API + PostgreSQL (Blueprint)

1. Render dashboard → **New → Blueprint** → select the repo. `render.yaml` defines `ps05x-api` (Python web service, root `apps/api`) and `ps05x-db` (Postgres, free plan).
2. Set the `sync: false` variables in the service's Environment tab:
   - `CORS_ORIGINS` = your Vercel URL (e.g. `https://ps05x.vercel.app`), comma-separated if several.
   - `DEMO_ANALYST_PASSWORD`, `DEMO_SUPERVISOR_PASSWORD`, `DEMO_ADMIN_PASSWORD` (strong values; blank = account not created).
   - Optional: `ENABLE_RDAP=true`, `ENABLE_DNS=true`, `URLHAUS_AUTH_KEY`, `THREATFOX_AUTH_KEY`, `MISP_URL`, `MISP_KEY`.
3. `DATABASE_URL` is injected from the database; `JWT_SECRET` is generated. The pre-deploy command runs `alembic upgrade head`.
   - If Render's connection string starts with `postgres://`, SQLAlchemy 2 needs `postgresql+psycopg://`. Render's `connectionString` is `postgresql://…`, which SQLAlchemy accepts with the psycopg driver only if the URL says `postgresql+psycopg://`. **Set `DATABASE_URL` manually to the Internal Database URL with the scheme changed to `postgresql+psycopg://`** if the first deploy logs a driver error.
4. Verify: `https://<service>.onrender.com/api/health/live` and `/api/health/ready` return 200; `/docs` shows the OpenAPI UI.

Alternative: the `apps/api/Dockerfile` builds a production image (migrations run at container start).

Durable uploads: the free plan's filesystem is ephemeral. Synthetic demo cases regenerate on demand; for uploaded evidence attach a Render disk at `STORAGE_DIR` or implement the S3 adapter in `services/storage.py`.

## 2. Vercel: frontend

1. Vercel → **Add New Project** → import the repo → **Root Directory = `apps/web`** (framework auto-detected: Next.js).
2. Environment variable: `NEXT_PUBLIC_API_BASE_URL` = `https://<service>.onrender.com` (no trailing slash).
3. Deploy. Then add the Vercel URL to `CORS_ORIGINS` on Render and redeploy the API.

## 3. Post-deploy acceptance checklist

- [ ] `/api/health/live` and `/api/health/ready` → 200
- [ ] Sign in with a demo account
- [ ] Synthetic Case Factory → generate (seed 42, messy, small) → 6 files parsed
- [ ] Upload the generated CSV again into a new case → same SHA-256 and parse stats
- [ ] Graph loads; click a SHARED_INFRASTRUCTURE edge → counter-evidence visible
- [ ] Timeline shows ambiguous-date badges
- [ ] Download PDF and JSON report
- [ ] Restart the API service → cases still listed (Postgres persistence)
- [ ] `/api/connectors/status` shows `not_configured` for unset providers (never `live` without credentials)

## 4. Local development

```powershell
cd apps/api; pip install -r requirements.txt; copy ..\..\.env.example .env; python -m uvicorn app.main:app --reload --port 8000
```
```powershell
cd apps/web; npm install; npm run dev
```

Set `DEMO_ANALYST_PASSWORD` (and others) in `apps/api/.env` before starting the API; SQLite is used automatically and tables are created at startup.
