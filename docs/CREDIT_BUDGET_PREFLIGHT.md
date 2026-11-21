# Credit / Usage Budget Preflight

**Timestamp:** 2026-11-21 (session start, IST afternoon)

## Observed usage indicator

The Claude desktop app exposes an official plan-usage panel (read via the session usage tool). Values below are the **official UI units (percent of plan window used)**, not token-derived estimates.

| Window | Observed | Resets |
|---|---|---|
| 5-hour limit | 2% used | ~4h 54m |
| Weekly, all models | 14% used | ~4d 6h |
| Weekly, Fable | 2% used | ~4d 6h |
| Extra usage | disabled | — |

Context window at preflight: ~120k of 1,000k tokens (12%). Context capacity, account allowance and tokens already spent are separate quantities and are not interchangeable.

**Note on the user-reported figure.** The user reported "approximately 13% remaining". The official panel shows **14% used** of the weekly all-models window (i.e. ~86% remaining) and 2% used of the Fable-specific window. The official reading is used as the planning baseline. The user-reported number is recorded here but superseded by the observed indicator.

## Estimation basis

Qualitative task-size estimation, expressed as percentage points of the weekly all-models window, derived from the panel's unit. No token-to-percent conversion rate is invented; the ranges below are judgement estimates with **low confidence**.

## Work-package forecast

| Work package | Low | Likely | High | Priority |
|---|---|---|---|---|
| Usage/repository preflight | <1 | <1 | 1 | P0 |
| Core end-to-end vertical slice (API models, auth, migrations, case/upload/graph/report) | 3 | 5 | 8 | P0 |
| File ingestion + synthetic case factory | 2 | 4 | 6 | P0 |
| Evidence graph + provenance + temporal safeguards | 1 | 2 | 4 | P0 |
| Smoke tests + targeted repair (≤2 cycles/phase) | 2 | 3 | 6 | P0 |
| Frontend (Next.js screens, build) | 3 | 5 | 8 | P0 |
| Local git commit (push is manual by user) | <1 | <1 | <1 | P1 |
| Vercel + Render config and docs (deploy is manual by user) | <1 | 1 | 2 | P1 |
| Lightweight ML triage model + model card | 1 | 2 | 3 | P2 |
| Optional connectors (RDAP/DNS/URLhaus/ThreatFox/MISP interface) | 1 | 1 | 2 | P2 |
| **Total** | **~14** | **~24** | **~40** | |

## Projected ending balance (weekly all-models window)

| Scenario | Projected used after this run | Remaining |
|---|---|---|
| Low | ~28% | ~72% |
| Likely | ~38% | ~62% |
| High | ~54% | ~46% |

Fable-specific window has far more headroom (2% used) and is not the binding constraint. The 5-hour window may become binding during long build/test loops; if so, work resumes after reset without loss of repository state.

## Decision

Likely and high scenarios fit comfortably with contingency. **Execute full planned scope**, with these credit-efficient rules: blueprint read once; repo inspected once; small targeted edits; one smoke benchmark first; max two repair cycles per phase; no large model downloads; no paid APIs.

## Scope adjustments from user instruction

The user instructed (mid-session): build and save everything in this folder, deployment-ready for GitHub, Vercel and Render; **the user will push and deploy manually**. Therefore GitHub push, Vercel deploy and Render deploy are **out of scope for this run**. Local git commits are in scope. No live URLs will be reported.

## Deferred if the high estimate materialises

1. Expanded 100+ case benchmark (keep smoke benchmark across several seeds).
2. OCR engine integration beyond a guarded fallback (Tesseract binary not installed on this machine).
3. Screenshot generation for OCR testing (kept simple).
4. Additional scenario families beyond the six required.

## Assumptions

- Python 3.12, Node 24, Vercel CLI present but **not authenticated**; no `gh`, `docker`, `psql`, `render` CLI available.
- Tests run against SQLite locally; PostgreSQL is used in production via the same SQLAlchemy models and Alembic migrations.

---

# Addendum: gap-closure run (2026-11-21, later the same day)

Prior sections are preserved as dated history. Official panel readings at the start of this run (plan units, not token estimates):

| Window | Observed |
|---|---|
| 5-hour limit | 49% used, resets in ~3h 20m |
| Weekly, all models | 20% used |
| Weekly, Fable | 13% used |

The earlier user-reported "~13% remaining" is historical and superseded by these readings. The binding constraint is now the 5-hour window; if it is exhausted the session pauses until reset without loss of repository state.

Estimate basis: qualitative, in weekly-window percentage points, low confidence.

| Phase | Low | Expected | High |
|---|---|---|---|
| Repo reconciliation + docs | <1 | 1 | 1 |
| Cross-case correlation (service, API, UI, tests) | 2 | 3 | 5 |
| OCR engine path + fixtures + Docker | 1 | 2 | 3 |
| Path reconstruction + benchmark metrics | 1 | 2 | 4 |
| Victim claims + cooperation pack + migration + tests | 2 | 3 | 5 |
| S3 storage adapter + health | <1 | 1 | 2 |
| Premium UI redesign + new screens + screenshots | 3 | 5 | 8 |
| Tests/CI/benchmark/repair | 1 | 2 | 4 |
| Branch, PR, Render/Vercel redeploy and verification | <1 | 1 | 2 |
| **Total** | **~12** | **~20** | **~34** |

Projected weekly usage after this run: ~32% (low), ~40% (expected), ~54% (high). Scope: execute P0 and P1 fully; P2 scam-artifact intake is deferred unless budget clearly remains. Bounded repair: two cycles per phase.
