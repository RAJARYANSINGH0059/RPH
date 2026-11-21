"""Bounded fund provenance / multiple feasible financial worlds.

Time-expanded two-commodity balance model solved as a linear programme (scipy.optimize.linprog, HiGHS).
For every account with its own statement, the rows are replayed in time order. Two commodities share the balance:
V = victim-origin funds (tagged by the chosen origin transaction(s) and propagated along observed transfers), O = other funds.
Each outflow j is split into v_j + o_j = amount_j with v_j <= V-balance before j and o_j <= O-balance before j.
Opening balance is O (if known) or an unknown non-negative O amount (if not). Observed running balances add equality
constraints (infeasibility surfaces conflicting rows). Min/max of v_j for the onward hops gives feasible attribution bounds.
FIFO / LIFO are optional labelled scenarios, never defaults. Accounts without statements make the chain UNDETERMINED beyond them.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import Case, EvidenceItem, Transaction
from app.services.contract import finding, result

FLOW_VERSION = "1.0.0"
STATUSES = ["EXACT_UNDER_CONSTRAINTS", "BOUNDED_UNDER_CONSTRAINTS", "UNDETERMINED", "INFEASIBLE"]


def _rows_for(db: Session, case: Case, canon: str, alias: dict) -> list[Transaction]:
    """Rows of the account's own statement(s) in statement order. Within one file the bank's row order is authoritative (parsed
    dates may be ambiguous); files are ordered by their first parsed time."""
    rows = db.execute(select(Transaction, EvidenceItem.source_file_id, EvidenceItem.source_locator).join(EvidenceItem, Transaction.evidence_item_id == EvidenceItem.id)
                      .where(Transaction.case_id == case.id)).all()
    rows = [(t, f, (loc or {}).get("row") or 0) for t, f, loc in rows if alias.get(t.account_ref, t.account_ref) == canon and t.amount_minor is not None and t.direction in {"debit", "credit"} and not t.duplicate_of]
    first_time = {}
    for t, f, _ in rows:
        if t.datetime_utc and (f not in first_time or t.datetime_utc < first_time[f]):
            first_time[f] = t.datetime_utc
    rows.sort(key=lambda x: ((0, first_time[x[1]].timestamp()) if x[1] in first_time else (1, 0.0), x[2], x[0].id))
    return [t for t, _, _ in rows]


def analyse(db: Session, case: Case, *, origin_transaction_ids: list[str] | None = None, path_index: int | None = None, scenario: str | None = None) -> dict:
    """Bounds for victim-origin funds along a reconstructed path (default: the chosen path's first hop is the origin)."""
    try:
        import numpy as np
        from scipy.optimize import linprog
    except Exception as exc:  # pragma: no cover
        return result(case, "bounded_fund_provenance", FLOW_VERSION, findings=[], status="unavailable", warnings=[f"scipy unavailable: {type(exc).__name__}"])
    alias = engine.alias_map(db, case)
    paths = engine.reconstruct_paths(db, case)
    if not paths:
        return result(case, "bounded_fund_provenance", FLOW_VERSION, findings=[], status="UNDETERMINED", warnings=["no reconstructed path"], attribution_status="UNDETERMINED", hops=[], missing_evidence=[], assumptions=[], inconsistencies=[], invariant_facts=[], possible_not_invariant=[], scenarios={}, path=None, statuses=STATUSES)
    all_tx = {t.id: t for t in db.execute(select(Transaction).where(Transaction.case_id == case.id)).scalars()}
    holders_all = {alias.get(t.account_ref, t.account_ref) for t in all_tx.values()}
    if path_index is None or not (0 <= path_index < len(paths)):
        path_index = next((i for i, pp in enumerate(paths) if len(pp["accounts"]) > 1 and pp["accounts"][1] in holders_all), 0)
    p = paths[path_index]
    origin_ids = set(origin_transaction_ids or [p["hops"][0]["tx_id"]])
    origin_amount = sum(all_tx[i].amount_minor or 0 for i in origin_ids if i in all_tx)
    accounts = p["accounts"][1:]  # downstream of the victim
    holders = {alias.get(t.account_ref, t.account_ref) for t in all_tx.values()}
    # variables: per account a, per outflow j: v_{a,j}; per account: open_O_a (if opening unknown)
    var_names: list[str] = []
    var_index: dict[str, int] = {}

    def var(name: str) -> int:
        if name not in var_index:
            var_index[name] = len(var_names)
            var_names.append(name)
        return var_index[name]

    A_ub, b_ub, A_eq, b_eq = [], [], [], []
    bounds_hi: dict[str, float] = {}
    hop_vars: list[tuple[str, str, str, int]] = []  # (account, tx_id, var, amount)
    inconsistencies, assumptions, missing = [], [], []
    # victim-origin inflow into account k comes from the hop var of the previous account (or the origin amount for the first)
    v_in_expr: dict[str, list[tuple[float, str | None]]] = {}  # account -> list of (coef, var or None for constant)
    v_in_expr[accounts[0]] = [(float(origin_amount), None)]
    undetermined_from = None
    for k, acct in enumerate(accounts):
        if acct not in holders:
            missing.append({"account": acct, "needed": f"statement of {acct}", "effect": "attribution beyond this account is UNDETERMINED; the inflow into it is bounded by the previous hop"})
            undetermined_from = acct
            break
        rows = _rows_for(db, case, acct, alias)
        if any(t.time_precision in {"ambiguous", "unknown"} for t in rows):
            assumptions.append({"account": acct, "assumption": "rows with ambiguous/unknown time are ordered as recorded in the statement", "rows": [t.id for t in rows if t.time_precision in {"ambiguous", "unknown"}][:10]})
        # running-balance breaks (perturbed/mistyped balances) are reported and excluded from the equality constraints so one bad
        # cell does not make the whole system infeasible; the break itself is surfaced as an inconsistency with its rows
        # Unexplained balance changes between consecutive rows (missing statement period, perturbed cell): modelled as an unknown
        # movement of that size right before the row. A positive gap is other money arriving; a negative gap is an outflow of unknown
        # composition that MAY have carried victim-origin funds, so it gets its own bounded variable (widening later intervals honestly).
        gap_before: dict[str, int] = {}
        for prev_t, t in zip(rows, rows[1:]):
            if prev_t.balance_after_minor is not None and t.balance_after_minor is not None and t.amount_minor is not None:
                expected = prev_t.balance_after_minor + (t.amount_minor if t.direction == "credit" else -t.amount_minor)
                delta = t.balance_after_minor - expected
                if delta != 0:
                    gap_before[t.id] = delta
                    inconsistencies.append({"account": acct, "row_transaction_ids": [prev_t.id, t.id], "issue": f"unexplained balance change between rows: {delta} paise ({'unknown inflow' if delta > 0 else 'unknown outflow'})",
                                            "handling": "modelled as an unknown movement of that size; a negative gap may have carried victim-origin funds, so bounds widen"})
                    assumptions.append({"account": acct, "assumption": f"an unknown {'inflow' if delta > 0 else 'outflow'} of {abs(delta)} paise occurred before row {t.id[:8]} (statement gap or balance error)"})
        # opening O balance: known from first row's balance_after - first row effect, else unknown variable
        first = rows[0] if rows else None
        if first is not None and first.balance_after_minor is not None:
            open_o = first.balance_after_minor - (first.amount_minor if first.direction == "credit" else -first.amount_minor)
            if open_o < 0:
                inconsistencies.append({"account": acct, "row_transaction_id": first.id, "issue": f"implied opening balance negative ({open_o} paise)"})
                open_o = 0.0
            open_terms = [(float(open_o), None)]
        else:
            ov = var(f"openO:{acct}")
            open_terms = [(1.0, ov)]
            assumptions.append({"account": acct, "assumption": "opening balance unknown (no running balance); treated as unknown non-negative other funds"})
        # replay
        # V balance expression (sum coef*var + const). Victim-origin inflow is credited at the row where it arrives, not before.
        pending_v: list[tuple[float, str | None]] = list(v_in_expr.get(acct, []))
        V_terms: list[tuple[float, str | None]] = []
        O_terms: list[tuple[float, str | None]] = list(open_terms)
        v_credited = False
        onward_targets = {h["dst"] for h in p["hops"] if h["src"] == acct}
        for t in rows:
            cp = alias.get(t.counterparty_ref, t.counterparty_ref) if t.counterparty_ref else None
            gap = gap_before.get(t.id)
            if gap:
                if gap > 0:
                    O_terms.append((float(gap), None))  # unknown other inflow
                else:
                    gv = var(f"v:{acct}:gap:{t.id}")  # unknown outflow: victim-origin part bounded by the V balance
                    bounds_hi[f"v:{acct}:gap:{t.id}"] = float(-gap)
                    A_ub.append(_lin({gv: 1.0}, V_terms, -1.0, var))
                    b_ub.append(_const(V_terms))
                    A_ub.append(_lin({gv: -1.0}, O_terms, -1.0, var))
                    b_ub.append(_const(O_terms) - float(-gap))
                    V_terms = V_terms + [(-1.0, gv)]
                    O_terms = O_terms + [(float(gap), None), (1.0, gv)]
            if t.direction == "credit":
                if k == 0 and (t.id in origin_ids or _matches_hop(p, p["accounts"][0], acct, t)):
                    V_terms = V_terms + [(float(t.amount_minor), None)]  # origin credit arrives here
                    v_credited = True
                elif k > 0 and not v_credited and cp == accounts[k - 1] and _matches_hop(p, accounts[k - 1], acct, t):
                    V_terms = V_terms + pending_v  # upstream hop variable arrives here
                    v_credited = True
                else:
                    O_terms.append((float(t.amount_minor), None))
            else:
                vj = var(f"v:{acct}:{t.id}")
                bounds_hi[f"v:{acct}:{t.id}"] = float(t.amount_minor)
                # v_j <= V balance before: v_j - V_terms <= 0
                A_ub.append(_lin({vj: 1.0}, V_terms, -1.0, var))
                b_ub.append(_const(V_terms))
                # o_j = amount - v_j <= O balance before: -v_j - O_terms <= -amount
                A_ub.append(_lin({vj: -1.0}, O_terms, -1.0, var))
                b_ub.append(_const(O_terms) - float(t.amount_minor))
                V_terms = V_terms + [(-1.0, vj)]
                O_terms = O_terms + [(-float(t.amount_minor), None), (1.0, vj)]
                if cp in onward_targets:
                    hop_vars.append((acct, t.id, f"v:{acct}:{t.id}", t.amount_minor))
            # running balance equality where present: V + O == balance_after
            if t.balance_after_minor is not None:
                A_eq.append(_lin({}, V_terms + O_terms, 1.0, var))
                b_eq.append(float(t.balance_after_minor) - _const(V_terms + O_terms))
        if not v_credited and k > 0:
            inconsistencies.append({"account": acct, "issue": "the upstream hop is not visible as a credit in this account's own statement"})
        # V flowing to the next account = v on the hop tx into accounts[k+1]
        if k + 1 < len(accounts):
            nxt = accounts[k + 1]
            hv = [(1.0, var_index[name]) for (a, tid, name, amt) in hop_vars if a == acct and alias.get(all_tx[tid].counterparty_ref or "", all_tx[tid].counterparty_ref) == nxt]
            v_in_expr[nxt] = hv if hv else [(0.0, None)]
    n = len(var_names)
    if n == 0:
        return result(case, "bounded_fund_provenance", FLOW_VERSION, findings=[], status="UNDETERMINED", attribution_status="UNDETERMINED", hops=[], inconsistencies=inconsistencies,
                      invariant_facts=[], possible_not_invariant=[], scenarios={}, origin={"transaction_ids": sorted(origin_ids), "amount_minor": origin_amount, "victim_account": p["accounts"][0]},
                      warnings=["no downstream statement with outflows available: attribution is UNDETERMINED beyond the first account"], missing_evidence=missing, assumptions=assumptions, path={"index": paths.index(p), "accounts": p["accounts"], "status": p["status"]}, undetermined_from=undetermined_from, statuses=STATUSES)

    def pad(row):
        return row + [0.0] * (n - len(row))
    A_ub_m = np.array([pad(r) for r in A_ub]) if A_ub else None
    A_eq_m = np.array([pad(r) for r in A_eq]) if A_eq else None
    bnds = [(0.0, bounds_hi.get(name)) for name in var_names]
    results = []
    status = "BOUNDED_UNDER_CONSTRAINTS"
    solver_status = "optimal"
    for (acct, tid, name, amt) in hop_vars:
        c = np.zeros(n)
        c[var_index[name]] = 1.0
        lo = linprog(c, A_ub=A_ub_m, b_ub=np.array(b_ub) if b_ub else None, A_eq=A_eq_m, b_eq=np.array(b_eq) if b_eq else None, bounds=bnds, method="highs")
        hi = linprog(-c, A_ub=A_ub_m, b_ub=np.array(b_ub) if b_ub else None, A_eq=A_eq_m, b_eq=np.array(b_eq) if b_eq else None, bounds=bnds, method="highs")
        if lo.status != 0 or hi.status != 0:
            solver_status = lo.message if lo.status != 0 else hi.message
            status = "INFEASIBLE" if lo.status == 2 or hi.status == 2 else "UNDETERMINED"
            results.append({"account": acct, "transaction_id": tid, "observed_transfer_minor": amt, "minimum_attributable_minor": None, "maximum_attributable_minor": None, "solver": solver_status})
            continue
        mn, mx = int(round(lo.fun)), int(round(-hi.fun))
        witness_min = {var_names[i].replace(":gap:", ":unknown_outflow:"): int(round(x)) for i, x in enumerate(lo.x) if var_names[i].startswith("v:") and round(x) > 0}
        witness_max = {var_names[i].replace(":gap:", ":unknown_outflow:"): int(round(x)) for i, x in enumerate(hi.x) if var_names[i].startswith("v:") and round(x) > 0}
        t = all_tx[tid]
        results.append({"account": acct, "transaction_id": tid, "to_account": alias.get(t.counterparty_ref or "", t.counterparty_ref), "event_time": t.datetime_utc.isoformat() if t.datetime_utc else None,
                        "observed_transfer_minor": amt, "minimum_attributable_minor": mn, "maximum_attributable_minor": mx, "exact": mn == mx, "interval_width_minor": mx - mn,
                        "not_attributable_from_evidence_minor": amt - mx, "witness_allocation_min": witness_min, "witness_allocation_max": witness_max,
                        "explanation": _explain(mn, mx, amt, acct, assumptions, missing)})
    if status == "BOUNDED_UNDER_CONSTRAINTS" and results and all(r.get("exact") for r in results) and not missing:
        status = "EXACT_UNDER_CONSTRAINTS"
    if undetermined_from and status != "INFEASIBLE":
        status = "BOUNDED_UNDER_CONSTRAINTS" if results else "UNDETERMINED"
    # optional labelled scenarios (assumption-based, never default)
    scenarios = {}
    if scenario in {"fifo", "lifo"}:
        scenarios[scenario] = _scenario(db, case, alias, p, accounts, origin_ids, all_tx, scenario)
    invariant = [f"Victim-origin funds reaching {r['to_account']} are at least ₹{r['minimum_attributable_minor'] / 100:,.2f} and at most ₹{r['maximum_attributable_minor'] / 100:,.2f} under the recorded constraints"
                 for r in results if r.get("minimum_attributable_minor") is not None]
    possible = [f"Any allocation between the bounds for {r['to_account']} is consistent with the evidence; the witnesses shown are illustrative, not a trace of specific rupees" for r in results if r.get("exact") is False]
    findings = [finding("attribution_bounds", f"{r['account']} → {r.get('to_account')}: [{r['minimum_attributable_minor']}, {r['maximum_attributable_minor']}] paise of ₹{r['observed_transfer_minor'] / 100:,.2f} transfer",
                        evidence_class="derived", evidence_refs=[all_tx[r["transaction_id"]].evidence_item_id], **{k: r[k] for k in ("minimum_attributable_minor", "maximum_attributable_minor", "exact")})
                for r in results if r.get("minimum_attributable_minor") is not None]
    return result(case, "bounded_fund_provenance", FLOW_VERSION, findings=findings, status=status, attribution_status=status, input_evidence_ids=[all_tx[t].evidence_item_id for t in origin_ids if t in all_tx],
                  limitations=["Money is fungible after commingling: bounds describe what the records permit, not which rupees moved.", "FIFO/LIFO results are assumption scenarios, labelled as such, never facts.",
                               "Accounts without their own statement end the computable chain (UNDETERMINED beyond them)."],
                  warnings=[f"solver: {solver_status}"] if solver_status != "optimal" else [], method="time_expanded_two_commodity_lp", solver="scipy.optimize.linprog(highs)",
                  origin={"transaction_ids": sorted(origin_ids), "amount_minor": origin_amount, "victim_account": p["accounts"][0]}, path={"index": paths.index(p), "accounts": p["accounts"], "status": p["status"]},
                  hops=results, assumptions=assumptions, inconsistencies=inconsistencies, missing_evidence=missing, undetermined_from=undetermined_from, invariant_facts=invariant,
                  possible_not_invariant=possible, scenarios=scenarios, variables=len(var_names), constraints={"inequalities": len(A_ub), "equalities": len(A_eq)}, statuses=STATUSES)


def _matches_hop(p: dict, src: str, dst: str, t: Transaction) -> bool:
    for h in p["hops"]:
        if h["src"] == src and h["dst"] == dst and (h["reference"] and t.external_reference and h["reference"] == t.external_reference or h["amount_minor"] == t.amount_minor):
            return True
    return False


def _lin(direct: dict[int, float], terms: list[tuple[float, str | None]], sign: float, var) -> list[float]:
    """Build a dense coefficient row: direct vars + sign * variable parts of `terms`."""
    row: dict[int, float] = dict(direct)
    for coef, v in terms:
        if v is not None:
            row[v] = row.get(v, 0.0) + sign * coef
    size = (max(row) + 1) if row else 0
    out = [0.0] * size
    for i, c in row.items():
        out[i] = c
    return out


def _const(terms: list[tuple[float, str | None]]) -> float:
    return sum(c for c, v in terms if v is None)


def _explain(mn: int, mx: int, amt: int, acct: str, assumptions: list, missing: list) -> str:
    if mn == mx:
        return "Exact under the constraints: the balance history leaves only one feasible allocation for this transfer."
    reasons = []
    if mx < amt:
        reasons.append(f"at most ₹{mx / 100:,.2f} of the ₹{amt / 100:,.2f} transfer can be victim-origin because the victim-origin balance never exceeded that amount")
    if mn == 0:
        reasons.append("other funds in the account were sufficient to cover the whole transfer, so the minimum is zero")
    elif mn > 0:
        reasons.append(f"other funds could not cover more than ₹{(amt - mn) / 100:,.2f}, so at least ₹{mn / 100:,.2f} must be victim-origin")
    if any(a["account"] == acct for a in assumptions):
        reasons.append("ordering or opening-balance assumptions apply to this account (see assumptions)")
    return "; ".join(reasons) + "."


def _scenario(db, case, alias, p, accounts, origin_ids, all_tx, mode: str) -> dict:
    """Assumption-based attribution (FIFO or LIFO) for comparison only."""
    out = []
    v_in = sum(all_tx[i].amount_minor or 0 for i in origin_ids if i in all_tx)
    for k, acct in enumerate(accounts):
        rows = _rows_for(db, case, acct, alias)
        if not rows:
            break
        # pool of layers [(amount, is_victim)]
        first = rows[0]
        open_o = max(0, (first.balance_after_minor - (first.amount_minor if first.direction == "credit" else -first.amount_minor))) if first.balance_after_minor is not None else 0
        layers: list[list] = [[open_o, False]] if open_o else []
        to_next = 0
        nxt = accounts[k + 1] if k + 1 < len(accounts) else None
        for t in rows:
            cp = alias.get(t.counterparty_ref, t.counterparty_ref) if t.counterparty_ref else None
            if t.direction == "credit":
                victim = (t.id in origin_ids) or (k == 0 and _matches_hop(p, p["accounts"][0], acct, t)) or (k > 0 and cp == accounts[k - 1] and _matches_hop(p, accounts[k - 1], acct, t))
                layers.append([t.amount_minor if not victim else v_in, victim])
            else:
                need, v_used = t.amount_minor, 0
                order = layers if mode == "fifo" else list(reversed(layers))
                for layer in order:
                    take = min(layer[0], need)
                    layer[0] -= take
                    need -= take
                    if layer[1]:
                        v_used += take
                    if need == 0:
                        break
                layers = [l for l in layers if l[0] > 0]
                if cp == nxt:
                    to_next += v_used
                    out.append({"account": acct, "transaction_id": t.id, "to_account": cp, "victim_origin_under_" + mode: v_used, "transfer_minor": t.amount_minor})
        v_in = to_next
    return {"label": f"{mode.upper()} assumption scenario (not evidence)", "hops": out}
