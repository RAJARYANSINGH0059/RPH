# Repository gap reconciliation (2026-11-21, gap-closure run)

Delta against `RPH_REPOSITORY_AUDIT_AND_COMPETITION_ROADMAP.md` (audit of the same day, commit `ee0fd9e`).

## State at the start of this run

| Item | Audit said | Now |
|---|---|---|
| `main` | `ee0fd9e`, CI green | `6bf3d7c`, CI green ([run 44899132454](https://github.com/RAJARYANSINGH0059/RPH/actions/runs/44899132454)); working tree clean |
| Frontend | Next.js 15.1 | Next.js **15.5.29** (Vercel refused 15.1 as vulnerable); guided UI with help drawer, stepper, lane graph, `/guide` |
| Live deployment | "configuration present; not verified" | **Deployed and verified**: API https://ps05x-api.onrender.com (Render, Singapore, Postgres `ps05x-db`), web https://ps05x-web.vercel.app; health 200, sign-in / synthetic case / graph / PDF exercised against the live API from the terminal |
| Deploy tooling | manual | `scripts/render_deploy.py` (Render REST API, idempotent), Vercel CLI linked project `ps05x-web`; both CLIs authenticated on the user's PC |
| DB URL / CORS | — | `postgres://` normalised to `postgresql+psycopg://`; `CORS_ORIGIN_REGEX` for `*.vercel.app` |
| OCR | guarded Tesseract path, binary absent | Still absent locally and on Render native runtime at run start → addressed in this run (P0-B) |
| Cross-case correlation | missing | missing at run start → P0-A in this run |
| Path reconstruction | F1 0.55 overall, 0.43 adversarial | unchanged at run start (benchmark re-run reproduced identical numbers) → P0-C |
| Victim claims / cooperation pack / S3 storage | missing | missing at run start → P1 |
| Benchmark | 96 cases/config | unchanged at run start |
| ML artefact | RF, checksum | unchanged; checksum test passes |
| Durable storage | local filesystem | unchanged at run start (uploads on Render are ephemeral) → P1-C |

## Confirmed still true

- Sealed ground truth isolated from case APIs (tests pass).
- Shared IP/CDN only ever yields candidate `SHARED_INFRASTRUCTURE` with counter-evidence.
- Similar names never merge.
- 38 backend tests, 3 inference tests, ruff, ESLint, tsc all pass on `6bf3d7c`.

## Not re-verified in this run

- The expanded official PS05 brief and sample data on the hackathon site (manual check still required before submission).
- Whether the `/old/` Rajasthan Police cooperation-request page is the current official process; the cooperation pack is a manual handoff only.
