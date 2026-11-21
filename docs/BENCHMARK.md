# Benchmark summary (smoke run)

**Command:** `python tests/benchmark/run_benchmark.py --seeds 4 --size small`
**Run:** 2026-11-21 · generator 0.3.0 · seeds 500–503 · 6 scenario families × 4 difficulties × 4 configurations = **384 runs, 96 cases per configuration** · wall time 91 s · same-seed reproducibility: **true**
**Raw results:** `tests/benchmark/results/benchmark_summary.json` (summary + per-case rows)

Every case is generated, sealed, and ingested through the public upload pipeline; scoring uses the sealed truth only after ingestion. Metrics are means over the 96 cases unless stated.

| Metric | A rules only | B financial graph | C combined, no safeguards | **D PS05-X full** |
|---|---|---|---|---|
| Field extraction F1 (exact reference + amount, observable rows) | 1.000 | 1.000 | 1.000 | **1.000** |
| Transaction path F1 (money edges vs observable true hops) | 0.550 | 0.550 | 0.550 | **0.550** |
| Entity resolution F1 (VPA↔account bridges) | 0.993 | 0.993 | 0.993 | **0.993** |
| Similar names wrongly merged (total) | 0 | 0 | 0 | **0** |
| False links (campaign↔decoy asserted as common operator), total | 0 (no infra) | 0 (no infra) | **144** | **0** |
| Shared-IP false-link rate | n/a | n/a | 0.75 | **0.00** |
| Temporal validity accuracy (planted stale DNS marked stale) | n/a | n/a | 1.00 | **1.00** |
| Evidence coverage (edges with locator or explicit candidate) | 1.00 | 1.00 | 1.00 | **1.00** |
| Counter-evidence recall (planted chaos surfaced) | 0.632 | 0.632 | 0.632 | **0.871** |
| Rules triage F1 (mule-pattern accounts) | 0.505 | 0.505 | 0.505 | 0.505 |
| Ingest + analysis latency per case (s) | 0.18 | 0.18 | 0.18 | 0.18 |

Configurations A, B and D share the financial pipeline, so financial metrics coincide by construction; the differences are in the infrastructure layer (C vs D).

## Robustness by difficulty (configuration D)

| Difficulty | Field extraction | Transaction path F1 | False links | Temporal validity | Counter-evidence recall |
|---|---|---|---|---|---|
| clean | 1.000 | 0.846 | 0 | 1.00 | 1.000 |
| messy | 1.000 | 0.495 | 0 | 1.00 | 0.889 |
| high_noise | 1.000 | 0.429 | 0 | 1.00 | 0.799 |
| adversarial | 1.000 | 0.432 | 0 | 1.00 | 0.798 |

## Reading the numbers honestly

- **Path F1 drops sharply with noise.** Ambiguous dd/mm dates break time ordering, OCR-substituted counterparties break identifier matching, and second-layer/exit accounts have no statement of their own. These are real failure modes the UI surfaces as warnings; they are not hidden by the metric.
- **Field extraction = 1.0** is set-based (reference, amount) recovery on rows that exist in a supplied statement; it does not measure name or date correctness. Date ambiguity is measured separately through the path metric and the `ambiguous_dates` parser statistic.
- **Entity resolution** counts SAME_ACCOUNT_IDENTIFIER bridges only; the one missed bridge per ~100 cases comes from an OCR-substituted VPA.
- **Counter-evidence recall < 1** in noisy cases: the duplicate-row rule only fires when the reference is intact, and similar-name counter-evidence needs both names present.
- The ML triage model (docs/MODEL_CARD.md) is evaluated separately on held-out scenarios: F1 0.789 vs rules 0.503.
- 96 cases per configuration is a smoke run; expand with `--seeds 25` (≈10 minutes) for 600 cases per configuration.
