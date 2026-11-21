# Bounded fund attribution (multiple feasible financial worlds)

Implementation: `apps/api/app/services/bounded_flow.py`; API `GET /api/cases/{id}/bounded-flow?path_index=&scenario=fifo|lifo`; UI *Financial Intelligence → Bounded Fund Provenance*; consumed by *Intervention Impact*.

## Formulation

Time-expanded two-commodity balance model solved as a linear programme (`scipy.optimize.linprog`, HiGHS).

For each account on the chosen path that has its own statement, rows are replayed in statement order (the bank's row order is authoritative within a file; ambiguous dates are flagged as an assumption, not reordered). Two commodities share the balance:

- **V** — victim-origin funds, credited when the origin transaction (or the upstream hop variable) arrives;
- **O** — other funds: opening balance (from the first running balance, else an unknown non-negative variable) plus every other credit.

For each debit *j* of amount *a_j*: `v_j + o_j = a_j`, `v_j ≤ V_before`, `o_j ≤ O_before`, `0 ≤ v_j ≤ a_j`. Each running balance adds the equality `V + O = balance_after`. An unexplained balance change between rows (missing statement period or a perturbed cell) is modelled as an unknown movement of that size: a positive gap is other money arriving; a negative gap is an outflow of unknown composition with its own bounded victim-origin variable, so later intervals widen honestly. The debit that feeds the next account becomes that account's V inflow (joint LP across the path).

Objective: minimise and maximise `v_j` for each onward hop.

## Outputs

Per hop: observed transfer, minimum and maximum attributable (paise), `exact` only when min = max, not attributable from evidence, witness allocations at min and max (illustrative, not a trace of rupees), explanation. Case-level: `attribution_status` ∈ `EXACT_UNDER_CONSTRAINTS | BOUNDED_UNDER_CONSTRAINTS | UNDETERMINED | INFEASIBLE`, invariant facts, possible-but-not-invariant allocations, inconsistencies (with the conflicting rows), assumptions, missing statements that would narrow the interval, solver status, variable and constraint counts.

## Assumptions and scenarios

FIFO and LIFO are available only as labelled assumption scenarios (`?scenario=fifo`); they are never the default and never presented as fact. Scenario counts are not probabilities.

## Undetermined and infeasible

An account without a statement ends the computable chain: the inflow into it is bounded by the previous hop and everything beyond is `UNDETERMINED`. If the constraint system is infeasible after gap modelling, the status is `INFEASIBLE` and the conflicting rows are listed; amounts are never altered to force a solution.

## Worked example (illustrative)

Account A receives ₹1,00,000 victim-origin and holds ₹40,000 other funds; it pays ₹70,000 to B and ₹60,000 to C with ₹10,000 left. Victim-origin to B is feasible in [₹30,000, ₹70,000] and to C in [₹20,000, ₹60,000], jointly constrained so that B + C + remaining victim-origin = ₹1,00,000. The UI shows both bands and states that the marginal ranges cannot be combined arbitrarily.

## Metrics (benchmark v2)

Interval coverage of the generator's sealed simulated allocation, mean width ratio, false-exact rate, hops scored. Reported with bootstrap 95% CIs in `docs/BENCHMARK_V2.md`.

## Tests

`apps/api/tests/test_bounded_adversary_lab.py::test_bounded_flow_bounds_are_sound`, `::test_bounded_flow_undetermined_without_statement`.
