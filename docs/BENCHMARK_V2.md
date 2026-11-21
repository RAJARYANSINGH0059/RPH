# Benchmark v2 — next-wave metrics (synthetic, sealed truth)

Command: `python tests/benchmark/run_benchmark_v2.py --seeds 6 --seed-start 1500` (five scenario families × six seeds = 30 cases; generator 0.4.1; results in `tests/benchmark/results/benchmark_v2_summary.json`, 27 s on a laptop, 0 scoring errors). Every case is generated with sealed truth, pushed through the public upload pipeline, analysed, and only then scored by the runner. None of these numbers is a real-world accuracy claim: the generator and the detectors share assumptions, so perfect scores show internal consistency.

Sample size is small and deterministic; every metric carries a bootstrap 95% CI and min/max in the results file, and `n` is the number of cases where the metric applies.

## Detection, attribution and integrity

| Metric | Definition | Mean | 95% CI | Min–max | n |
|---|---|---|---|---|---|
| pi_recall / pi_precision | decoded payment instructions vs sealed `payment_instructions` | 1.00 / 1.00 | — | — | 18 |
| pi_match_precision | instruction→transaction links that are EXACT and correct | 0.944 | 0.86–1.00 | 0.50–1.00 | 18 |
| attribution_coverage | sealed simulated allocation lies inside [min, max] of the bounded-flow hop | 1.00 | 1.00–1.00 | 1.00 | 10 |
| attribution_width_ratio | mean (max − min) / observed transfer (1.0 = uninformative) | 0.62 | 0.44–0.83 | 0.29–1.00 | 10 |
| attribution_false_exact_rate | hops reported exact whose truth differs | 0.00 | — | — | 10 |
| gap_detected / false_observed_zero | missing statement period flagged PARTIAL_COVERAGE / any missing period shown as observed zero | 1.00 / 0.00 | — | — | 6 |
| balance_break_recall | planted balance perturbations found by statement forensics | 1.00 | 1.00–1.00 | 1.00 | 24 |
| innocent_triage_flag_rate | sealed-innocent accounts flagged by rule triage (lower is better) | 0.049 | 0.02–0.09 | 0.00–0.33 | 30 |
| knowing_participation_auto_asserted | P5/P6 ever auto-set to supported | 0 | — | — | 30 |
| common_operator_edges / shared_infra_candidates | shared hosting turned into an operator link / surfaced as CANDIDATE | 0.00 / 1.00 | — | — | 30 |
| proof_verify_pass / proof_tamper_detected | offline verifier passes originals / fails a modified source file | 1.00 / 1.00 | — | — | 30 |
| lab_* (4 profiles) | missing statement changes the result; OCR substitution is sensitive; shared hosting and stale DNS leave conclusions stable | 1.00 each | — | — | 30 |
| campaign rotation_recall / benign_false_cluster_rate | identifier-rotation pairs linked HIGH / benign look-alike pairs linked HIGH | 1.00 / 0.00 | — | — | 6 pairs each |

## Graph-only baseline vs PS05-X on identical cases

The baseline (`app/services/baseline.py`) follows every debit from every statement-holder account to its counterparty and onwards with no corroboration, timing, amount, duplicate or noise filtering, and treats any two domains sharing an IP as a common operator. It is the deliberately unsafeguarded comparison point.

| Per case (mean, 30 cases) | Graph-only baseline | PS05-X fund paths (accounts downstream on reconstructed paths) | PS05-X rule triage (cue only) |
|---|---|---|---|
| Mule recall | 0.74 (CI 0.70–0.76) | 0.75 (CI 0.74–0.77) | 0.24 (CI 0.20–0.28) |
| Mule precision | 0.33 | 0.34 | 0.78 |
| Innocent / victim accounts reached or flagged | 2.4 | 2.6 | 0.2 |
| Common-operator pairs asserted | 1.0 | 0 | 0 |

How to read this honestly:

- Reaching an account is not flagging it. PS05-X fund paths record where money demonstrably went (reference, amount and time checked, unresolved hops explicit), so they reach the same unrelated counterparties a naive traversal reaches — rent, groceries, a reversed supplier payment. PS05-X never labels those accounts; the baseline does.
- The suspicion cue (rule triage) flags one innocent account in five cases while flagging a quarter of the true collection/layering accounts. It is deliberately conservative and is presented as a cue, never a finding; it is not the detection mechanism.
- The decisive difference is attribution discipline: the baseline asserts one common-operator pair per case from a shared IP (always a planted decoy); PS05-X asserts none and keeps shared infrastructure as a CANDIDATE with alternatives. The role review never asserts knowing participation.
- Mule recall below 1.0 on both sides is structural: accounts beyond the last supplied statement are unreachable from the evidence, and PS05-X reports them as UNDETERMINED rather than guessing.

## Changes since the previous run

Generator 0.4.1 no longer perturbs the balance of a row that was also planted as a duplicate (the break was correctly attributed to the duplicate and the planted mismatch was unobservable); `balance_break_recall` returned to 1.00 on 24 cases. The `commingled_funds` family now plants a same-day reversal pair, which bounded attribution reports as gross vs net.

## Limitations

Synthetic only; 30 cases; detectors and generator share assumptions; `pi_match_precision` < 1 reflects deliberately OCR-corrupted VPAs matched only as CANDIDATE; width ratio depends on how many statements each scenario supplies; the baseline is a definition in this repository, not a measurement of any real tool. Benchmark v1 (`docs/BENCHMARK.md`) remains the false-link safeguard benchmark.
