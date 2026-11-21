# Benchmark summary

All metrics are measured on **synthetic, sealed-truth cases**. F1 is not accuracy. No real-world transfer is claimed.

## Smoke run (development seeds)

**Command:** `python tests/benchmark/run_benchmark.py --seeds 4 --size small`
**Run:** 2026-11-21 · generator 0.3.0 · path algorithm 2.0.0 · seeds 500–503 · 6 scenario families × 4 difficulties × 4 configurations = **384 runs, 96 cases per configuration** · wall 197 s · same-seed reproducibility: **true** · OCR disabled for the run (OCR has its own tests).
**Raw results:** `tests/benchmark/results/benchmark_summary.json` (summary + per-case rows).

Every case is generated, sealed, ingested through the public upload pipeline and only then scored against the sealed truth.

| Metric | A rules only | B financial graph | C combined, no safeguards | **D PS05-X full** |
|---|---|---|---|---|
| Field extraction F1 (exact reference + amount, observable rows) | 1.000 | 1.000 | 1.000 | **1.000** |
| Transaction edge F1 (money edges vs observable true hops) | 0.550 | 0.550 | 0.550 | **0.550** |
| Entity resolution F1 (VPA↔account bridges) | 0.993 | 0.993 | 0.993 | **0.993** |
| Similar names wrongly merged (total) | 0 | 0 | 0 | **0** |
| False links (campaign↔decoy asserted as common operator), total | 0 (no infra) | 0 (no infra) | **144** | **0** |
| Shared-IP false-link rate | n/a | n/a | 0.75 | **0.00** |
| Temporal validity accuracy (planted stale DNS marked stale) | n/a | n/a | 1.00 | **1.00** |
| Evidence coverage (edges with locator or explicit candidate) | 1.00 | 1.00 | 1.00 | **1.00** |
| Counter-evidence recall (planted chaos surfaced) | 0.632 | 0.632 | 0.632 | **0.871** |
| Rules triage F1 (mule-pattern accounts) | 0.505 | 0.505 | 0.505 | 0.505 |

A, B and D share the financial pipeline, so financial metrics coincide by construction; C and D differ in the infrastructure layer.

### Path-level metrics (algorithm v2, configuration D, mean with bootstrap 95% CI)

| Metric | Definition | Mean | 95% CI |
|---|---|---|---|
| Coverage | share of true chains (observable prefix) fully contained in a reconstructed path | **0.977** | 0.956–0.995 |
| False-path rate | share of multi-hop reconstructed chains containing an edge that is not a true scam hop | 0.227 | 0.193–0.266 |
| Amount conservation | mean exit/entry ratio of multi-hop chains (capped at 1) | 0.728 | 0.696–0.758 |
| Temporal consistency | share of multi-hop chains with monotone, non-ambiguous times | 0.879 | 0.835–0.917 |
| Unresolved-hop rate | share of multi-hop chains ending at a non-exit account whose statement is absent | **1.000** | 1.000–1.000 |
| Runtime | path reconstruction per case (s) | 0.012 | 0.011–0.013 |

**Reading these honestly.** The unresolved-hop rate is 1.0 **by construction of the bundles**: only victims' and first-layer statements are generated, so every reconstructed chain genuinely stops at an account whose statement is missing. v2 now says so explicitly in the UI ("No statement for X is in the case; obtain the statement of X"). It does not invent the continuation. False paths arise mostly from legitimate background payments that chain in time behind a scam transfer in messy/adversarial cases; they are shown as `observed` hops with split/merge flags, never as conclusions.

### Robustness by difficulty (configuration D)

| Difficulty | Edge F1 | Coverage | False-path rate | Conservation | Temporal consistency | Counter-evidence recall |
|---|---|---|---|---|---|---|
| clean | 0.846 | 1.000 | 0.027 | 0.765 | 1.000 | 1.000 |
| messy | 0.495 | 1.000 | 0.284 | 0.700 | 0.855 | 0.889 |
| high_noise | 0.429 | 0.969 | 0.238 | 0.761 | 0.827 | 0.799 |
| adversarial | 0.432 | 0.938 | 0.357 | 0.686 | 0.833 | 0.798 |

Edge F1 drops with noise because ambiguous dd/mm dates break time ordering and OCR-style substitutions break identifier matching; coverage stays high because the first two hops remain observable in the victims' and first-layer statements.

## Frozen held-out run

**Command:** `python tests/benchmark/run_benchmark.py --seeds 4 --seed-start 700 --heldout-scenario fake_customer_care --out tests/benchmark/results/heldout_summary.json`
Seeds 700–703 were never used while developing or inspecting the algorithm; `fake_customer_care` is reported separately as the held-out typology. 384 runs. Results: `tests/benchmark/results/heldout_summary.json`.

| Metric (configuration D) | Held-out | Smoke (for comparison) |
|---|---|---|
| Transaction edge F1 | 0.551 | 0.550 |
| Entity resolution F1 | 0.992 | 0.993 |
| False links from shared hosting | 0 (C: 144) | 0 (C: 144) |
| Counter-evidence recall | 0.851 | 0.871 |
| Coverage (95% CI) | 0.958 (0.932–0.979) | 0.977 (0.956–0.995) |
| False-path rate (95% CI) | 0.220 (0.179–0.267) | 0.227 (0.193–0.266) |
| Amount conservation | 0.722 | 0.728 |
| Temporal consistency | 0.853 | 0.879 |
| Unresolved-hop rate | 1.000 | 1.000 |
| Held-out typology `fake_customer_care` edge F1 | 0.539 (others 0.524–0.577) | — |

Held-out figures sit within the smoke intervals, so no tuning leakage is apparent.

## Related evaluations

- ML triage model (held-out scenarios, scenario-level split): F1 0.789 vs rules 0.503 — `docs/MODEL_CARD.md`.
- OCR: fixture tests (text-layer PDF, scanned PDF, screenshot, rotated/noisy scan, engine absent) — `apps/api/tests/test_ocr_and_storage.py`.
- Cross-case correlation: true bridge found, decoy rejected, shared CDN candidate-only, stale respected, IDOR, revocation, reproducibility — `apps/api/tests/test_crosscase.py`.

Expand with `--seeds 25 --seed-start 1000` (≈12 minutes) for 600 cases per configuration.
