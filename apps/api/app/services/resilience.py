"""Investigative chokepoint map and network resilience / displacement simulator.

Structural measures over OBSERVED/CORROBORATED money edges only (candidates excluded), with removal simulations on an
in-memory copy. Centrality is not culpability and not operational criticality. What-if runs never touch the database.
Hypothetical substitutions are only applied when the investigator supplies them and are labelled as assumptions.
"""
from __future__ import annotations

from collections import defaultdict

import networkx as nx
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import Case
from app.services.contract import finding, result

RESILIENCE_VERSION = "1.0.0"
DISCLAIMER = ("Network centrality, path count or removal impact is a structural property of the supplied records. It is not proof of criminality, intent, "
              "control or operational criticality, and it is not a recommendation to freeze, seize or take any enforcement action. Framed as defensive investigative resilience analysis.")


def _graph(db: Session, case: Case):
    edges = [e for e in engine.money_edges(db, case) if not e["duplicate"]]
    paths = engine.reconstruct_paths(db, case)
    g = nx.DiGraph()
    for e in edges:
        if g.has_edge(e["src"], e["dst"]):
            g[e["src"]][e["dst"]]["amount"] += e["amount_minor"]
            g[e["src"]][e["dst"]]["tx"].append(e["tx_id"])
            g[e["src"]][e["dst"]]["uncertain"] = g[e["src"]][e["dst"]]["uncertain"] or e["precision"] in {"ambiguous", "unknown"}
        else:
            g.add_edge(e["src"], e["dst"], amount=e["amount_minor"], tx=[e["tx_id"]], corroborated=e["corroborated"], uncertain=e["precision"] in {"ambiguous", "unknown"})
    return g, edges, paths


def _roles(paths):
    """Functional roles from reconstructed paths. Paths whose origin never receives money (true entry points) assign roles first,
    so a chain fragment that starts at an intermediary does not relabel it as a victim."""
    receives = {h["dst"] for p in paths for h in p["hops"]}
    role: dict[str, str] = {}
    for p in sorted(paths, key=lambda p: (p["accounts"][0] in receives, -p["hop_count"])):
        accts = p["accounts"]
        for i, a in enumerate(accts):
            role.setdefault(a, "victim" if i == 0 else "collection" if i == 1 else "exit" if i == len(accts) - 1 else "layering")
    return role


def chokepoints(db: Session, case: Case) -> dict:
    g, edges, paths = _graph(db, case)
    receives = {h["dst"] for p in paths for h in p["hops"]}
    victims = {p["accounts"][0] for p in paths} - receives  # entry points that never receive money
    ends = {p["accounts"][-1] for p in paths}
    through: dict[str, set] = defaultdict(set)
    amount_through: dict[str, int] = defaultdict(int)
    seen_tx: dict[str, set] = defaultdict(set)
    for i, p in enumerate(paths):
        for h in p["hops"]:
            n = h["dst"]
            through[n].add(i)
            if h["tx_id"] not in seen_tx[n]:
                seen_tx[n].add(h["tx_id"])
                amount_through[n] += h["amount_minor"]
    bet = nx.betweenness_centrality(g) if g.number_of_nodes() > 2 else {}
    rows = []
    for n in g.nodes:
        if n in victims:
            continue
        h = g.copy()
        h.remove_node(n)
        disconnected = sum(1 for p in paths if n in p["accounts"][1:-1] and p["accounts"][0] in h and p["accounts"][-1] in h and not nx.has_path(h, p["accounts"][0], p["accounts"][-1]))
        uncertain_in = sum(1 for u, v, d in g.in_edges(n, data=True) if d.get("uncertain"))
        rows.append({"account": n, "role": _roles(paths).get(n, "other"), "supported_paths_through": len(through.get(n, ())), "distinct_amount_through_minor": amount_through.get(n, 0), "betweenness": round(bet.get(n, 0.0), 4),
                     "paths_disconnected_if_records_missing": disconnected, "in_degree": g.in_degree(n), "out_degree": g.out_degree(n), "is_path_end": n in ends, "uncertain_time_edges_in": uncertain_in,
                     "explanation": f"{len(through.get(n, ()))} evidenced path(s) pass through this account carrying ₹{amount_through.get(n, 0) / 100:,.2f} (each transaction counted once); removing its records would disconnect {disconnected} path(s)."
                                    + (" Some inbound edges have uncertain times: sensitivity to ordering." if uncertain_in else "")})
    rows.sort(key=lambda r: (-r["supported_paths_through"], -r["distinct_amount_through_minor"], r["account"]))
    return result(case, "chokepoint_map", RESILIENCE_VERSION, findings=[finding("chokepoint", f"{r['account']}: {r['supported_paths_through']} paths, betweenness {r['betweenness']}", evidence_class="derived", account=r["account"]) for r in rows[:10]],
                  limitations=[DISCLAIMER, "Only observed/corroborated money edges are used; candidate, stale and duplicate edges are excluded."], rows=rows,
                  excluded_edges=["candidate relationships (SHARED_INFRASTRUCTURE, SIMILAR_NAME)", "stale observations", "duplicate rows"],
                  graph={"nodes": g.number_of_nodes(), "edges": g.number_of_edges(), "paths": len(paths)})


def simulate(db: Session, case: Case, *, remove_accounts: list[str] | None = None, remove_function: str | None = None, substitutions: dict[str, str] | None = None) -> dict:
    g, edges, paths = _graph(db, case)
    base = g.copy()
    role = _roles(paths)
    removed = set(remove_accounts or [])
    if remove_function:
        removed |= {a for a, r in role.items() if r == remove_function}
    sim = g.copy()
    for a in removed:
        if a in sim:
            sim.remove_node(a)
    assumptions = [f"records/function of {a} removed from the observed network (analytical copy only)" for a in sorted(removed)]
    hypothetical_nodes = []
    for old, new in (substitutions or {}).items():
        if old in g:
            for u, v, d in g.in_edges(old, data=True):
                sim.add_edge(u, new, **d, hypothetical=True)
            for u, v, d in g.out_edges(old, data=True):
                sim.add_edge(new, v, **d, hypothetical=True)
            hypothetical_nodes.append(new)
            assumptions.append(f"ASSUMPTION supplied by the investigator: {old} is replaced by {new} with the same observed edges (hypothetical; not evidence)")
    after = []
    subs_map = substitutions or {}
    for i, p in enumerate(paths):
        s, t = p["accounts"][0], p["accounts"][-1]
        reach_before = base.has_node(s) and base.has_node(t) and nx.has_path(base, s, t)
        s, t = subs_map.get(s, s), subs_map.get(t, t)  # a substituted endpoint is reached through its hypothetical replacement
        reach_after = sim.has_node(s) and sim.has_node(t) and nx.has_path(sim, s, t)
        alts = []
        if reach_after:
            try:
                alts = [pp for pp in nx.all_simple_paths(sim, s, t, cutoff=6) if pp != p["accounts"]][:5]
            except nx.NetworkXNoPath:
                alts = []
        uncertain = any(sim[u][v].get("uncertain") for pp in alts for u, v in zip(pp, pp[1:]) if sim.has_edge(u, v))
        after.append({"path_index": i, "route": p["accounts"], "reachable_before": reach_before, "still_reachable_in_observed_records": reach_after, "alternative_observed_routes": alts,
                      "alternative_uses_hypothetical_node": any(n in hypothetical_nodes for pp in alts for n in pp), "alternative_depends_on_uncertain_time_edges": uncertain,
                      "affected": any(a in removed or a in (substitutions or {}) for a in p["accounts"])})
    diff = {"paths_total": len(paths), "paths_affected": sum(1 for r in after if r["affected"]), "paths_disconnected": sum(1 for r in after if r["affected"] and not r["still_reachable_in_observed_records"]),
            "paths_with_alternative_observed_route": sum(1 for r in after if r["affected"] and r["still_reachable_in_observed_records"] and r["alternative_observed_routes"] and not r["alternative_uses_hypothetical_node"]),
            "paths_with_hypothetical_route_only": sum(1 for r in after if r["affected"] and r["still_reachable_in_observed_records"] and r["alternative_uses_hypothetical_node"]),
            "components_before": nx.number_weakly_connected_components(base) if base.number_of_nodes() else 0, "components_after": nx.number_weakly_connected_components(sim) if sim.number_of_nodes() else 0,
            "nodes_removed": sorted(removed), "hypothetical_nodes": hypothetical_nodes, "functions": {k: sorted(a for a, r in role.items() if r == k) for k in ("victim", "collection", "layering", "exit")},
            "sensitive_to_uncertain_edges": any(r["alternative_depends_on_uncertain_time_edges"] for r in after)}
    no_sub = sorted(a for a in removed if all(not r["still_reachable_in_observed_records"] for r in after if a in r["route"]))
    return result(case, "network_resilience_simulation", RESILIENCE_VERSION,
                  findings=[finding("simulation", f"removing {len(removed)} node(s) disconnects {diff['paths_disconnected']} of {diff['paths_affected']} affected path(s); {diff['paths_with_alternative_observed_route']} keep an observed alternative route", evidence_class="derived")],
                  limitations=[DISCLAIMER, "Alternative routes are counted only among OBSERVED transfers; absence of an observed alternative does not mean none exists.",
                               "An alternative route is a simulated possibility, not a prediction that anyone will use it."],
                  assumptions=assumptions, inputs={"remove_accounts": sorted(remove_accounts or []), "remove_function": remove_function, "substitutions": substitutions or {}}, after=after, diff=diff,
                  dependencies_without_observed_substitute=no_sub, baseline_mutated=False)
