# Remaining blockers and deferred work (updated 2026-11-22)

| Item | Status | What is needed |
|---|---|---|
| OCR on Render free plan | **Disabled on the live service** (`OCR_ENGINE=off`): the first OCR request on the 512 MiB free instance was OOM-killed (Render event `server_failed`, `oomKilled`). OCR is verified locally (RapidOCR) and in tests; Tesseract eng+hin is installed by `apps/api/Dockerfile`. | Upgrade the instance to >=1 GB and set `OCR_ENGINE=auto`, or run the Docker image on a paid plan. Scanned pages/images are still stored, hashed and flagged for manual review. |
| Durable evidence storage on Render | Adapter implemented and tested locally against the local backend; **not exercised against a real bucket** in this run. | Create a private R2/S3 bucket, set `STORAGE_BACKEND=s3` and the `S3_*` secrets on Render, redeploy, then run the storage round-trip from `/api/health/live` and an upload. |
| PostgreSQL migration test on Postgres | Verified on SQLite locally and by the GitHub Actions job on PostgreSQL 16 for the previous migration; the new migration `7e960fbc555c` runs on Render at start (`alembic upgrade head`). | Watch the first Render deploy log of this branch. |
| Benchmark size | Smoke (4 seeds, 96 cases/config) and a frozen held-out range (seeds 700–703, `fake_customer_care` reported as held-out). Not 600 cases/config. | Run `python tests/benchmark/run_benchmark.py --seeds 25 --seed-start 1000` (~10 min) when runtime allows. |
| Path recall under noise | Algorithm v2 adds explicit unresolved hops, split/merge flags, alternatives and new metrics; recall is still limited by ambiguous dates and absent second-layer statements by design. | Column-level date-format inference per statement (dd/mm vs mm/dd majority vote) is the next deterministic improvement. |
| PS01-compatible scam-artifact intake (P2) | Deferred. Documents, screenshots and text already flow through the indicator extractor; APK static inspection is not implemented. | Separate increment. |
| Hindi UI labels | Deferred. | Separate increment; technical evidence fields stay English. |
| Official PS05 expanded brief / sample data | Not re-checked in a browser in this run. | Manual check before the action-plan submission. |
| Cooperation request process | Pack fields follow the publicly described form; the `/old/` portal page was not re-verified as current. | Verify the current official process; the pack remains a manual handoff. |
| Deployment protection on Vercel preview URLs | Deployment-specific URLs are SSO-protected; the production alias is public. | None (expected behaviour). |

## Digital-twin increment (2026-11-22)

| Item | Status | What is needed |
|---|---|---|
| Proof manifest HMAC on the live API | Hash-only on Render (no `PROOF_SIGNING_KEY` set) | Set the key in Render env; manifests then carry `hmac_sha256` and the verifier accepts `--key`. |
| Keyed-token privacy matching on the live API | Disabled (no `CROSSCASE_TOKEN_KEY`) | Set a server key; the feature is intentionally off without one. |
| Automated UI interaction tests (graph workbench, walkthrough, motion) | Not written; typecheck/lint/build and manual browser checks only | Playwright smoke over the Desert Mirage pages. |
| Second tabular parser for field-level extraction disagreement | Not implemented | A second independent CSV/XLSX mapping pass to compare against the first. |
| Benchmark v2 size | 5 families × 6 seeds (30 cases) | `--seeds 25` run when runtime allows; results JSON is committed for the 6-seed run. |
| Demo rate limiting across workers | In-process limiter | Shared store (Redis/Postgres) if the API ever runs multi-worker. |
| STIX/TAXII export, geospatial view, APK intake, Hindi UI labels | Not implemented | Separate increments; the geospatial view is deliberately excluded while the only candidate source is IP geolocation. |
