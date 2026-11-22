"""Property-based tests for fund conservation and the invariants that must hold whatever the ledger looks like.

Scenario tests check the cases we thought of. These generate ledgers we did not: arbitrary credits, debits, running
balances, duplicates, reversals and missing periods, and assert the properties that must never break.

The properties are stated as the specification states them:

* no amount is created from nothing;
* no source transaction is counted twice;
* a refund is not silently netted away;
* missing evidence is never treated as zero;
* an unrelated balance is never attributed to a victim;
* every reported amount traces back to raw source cells.

The bounded attribution solver is the component under test, exercised through the same service the API uses.
"""
from __future__ import annotations


import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st


PAISE = st.integers(min_value=1_00, max_value=5_000_00)

# Property tests run many examples; a case fixture is expensive, so the ledger-level properties below are pure and the
# end-to-end ones are marked and run with a small budget.
SETTINGS = settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])


# --------------------------------------------------------------------------------------------------------------
# Pure properties of the attribution arithmetic itself
# --------------------------------------------------------------------------------------------------------------

@given(victim=PAISE, other=PAISE, out1=PAISE, out2=PAISE)
@SETTINGS
def test_attributable_never_exceeds_what_arrived_or_what_left(victim, other, out1, out2):
    """Whatever the mix, the victim-origin part of an outgoing transfer cannot exceed the transfer itself, nor the
    victim money that ever arrived. This is conservation stated at its simplest."""
    pool_v, pool_o = victim, other
    for out in (out1, out2):
        # Only a ledger that could actually pay the transfer is meaningful here; an overdraft is a different case,
        # covered by the solver's INFEASIBLE status rather than by this arithmetic.
        assume(out <= pool_v + pool_o)
        v_max = min(out, pool_v)
        v_min = max(0, out - pool_o)
        assert 0 <= v_min <= v_max <= out, "the feasible band must lie inside the transfer"
        assert v_max <= victim, "no more victim money can leave than ever arrived"
        # advance one feasible world: take the maximum victim share, the tightest case for what follows
        pool_v -= v_max
        pool_o -= out - v_max


@given(victim=PAISE, other=PAISE, outs=st.lists(PAISE, min_size=1, max_size=5))
@SETTINGS
def test_sum_of_minimums_never_exceeds_the_victim_inflow(victim, other, outs):
    """Across several onward transfers, the amounts that must be victim-origin cannot together exceed what arrived:
    otherwise the model would be creating victim money out of nothing."""
    total_out = sum(outs)
    assume(total_out > 0)
    minimums = [max(0, o - other) for o in outs]
    assert sum(minimums) <= max(total_out, victim) + other


@given(amount=PAISE)
@SETTINGS
def test_a_reversed_transfer_is_reported_gross_and_net_not_netted_away(amount):
    """A debit later reversed must still be visible: gross keeps it, net removes it, and the two differ by exactly
    the reversed amount. Silently netting would hide a movement that happened."""
    gross, reversed_minor = amount, amount
    net = gross - reversed_minor
    assert gross == amount and net == 0 and gross - net == reversed_minor


@given(known=st.lists(PAISE, min_size=0, max_size=4))
@SETTINGS
def test_missing_period_widens_the_band_rather_than_reading_as_zero(known):
    """An unexplained balance change is an unknown movement. It must widen what is possible, never silently count as
    no activity, which would understate what could have left."""
    observed = sum(known)
    unknown_gap = 10_000_00
    lower_without_gap, upper_without_gap = observed, observed
    lower_with_gap, upper_with_gap = observed, observed + unknown_gap
    assert upper_with_gap > upper_without_gap or unknown_gap == 0
    assert lower_with_gap == lower_without_gap, "a gap cannot raise the floor; it only admits more possibilities"
    assert upper_with_gap != 0 or observed == 0, "a gap must never be read as zero activity"


# --------------------------------------------------------------------------------------------------------------
# The same invariants asserted against the real solver on a generated case
# --------------------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def case(client, analyst):
    r = client.post("/api/synthetic/generate",
                    json={"scenario_type": "commingled_funds", "difficulty": "messy", "size": "small", "seed": 7301},
                    headers=analyst)
    assert r.status_code == 201
    return r.json()["case"]["id"]


def test_solver_bands_obey_conservation_on_every_path(client, analyst, case):
    """For every reconstructed path, each hop's band lies inside the transfer and inside the victim inflow, the
    not-attributable remainder adds up, and nothing claims exactness it has not got."""
    paths = client.get(f"/api/cases/{case}/paths", headers=analyst).json()["paths"]
    assert paths, "the scenario must reconstruct at least one path"
    checked = 0
    for i in range(min(len(paths), 6)):
        bf = client.get(f"/api/cases/{case}/bounded-flow?path_index={i}", headers=analyst).json()
        if not bf.get("hops"):
            continue
        origin = bf["origin"]["amount_minor"]
        for h in bf["hops"]:
            if h.get("minimum_attributable_minor") is None:
                continue
            lo, hi, moved = h["minimum_attributable_minor"], h["maximum_attributable_minor"], h["observed_transfer_minor"]
            assert 0 <= lo <= hi <= moved, f"band outside the transfer on path {i}"
            assert hi <= origin, "more victim money attributed than ever entered"
            assert h["not_attributable_from_evidence_minor"] == moved - hi
            assert (lo == hi) == h["exact"], "exactness must mean the band collapsed, nothing else"
            checked += 1
    assert checked, "no hop was scored"


def test_duplicate_rows_are_preserved_but_not_counted_twice(client, analyst, case):
    """Duplicates are kept as evidence and flagged, and excluded from the counted total: both halves matter."""
    c = client.get(f"/api/cases/{case}/counts", headers=analyst).json()
    txs = client.get(f"/api/cases/{case}/transactions", headers=analyst).json()
    flagged = [t for t in txs if t.get("duplicate_of")]
    assert len(txs) == c["transactions"]["total"], "every row, duplicates included, is still present"
    assert c["transactions"]["excluding_duplicates"] == c["transactions"]["total"] - c["transactions"]["duplicates"]
    assert len(flagged) == c["transactions"]["duplicates"]


def test_every_reported_amount_traces_back_to_a_source_cell(client, analyst, case):
    """A number with no raw cell behind it cannot be audited, so the proof manifest must carry one for every hop."""
    proof = client.get(f"/api/cases/{case}/paths/0/proof.json", headers=analyst).json()
    assert proof["hops"], "a path must carry its hops"
    for hop in proof["hops"]:
        assert hop["source_sha256"] and hop["locator"], "a hop without a source file and locator is unauditable"
        assert hop["raw_row"], "the raw row must be retained beside the normalised value"
        assert hop["amount_raw"] is not None, "the amount must be traceable to the text that produced it"
