"""Benchmark v2: next-wave metrics scored against sealed truth on synthetic cases.

Metrics (per case, then mean with bootstrap 95% CI):
  payment-instruction extraction recall/precision and instruction->transaction match precision
  attribution interval coverage, width ratio and false-exact rate (vs the generator's sealed simulated allocation)
  evidence-gap recognition (planted missing statement period) and false observed-zero rate
  extraction-error detection (planted balance breaks found at row level)
  innocent-holder false attribution (role review never asserts knowing participation; rules triage flags on victims/unrelated)
  decoy rejection (no COMMON_OPERATOR under safeguards)
  counterfactual robustness (shared_hosting / stale_dns STABLE; missing_intermediary_statement CHANGED)
  proof-certificate reproducibility (offline verifier PASS) and tamper detection (modified file -> FAIL)
  campaign identifier-rotation recall and benign false-cluster rate
  runtime per analysis

Usage: python tests/benchmark/run_benchmark_v2.py [--seeds 6] [--seed-start 1500] [--out ...]
Everything is synthetic; nothing here is real-world accuracy.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "scripts"))
_TMP = tempfile.mkdtemp(prefix="ps05x_bench2_")
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(_TMP, "bench.db").replace("\\", "/"))
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "data"))
os.environ.setdefault("BENCHMARK_STORE_DIR", os.path.join(_TMP, "sealed"))
os.environ.setdefault("OCR_ENGINE", "off")

from sqlalchemy import select  # noqa: E402

from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.graph import engine as gengine  # noqa: E402
from app.models import PaymentInstruction, Relationship, Role, SourceFile, Transaction, User  # noqa: E402
from app.services import bounded_flow, campaign, counterfactual, coverage, integrity, payment_bridge, proof, roles  # noqa: E402
from app.services.storage import get_storage  # noqa: E402
from app.synthetic import sealed_store  # noqa: E402
from app.services import baseline
from app.synthetic import challenge
from app.synthetic.generator import GENERATOR_VERSION  # noqa: E402
from app.synthetic.service import generate_case  # noqa: E402
from verify_proof import verify  # noqa: E402

SCENARIOS = ["desert_mirage", "commingled_funds", "identifier_rotation_campaign", "benign_lookalike", "compromised_account"]


def ci(xs: list[float], n_boot: int = 400, seed: int = 7) -> dict:
    xs = [x for x in xs if x is not None]
    if not xs:
        return {"mean": None, "n": 0}
    rng = random.Random(seed)
    means = sorted(statistics.fmean(rng.choices(xs, k=len(xs))) for _ in range(n_boot))
    return {"mean": round(statistics.fmean(xs), 4), "ci95": [round(means[int(0.025 * n_boot)], 4), round(means[int(0.975 * n_boot)], 4)], "min": round(min(xs), 4), "max": round(max(xs), 4), "n": len(xs)}


def score_case(db, case, truth: dict, user) -> dict:
    row: dict = {}
    params = truth.get("params", {})
    alias = gengine.alias_map(db, case)
    t0 = time.time()
    # ---- payment instructions
    expected = params.get("payment_instructions", [])
    pis = db.execute(select(PaymentInstruction).where(PaymentInstruction.case_id == case.id)).scalars().all()
    if expected:
        exp_refs = {e["payload"].split("tr=")[1].split("&")[0] for e in expected}
        got_refs = {p.reference for p in pis if p.reference}
        row["pi_recall"] = len(exp_refs & got_refs) / len(exp_refs)
        row["pi_precision"] = len(exp_refs & got_refs) / len(got_refs) if got_refs else 0.0
        ok = 0
        for p in pis:
            res = payment_bridge.match_instruction(db, case, p, persist=False)
            best = res["candidates"][0] if res["candidates"] else None
            if res["match_status"].startswith("EXACT") and best and (best["transaction"]["reference"] or "").upper() == (p.reference or "").upper():
                ok += 1
        row["pi_match_precision"] = ok / len(pis) if pis else None
    # ---- attribution bounds vs sealed simulated allocation
    alloc = params.get("simulated_allocation") or []
    if alloc:
        paths = gengine.reconstruct_paths(db, case)
        covered, widths, false_exact, n = 0, [], 0, 0
        for i, p in enumerate(paths):
            if len(p["accounts"]) < 3 or p["accounts"][1] not in {alias.get(a["from"], a["from"]) for a in alloc}:
                continue
            victim = p["accounts"][0]
            bf = bounded_flow.analyse(db, case, path_index=i)
            for h in bf.get("hops", []):
                if h.get("minimum_attributable_minor") is None:
                    continue
                tx = db.get(Transaction, h["transaction_id"])
                tru = next((a for a in alloc if a["ref"] == tx.external_reference), None)
                if tru is None:
                    continue
                true_v = tru["victim_origin_by_victim"].get(victim, 0)
                n += 1
                inside = h["minimum_attributable_minor"] <= true_v <= h["maximum_attributable_minor"]
                covered += int(inside)
                widths.append((h["maximum_attributable_minor"] - h["minimum_attributable_minor"]) / max(1, h["observed_transfer_minor"]))
                if h["exact"] and not inside:
                    false_exact += 1
        if n:
            row["attribution_coverage"] = covered / n
            row["attribution_width_ratio"] = statistics.fmean(widths)
            row["attribution_false_exact_rate"] = false_exact / n
            row["attribution_hops_scored"] = n
    # ---- coverage gap recognition
    mp = params.get("missing_period")
    cov = coverage.coverage_report(db, case)
    if mp:
        st = [s for s in cov["statements"] if s["subject"] == mp["account"]]
        row["gap_detected"] = 1.0 if any(s["state"] == "PARTIAL_COVERAGE" and s["gaps"] for s in st) else 0.0
        row["false_observed_zero"] = 1.0 if any(s["observed_zero_months"] for s in st) else 0.0
    # ---- extraction error detection (planted balance mismatch rows)
    planted = [c for c in truth.get("chaos", []) if c["kind"] == "balance_mismatch"]
    if planted:
        rep = integrity.case_report(db, case)
        found = 0
        for c in planted:
            for f in rep["files"]:
                sf = f["statement_forensics"]
                if sf and c["account"] in sf["accounts"] and any(a["kind"] == "running_balance_break" for a in sf["anomalies"]):
                    found += 1
                    break
        row["balance_break_recall"] = found / len(planted)
    # ---- innocent-holder false attribution
    victims = {p["victim"] for p in truth.get("paths", [])}
    unrelated = {a["acct_no"] for a in truth["accounts"] if a["role"] == "unrelated"}
    feats = gengine.account_features(db, case)
    innocents = [a for a in feats if a in victims | unrelated]
    if innocents:
        row["innocent_triage_flag_rate"] = sum(1 for a in innocents if gengine.rules_triage(feats[a])["label"].startswith("possible")) / len(innocents)
    asserted = 0
    for a in list(feats)[:12]:
        rr = roles.get_or_create(db, case, user, a)
        if (rr.propositions or {}).get("P6", {}).get("status") == "supported":
            asserted += 1
    row["knowing_participation_auto_asserted"] = asserted  # must be 0 by construction
    # ---- decoy rejection
    rels = db.execute(select(Relationship).where(Relationship.case_id == case.id)).scalars().all()
    row["common_operator_edges"] = sum(1 for r in rels if r.relationship_type == "COMMON_OPERATOR")
    row["shared_infra_candidates"] = sum(1 for r in rels if r.relationship_type == "SHARED_INFRASTRUCTURE")
    # ---- counterfactual robustness
    if truth.get("paths"):
        lab = {prof: counterfactual.run(db, case, profile=prof, seed=42001)["robustness"] for prof in ("shared_hosting", "stale_dns", "missing_intermediary_statement", "ocr_substitution")}
        row["lab_shared_hosting_stable"] = 1.0 if lab["shared_hosting"] == "STABLE" else 0.0
        row["lab_stale_dns_stable"] = 1.0 if lab["stale_dns"] == "STABLE" else 0.0
        row["lab_missing_statement_changed"] = 1.0 if lab["missing_intermediary_statement"] in {"CHANGED", "FRAGILE"} else 0.0
        row["lab_ocr_substitution_sensitive"] = 1.0 if lab["ocr_substitution"] in {"CHANGED", "FRAGILE"} else 0.0
    # ---- proof certificate reproducibility + tamper detection
    paths = gengine.reconstruct_paths(db, case)
    if paths:
        m = proof.build_manifest(db, case, 0)
        fdir = Path(_TMP) / f"files_{case.id[:8]}"
        fdir.mkdir(exist_ok=True)
        for f in m["source_files"]:
            sf = db.get(SourceFile, f["id"])
            (fdir / f["name"]).write_bytes(get_storage().get(sf.storage_key))
        res = verify(m, fdir, None)
        row["proof_verify_pass"] = 1.0 if res["verdict"] == "PASS" else 0.0
        target = fdir / m["source_files"][0]["name"]
        target.write_bytes(target.read_bytes() + b"\n#tamper")
        row["proof_tamper_detected"] = 1.0 if verify(m, fdir, None)["verdict"] == "FAIL" else 0.0
    # ---- graph-only baseline vs PS05-X triage on the same case (sealed truth passed in by this scorer only)
    cmpb = challenge.compare_with_truth(db, case, truth)
    for src, pref in ((cmpb["graph_only_baseline"], "baseline"), (cmpb["ps05x"], "ps05x"), (cmpb["ps05x_paths"], "ps05x_path")):
        if src.get("mule_recall") is not None:
            row[f"{pref}_mule_recall"] = src["mule_recall"]
        if src.get("mule_precision") is not None:
            row[f"{pref}_mule_precision"] = src["mule_precision"]
        row[f"{pref}_innocent_flagged"] = src["innocent_or_victim_accounts_flagged"]
        row[f"{pref}_common_operator_pairs"] = src["common_operator_pairs_asserted"]
    row["runtime_s"] = round(time.time() - t0, 2)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=6)
    ap.add_argument("--seed-start", type=int, default=1500)
    ap.add_argument("--out", default=str(ROOT / "tests" / "benchmark" / "results" / "benchmark_v2_summary.json"))
    a = ap.parse_args()
    Base.metadata.create_all(bind=engine)
    t_all = time.time()
    rows: list[dict] = []
    campaign_rows: list[dict] = []
    with SessionLocal() as db:
        user = User(email="bench2@demo.local", display_name="bench", password_hash="x", role=Role.admin)
        db.add(user)
        db.commit()
        for seed in range(a.seed_start, a.seed_start + a.seeds):
            cases_by_sc = {}
            for sc in SCENARIOS:
                diff = "identifier_rotation" if sc == "identifier_rotation_campaign" else "messy"
                case, scen, _, _ = generate_case(db, user, scenario_type=sc, difficulty=diff, size="small", seed=seed)
                db.commit()
                truth = sealed_store.unseal(scen.sealed_truth_ref)
                try:
                    row = score_case(db, case, truth, user)
                except Exception as exc:  # record failures instead of hiding them
                    row = {"error": f"{type(exc).__name__}: {exc}"}
                rows.append({"scenario": sc, "seed": seed, **row})
                cases_by_sc[sc] = case
                db.commit()
            # campaign: rotation pair (mirage vs rotated campaign) and benign pair
            cmp = campaign.compare_cases(db, user, [cases_by_sc["desert_mirage"].id, cases_by_sc["identifier_rotation_campaign"].id, cases_by_sc["benign_lookalike"].id])
            for p in cmp["pairs"]:
                kind = "benign_pair" if cases_by_sc["benign_lookalike"].id in (p["case_a"], p["case_b"]) else "rotation_pair"
                campaign_rows.append({"seed": seed, "kind": kind, "status": p["relationship_status"], "score": p["aggregate_score_not_probability"], "rotation_candidate": p["identifier_rotation"]["rotation_candidate"]})
    metrics = {}
    keys = sorted({k for r in rows for k in r if k not in {"scenario", "seed", "error"}})
    for k in keys:
        metrics[k] = ci([r[k] for r in rows if k in r and isinstance(r[k], (int, float))])
    rot = [r for r in campaign_rows if r["kind"] == "rotation_pair"]
    ben = [r for r in campaign_rows if r["kind"] == "benign_pair"]
    camp = {"rotation_recall": ci([1.0 if r["status"].startswith("CANDIDATE") else 0.0 for r in rot]), "rotation_candidate_rate": ci([1.0 if r["rotation_candidate"] else 0.0 for r in rot]),
            "benign_false_cluster_rate": ci([1.0 if r["status"].startswith("CANDIDATE_PATTERN_SIMILARITY_HIGH") else 0.0 for r in ben]), "benign_medium_rate": ci([1.0 if "MEDIUM" in r["status"] else 0.0 for r in ben])}
    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "generator_version": GENERATOR_VERSION, "seeds": list(range(a.seed_start, a.seed_start + a.seeds)), "scenarios": SCENARIOS,
           "cases": len(rows), "sample_size": {"cases": len(rows), "seeds": a.seeds, "scenario_families": len(SCENARIOS), "cases_per_family": a.seeds, "note": "small deterministic sample; metrics carry bootstrap 95% CIs and min/max"},
           "baseline_definition": baseline.DEFINITION, "errors": [r for r in rows if "error" in r], "metrics": metrics, "campaign": camp, "rows": rows, "campaign_rows": campaign_rows, "wall_seconds": round(time.time() - t_all, 1),
           "note": "Synthetic benchmark scored against sealed truth after analysis; F1/rates are not real-world accuracy. Coverage = sealed allocation inside [min,max]; width ratio = interval / transfer."}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(json.dumps({k: v.get("mean") for k, v in metrics.items()}, indent=1))
    print("campaign:", {k: v.get("mean") for k, v in camp.items()})
    print("errors:", len(out["errors"]), "wall", out["wall_seconds"], "s ->", a.out)


if __name__ == "__main__":
    main()
