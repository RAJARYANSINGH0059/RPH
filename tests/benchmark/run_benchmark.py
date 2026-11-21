"""Reproducible benchmark: generate scenarios, run them through the real pipeline under four configurations, score
against sealed truth. Writes tests/benchmark/results/benchmark_summary.json.

Configurations:
  A transaction_rules      - rules triage only (no graph)            -> account triage metrics
  B financial_graph_only   - money edges, no infrastructure          -> path metrics, no infra edges
  C combined_no_safeguards - infra edges, naive shared-IP => COMMON_OPERATOR
  D ps05x_full             - full verification layer (safeguards on)

Usage: python tests/benchmark/run_benchmark.py [--seeds 6] [--size small]
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
_TMP = tempfile.mkdtemp(prefix="ps05x_bench_")
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(_TMP, "bench.db").replace("\\", "/"))
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "data"))
os.environ.setdefault("BENCHMARK_STORE_DIR", os.path.join(_TMP, "sealed"))

from sqlalchemy import select  # noqa: E402

from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.graph import engine as gengine  # noqa: E402
from app.models import CounterEvidence, Entity, EvidenceItem, Relationship, RelationshipEvidence, Role, Transaction, User  # noqa: E402
from app.synthetic import sealed_store  # noqa: E402
from app.synthetic.generator import DIFFICULTIES, GENERATOR_VERSION, SCENARIOS  # noqa: E402
from app.synthetic.service import generate_case  # noqa: E402

CONFIGS = {"A_transaction_rules": dict(infra=False, safeguards=True), "B_financial_graph_only": dict(infra=False, safeguards=True),
           "C_combined_no_safeguards": dict(infra=True, safeguards=False), "D_ps05x_full": dict(infra=True, safeguards=True)}


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0}


def evaluate(db, case, truth: dict, cfg: str) -> dict:
    t0 = time.time()
    rels = db.execute(select(Relationship).where(Relationship.case_id == case.id)).scalars().all()
    ents = {e.id: e for e in db.execute(select(Entity).where(Entity.case_id == case.id)).scalars()}
    alias = gengine.alias_map(db, case)
    role = {a["acct_no"]: a["role"] for a in truth["accounts"]}
    role.update({a["vpa"]: a["role"] for a in truth["accounts"]})
    # --- field extraction: references and amounts of true transactions recovered exactly
    txs = db.execute(select(Transaction).where(Transaction.case_id == case.id)).scalars().all()
    got = {(t.external_reference, t.amount_minor) for t in txs if t.external_reference}
    # observable truth only: transactions that appear in at least one statement included in the public bundle
    holders = set(truth["params"].get("statement_accounts", []))
    observable = [t for t in truth["transactions"] if t["src"] in holders or t["dst"] in holders]
    true_tx = {(t["ref"], t["amount_minor"]) for t in observable}
    field_tp = len(got & true_tx)
    field = prf(field_tp, len(got - true_tx), len(true_tx - got))
    # --- transaction path edges (money edges, canonicalised) vs true hop edges
    edges = {(alias.get(e["src"], e["src"]), alias.get(e["dst"], e["dst"])) for e in gengine.money_edges(db, case)}
    obs_refs = {t["ref"] for t in observable}
    true_edges = {(e["src"], e["dst"]) for e in truth["true_edges"] if e["type"] == "TRANSFERRED_TO" and e["ref"] in obs_refs}
    # canonicalise truth too (truth uses acct_no everywhere; alias map may canonicalise to vpa when no statement exists)
    true_edges_c = {(alias.get(a, a), alias.get(b, b)) for a, b in true_edges}
    path = prf(len(edges & true_edges_c), len(edges - true_edges_c), len(true_edges_c - edges))
    # --- path-level metrics (algorithm v2): coverage, false-path rate, amount conservation, temporal consistency, unresolved rate
    t_paths = time.time()
    rpaths = gengine.reconstruct_paths(db, case)
    path_runtime = time.time() - t_paths
    hop_true = {(alias.get(t["src"], t["src"]), alias.get(t["dst"], t["dst"])): t for t in truth["transactions"] if t["hop"] > 0}
    observable_hop_edges = {(alias.get(t["src"], t["src"]), alias.get(t["dst"], t["dst"])) for t in observable if t["hop"] > 0}
    true_chains = []
    for tp in truth["paths"]:
        accts = [alias.get(a, a) for a in tp["accounts"]]
        chain = []
        for a, b in zip(accts, accts[1:]):
            if (a, b) in observable_hop_edges and (not chain or chain[-1][1] == a):
                chain.append((a, b))
            else:
                break
        if chain:
            true_chains.append(chain)
    recon_chains = [list(zip(pth["accounts"], pth["accounts"][1:])) for pth in rpaths]
    covered = sum(1 for ch in true_chains if any(all(e in rc for e in ch) for rc in recon_chains))
    false_paths = sum(1 for rc in recon_chains if any(e not in hop_true for e in rc))
    complete = [pth for pth in rpaths if pth["status"] == "complete"]
    path_metrics = {"coverage": round(covered / len(true_chains), 4) if true_chains else 1.0,
                    "false_path_rate": round(false_paths / len(rpaths), 4) if rpaths else 0.0,
                    "amount_conservation_mean": round(sum(pth["conservation_ratio"] or 0 for pth in complete) / len(complete), 4) if complete else None,
                    "temporal_consistency_rate": round(sum(1 for pth in rpaths if pth["temporal_consistent"]) / len(rpaths), 4) if rpaths else 1.0,
                    "unresolved_hop_rate": round(sum(1 for pth in rpaths if pth["status"] == "unresolved") / len(rpaths), 4) if rpaths else 0.0,
                    "paths": len(rpaths), "runtime_seconds": round(path_runtime, 4)}
    # --- entity resolution: alias edges correct (vpa<->acct of same account) vs wrong
    er_tp = er_fp = 0
    vpa_to_acct = {a["vpa"]: a["acct_no"] for a in truth["accounts"]}
    for r in rels:
        if r.relationship_type == "SAME_ACCOUNT_IDENTIFIER":
            a, b = ents[r.source_entity_id].key, ents[r.target_entity_id].key
            ok = vpa_to_acct.get(a) == b or vpa_to_acct.get(b) == a or a == b
            er_tp += ok
            er_fp += (not ok)
    er_fn = max(0, len({a["vpa"] for a in truth["accounts"] if a["role"].startswith("mule")}) - er_tp)
    entity_res = prf(er_tp, er_fp, er_fn)
    merged_similar = sum(1 for r in rels if r.relationship_type == "SIMILAR_NAME" and r.evidence_level.value in {"derived", "corroborated", "directly_observed"})
    # --- false links: any asserted (non-candidate) common-operator/ownership relation between campaign and decoy domains
    decoys = {d["domain"] for d in truth["domains"] if d["role"] == "decoy"}
    camp = truth["params"]["campaign_domain"]
    false_links = 0
    shared_ip_pairs = 0
    for r in rels:
        a, b = ents[r.source_entity_id].key, ents[r.target_entity_id].key
        if {a, b} & decoys and camp in {a, b} and r.relationship_type in {"COMMON_OPERATOR", "COMMON_OWNER", "SHARED_INFRASTRUCTURE"}:
            shared_ip_pairs += 1
            if r.evidence_level.value != "candidate" or r.relationship_type != "SHARED_INFRASTRUCTURE":
                false_links += 1
    # --- temporal validity: planted stale observations must be marked stale/contradicted
    stale_planted = [c for c in truth["chaos"] if c["kind"] == "stale_conflicting_dns"] + [d for d in truth["domains"] if d["role"] == "campaign_stale"]
    stale_marked = sum(1 for r in rels if r.relationship_type == "RESOLVES_TO" and r.evidence_level.value == "stale")
    temporal_acc = (min(stale_marked, len(stale_planted)) / len(stale_planted)) if stale_planted else 1.0
    # --- evidence coverage: share of non-candidate edges with >=1 evidence item with a locator
    ev_count = {r.relationship_id: 0 for r in db.execute(select(RelationshipEvidence).join(Relationship).where(Relationship.case_id == case.id)).scalars()}
    for re_ in db.execute(select(RelationshipEvidence).join(Relationship).where(Relationship.case_id == case.id)).scalars():
        ev_count[re_.relationship_id] += 1
    substantive = [r for r in rels if r.relationship_type not in {"DOCUMENTS"}]
    covered = sum(1 for r in substantive if ev_count.get(r.id, 0) > 0 or r.evidence_level.value == "candidate")
    evidence_cov = covered / len(substantive) if substantive else 1.0
    # --- counter-evidence recall: planted chaos kinds that have a corresponding counter-evidence record
    counters = {c.kind for c in db.execute(select(CounterEvidence).where(CounterEvidence.case_id == case.id)).scalars()}
    planted = {"duplicate_row": "duplicate_reference", "ambiguous_date": "ambiguous_event_time", "similar_name": "approximate_name_identifiers_conflict",
               "stale_conflicting_dns": "observation_outside_event_window"}
    planted_kinds = {planted[c["kind"]] for c in truth["chaos"] if c["kind"] in planted}
    if decoys:
        planted_kinds.add("multi_tenant_infrastructure")
    ce_recall = (len(planted_kinds & counters) / len(planted_kinds)) if planted_kinds else 1.0
    # --- triage (rules) on mule accounts
    feats = gengine.account_features(db, case)
    tp = fp = fn = 0
    for acct, f in feats.items():
        pred = gengine.rules_triage(f)["label"] == "possible_mule_pattern_requires_review"
        is_mule = role.get(acct, "").startswith("mule") or role.get(acct) == "exit"
        tp += pred and is_mule
        fp += pred and not is_mule
        fn += (not pred) and is_mule
    return {"field_extraction": field, "transaction_path": path, "path_metrics": path_metrics, "entity_resolution": entity_res, "similar_names_wrongly_merged": merged_similar,
            "false_link_count": false_links, "shared_ip_false_link_rate": round(false_links / shared_ip_pairs, 4) if shared_ip_pairs else 0.0,
            "shared_ip_pairs": shared_ip_pairs, "temporal_validity_accuracy": round(temporal_acc, 4), "evidence_coverage": round(evidence_cov, 4),
            "counter_evidence_recall": round(ce_recall, 4), "triage_rules": prf(tp, fp, fn), "eval_seconds": round(time.time() - t0, 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--seed-start", type=int, default=500, help="use 700+ for the frozen held-out range")
    ap.add_argument("--heldout-scenario", default="", help="scenario family reported separately as held-out (never used for tuning)")
    ap.add_argument("--size", default="small")
    ap.add_argument("--out", default=str(ROOT / "tests" / "benchmark" / "results" / "benchmark_summary.json"))
    args = ap.parse_args()
    Base.metadata.create_all(bind=engine)
    seeds = list(range(args.seed_start, args.seed_start + args.seeds))
    per_case = []
    t_start = time.time()
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == "bench@local").one_or_none() or User(email="bench@local", display_name="bench", password_hash="x", role=Role.admin)
        db.add(user)
        db.flush()
        for seed in seeds:
            for sc in SCENARIOS:
                for diff in DIFFICULTIES:
                    for cfg, opts in CONFIGS.items():
                        t0 = time.time()
                        case, scen, outcomes, _ = generate_case(db, user, scenario_type=sc, difficulty=diff, size=args.size, seed=seed, **opts)
                        gen_s = time.time() - t0
                        truth = sealed_store.unseal(scen.sealed_truth_ref)
                        m = evaluate(db, case, truth, cfg)
                        m.update({"config": cfg, "scenario": sc, "difficulty": diff, "seed": seed, "ingest_seconds": round(gen_s, 3),
                                  "files": len(outcomes), "warnings": sum(len(o.parse_run.warnings or []) for o in outcomes if o.parse_run)})
                        per_case.append(m)
                        db.commit()
    # reproducibility: same seed twice -> identical public file hashes
    from app.synthetic.artifacts import build_bundle
    from app.synthetic.generator import Generator
    a, _, _ = build_bundle(Generator("phishing_to_mule", "adversarial", "small", 500))
    b, _, _ = build_bundle(Generator("phishing_to_mule", "adversarial", "small", 500))
    reproducible = all(a[k] == b[k] for k in a)

    def agg(rows, key):
        vals = [r[key] if not isinstance(r[key], dict) else r[key]["f1"] for r in rows]
        return round(statistics.mean(vals), 4) if vals else None

    def agg_path(rows):
        keys = ("coverage", "false_path_rate", "amount_conservation_mean", "temporal_consistency_rate", "unresolved_hop_rate", "runtime_seconds")
        out = {}
        for k in keys:
            vals = [r["path_metrics"][k] for r in rows if r["path_metrics"].get(k) is not None]
            if vals:
                m = statistics.mean(vals)
                # bootstrap 95% interval (deterministic seed)
                import random as _r
                rng = _r.Random(0)
                bs = sorted(statistics.mean(rng.choices(vals, k=len(vals))) for _ in range(300))
                out[k] = {"mean": round(m, 4), "ci95": [round(bs[7], 4), round(bs[292], 4)], "n": len(vals)}
        return out

    summary = {"generator_version": GENERATOR_VERSION, "seeds": seeds, "size": args.size, "cases_per_config": len(per_case) // len(CONFIGS),
               "total_runs": len(per_case), "reproducible_same_seed": reproducible, "wall_seconds": round(time.time() - t_start, 1), "by_config": {}, "by_difficulty_full": {}}
    for cfg in CONFIGS:
        rows = [r for r in per_case if r["config"] == cfg]
        summary["by_config"][cfg] = {k: agg(rows, k) for k in ("field_extraction", "transaction_path", "entity_resolution", "false_link_count", "shared_ip_false_link_rate",
                                                                "temporal_validity_accuracy", "evidence_coverage", "counter_evidence_recall", "triage_rules", "ingest_seconds", "eval_seconds")}
        summary["by_config"][cfg]["path_metrics"] = agg_path(rows)
        summary["by_config"][cfg]["similar_names_wrongly_merged_total"] = sum(r["similar_names_wrongly_merged"] for r in rows)
        summary["by_config"][cfg]["false_links_total"] = sum(r["false_link_count"] for r in rows)
    for diff in DIFFICULTIES:
        rows = [r for r in per_case if r["config"] == "D_ps05x_full" and r["difficulty"] == diff]
        summary["by_difficulty_full"][diff] = {k: agg(rows, k) for k in ("field_extraction", "transaction_path", "false_link_count", "temporal_validity_accuracy", "counter_evidence_recall")}
        summary["by_difficulty_full"][diff]["path_metrics"] = agg_path(rows)
    summary["by_scenario_full"] = {}
    for sc in SCENARIOS:
        rows = [r for r in per_case if r["config"] == "D_ps05x_full" and r["scenario"] == sc]
        summary["by_scenario_full"][sc] = {"transaction_path_f1": agg(rows, "transaction_path"), "path_metrics": agg_path(rows), "held_out": sc == args.heldout_scenario}
    summary["path_algorithm_version"] = gengine.PATH_ALGORITHM_VERSION
    summary["seed_start"] = args.seed_start
    summary["heldout_scenario"] = args.heldout_scenario or None
    summary["statement"] = "All metrics are measured on synthetic, sealed-truth cases. F1 is not accuracy. No real-world transfer is claimed."
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "per_case": per_case}, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
