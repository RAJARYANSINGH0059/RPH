# UI/UX redesign — "Rajasthan cyber investigation operations room" (light mode)

## Design direction

A calm, premium investigative workstation: a midnight-navy navigation rail with a faint jaali dot texture, a warm sandstone canvas with a very light coordinate grid, ivory cards and pale blue-grey panels, peacock-teal primary actions, restrained terracotta for synthetic-data labelling and saffron only as a highlight. No official insignia; the product is labelled **PS05-X · Investigative prototype**. All disclaimers (`Synthetic demo`, `Uploaded evidence`, `No live police/bank connection`, `Human verification required`) stay visible in the top context bar of every page.

## Tokens (`apps/web/app/globals.css`)

| Token | Value | Use |
|---|---|---|
| `--canvas` | `#F1EEE7` | application background (with 28 px grid at 3.5 % ink) |
| `--card` | `#FBFAF6` | primary cards |
| `--panel` | `#E9EEF2` | secondary panels, table headers |
| `--rail` / `--rail-2` | `#17283A` / `#1F3448` | navigation rail |
| `--ink` / `--slate` | `#172536` / `#647386` | text / secondary text |
| `--accent` / `--accent-deep` / `--accent-soft` | `#147D83` / `#0F6368` / `#E1EFEF` | primary actions, links, directly-observed level |
| `--terracotta` | `#B66A4D` | synthetic-data badge, stale level |
| `--saffron` | `#C58A36` | active nav icon, candidate level, warnings |
| `--ok` / `--warn` / `--danger` | `#1E6B4F` / `#8A5A0F` / `#9B3B3B` | status |
| `--line` / `--line-strong` | `#DED8CC` / `#C9C1B2` | borders |

Evidence-level classes `lvl-directly_observed … lvl-insufficient` are defined once and used by `LevelBadge` everywhere (graph, tables, cross-case, reports). Tabular numerals are enabled globally; `.mono` is used only for identifiers, hashes, references, IPs and technical values. Transitions are 150 ms and disabled under `prefers-reduced-motion`.

## Shell (`components/Shell.tsx`)

Dark rail with icon navigation (max six items), a per-case tool block (overview, transactions, related cases, victim claims, cooperation pack), quick tour and sign-out; a sticky top bar with breadcrumb and environment pills; page header with title, purpose line and primary actions; the investigation stepper on case pages; Help drawer per page (`lib/guide.ts`); first-visit walkthrough; collapsible navigation under 768 px; skeleton loading, error-with-retry and empty states (`State`); `Copyable` for long hashes.

## Pages changed

Sign-in (split layout, readiness indicator with retry, no passwords shown), Cases (registry cards, search, one-click demo), Case overview (suggested next step, stat cards, file table, shortcuts), Synthetic Case Factory (chip controls with explanations, honest progress state, ingestion table), Upload (drop zone, parser warnings explained, mapping editor, **OCR preview with engine, confidence and “needs human verification”**), Transactions (ledger with raw strings, path chips, triage), Investigation graph (focus presets, lanes/force, grid canvas, search, needs-decision table, evidence panel), Timeline (grouped by day), Reports (observed / derived / hypotheses / unresolved), Data sources (connector registry cards with exact statuses), Guide.

New pages: `/crosscase` and `/cases/[id]/crosscase` (correlation with provenance drill-down and “not asserted” list, accessible table), `/cases/[id]/claims` (claimed / traced / held / restored / unresolved, competing and duplicate flags, evidence-backed funds records, approval states, pack export), `/cases/[id]/cooperation` (field wizard with validation, attachment checklist, supervisor endorsement, ZIP export).

## Functions explicitly preserved

Authentication and roles, case access checks, upload and column remapping, parser previews, graph filters/selection/evidence panel/review, timeline filters, PDF/JSON/CSV exports, connector statuses, synthetic generation, all disclaimers.

## Accessibility and responsiveness

Semantic landmarks, labelled controls, `aria-current` on navigation and steps, visible focus rings, keyboard-selectable table rows for edges and correlation links, skip link, the graph always mirrored by a table, 16 px gutters, no horizontal page scroll (tables scroll in their own region), collapsible rail under 768 px, optimised for 1366×768 and 1440×900.

## Commands run and results

- `npx tsc --noEmit` — clean
- `npx next lint` — clean
- `npx next build` — see COMPETITION_READINESS_REPORT.md for the final run
- Backend: `python -m pytest -q` — 58 passed (after the gap-closure backend work)

## Screens inspected

Recorded in COMPETITION_READINESS_REPORT.md with viewport sizes and findings.

## Remaining UI limitations

- The Cytoscape canvas is not screen-reader accessible; the tables beside it carry the same relationships.
- Hindi labels were not added in this pass (English-only UI; the OCR engine can read Hindi only when Tesseract with `hin` data is installed via the Dockerfile).
- Free-plan API sleep latency shows as a longer first load; the sign-in page surfaces readiness explicitly.
