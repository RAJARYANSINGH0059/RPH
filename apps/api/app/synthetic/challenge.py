"""Blind investigation challenge: an analyst records conclusions for a synthetic case; only after the submission is locked is the
sealed truth read (by this module alone) to score the exercise. Never callable for non-synthetic cases; the reveal is a summary
of roles/paths/decoys, labelled SYNTHETIC EVALUATION, and every reveal is audited."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import AnalysisRun, Case, SyntheticScenario, User, Relationship
from app.services import audit
from app.synthetic import sealed_store

CHALLENGE_VERSION = "1.0.0"


def submission(db: Session, case: Case, user: User) -> AnalysisRun | None:
    return db.execute(select(AnalysisRun).where(AnalysisRun.case_id == case.id, AnalysisRun.kind == "challenge_submission", AnalysisRun.created_by == user.id)
                      .order_by(AnalysisRun.created_at.desc())).scalars().first()


def submit(db: Session, case: Case, user: User, decisions: dict) -> AnalysisRun:
    if not case.is_synthetic:
        raise ValueError("challenge mode exists only for synthetic cases")
    run = AnalysisRun(case_id=case.id, kind="challenge_submission", algorithm_version=CHALLENGE_VERSION, inputs={"decisions": decisions, "locked_at": datetime.now(timezone.utc).isoformat()},
                      outputs={}, created_by=user.id, status="locked")
    db.add(run)
    db.flush()
    audit.record(db, "challenge.submitted", actor_id=user.id, case_id=case.id, target_type="analysis_run", target_id=run.id, detail={"keys": sorted(decisions)})
    return run


def reveal(db: Session, case: Case, user: User) -> dict:
    """Score the locked submission against sealed truth. Requires a prior submission by this user."""
    if not case.is_synthetic:
        raise ValueError("no ground truth exists for non-synthetic cases")
    sub = submission(db, case, user)
    if sub is None:
        raise PermissionError("submit your conclusions first; the sealed truth is revealed only after the exercise is locked")
    scen = db.execute(select(SyntheticScenario).where(SyntheticScenario.case_id == case.id)).scalar_one_or_none()
    if scen is None:
        raise LookupError("no sealed scenario for this case")
    truth = sealed_store.unseal(scen.sealed_truth_ref)
    dec = (sub.inputs or {}).get("decisions", {})
    mules = set(truth.get("mule_accounts") or [])
    victims = {p["victim"] for p in truth.get("paths", [])}
    unrelated = {a["acct_no"] for a in truth.get("accounts", []) if a.get("role") == "unrelated"}
    flagged = set(dec.get("mule_pattern_accounts") or [])
    tp = len(flagged & mules)
    innocent_flagged = sorted(flagged & (victims | unrelated))
    decoys = {e["dst"] for e in truth.get("false_edges", []) if e.get("type") == "COMMON_OPERATOR"}
    asserted_co = set(dec.get("common_operator_domains") or [])
    paths_sys = engine.reconstruct_paths(db, case)
    true_paths = [tuple(p["accounts"]) for p in truth.get("paths", [])]
    sys_paths = [tuple(p["accounts"]) for p in paths_sys]
    covered = sum(1 for tp_ in true_paths if any(tp_[:len(sp)] == sp[:len(tp_)] or sp[:2] == tp_[:2] for sp in sys_paths))
    result = {"label": "SYNTHETIC EVALUATION — scored against sealed ground truth after submission; not real-world accuracy", "submitted_at": (sub.inputs or {}).get("locked_at"),
              "your_decisions": dec,
              "scores": {"mule_accounts_identified": tp, "mule_accounts_total": len(mules), "mule_recall": round(tp / len(mules), 3) if mules else None,
                         "mule_precision": round(tp / len(flagged), 3) if flagged else None, "innocent_or_victim_accounts_flagged": innocent_flagged,
                         "decoy_domains_asserted_as_common_operator": sorted(asserted_co & decoys), "decoy_rejection": (len(decoys - asserted_co) / len(decoys)) if decoys else None,
                         "system_path_coverage_of_true_chains": round(covered / len(true_paths), 3) if true_paths else None},
              "truth_summary": {"victims": sorted(victims), "collection_and_layering_accounts": sorted(mules), "unrelated_accounts": sorted(unrelated), "campaign_domains": [d["domain"] for d in truth.get("domains", []) if d["role"].startswith("campaign")],
                                "decoy_domains": sorted(decoys), "planted_chaos": sorted({c["kind"] for c in truth.get("chaos", [])}), "rotation": (truth.get("params") or {}).get("rotation"),
                                "missing_period": (truth.get("params") or {}).get("missing_period"), "control_hypothesis": (truth.get("params") or {}).get("control"),
                                "simulated_allocation_sample": ((truth.get("params") or {}).get("simulated_allocation") or [])[:3]},
              "note": "Roles are generator labels inside a fictional scenario. They say nothing about any real person."}
    result["baseline_comparison"] = compare_with_truth(db, case, truth)
    sub.outputs = {"scores": result["scores"], "revealed_at": datetime.now(timezone.utc).isoformat()}
    audit.record(db, "challenge.revealed", actor_id=user.id, case_id=case.id, target_type="analysis_run", target_id=sub.id, detail=result["scores"])
    return result


def compare_with_truth(db: Session, case: Case, truth: dict) -> dict:
    """Graph-only baseline vs PS05-X rule triage on the same case, both scored against the sealed truth passed in by the caller
    (the locked reveal or the benchmark runner). Synthetic evaluation only."""
    from app.services import baseline
    alias = engine.alias_map(db, case)
    canon = lambda a: alias.get(a, a)  # noqa: E731
    mules = {canon(a) for a in truth.get("mule_accounts") or []}
    innocents = {canon(p["victim"]) for p in truth.get("paths", [])} | {canon(a["acct_no"]) for a in truth.get("accounts", []) if a.get("role") == "unrelated"}
    decoys = {e["dst"] for e in truth.get("false_edges", []) if e.get("type") == "COMMON_OPERATOR"} | {e["src"] for e in truth.get("false_edges", []) if e.get("type") == "COMMON_OPERATOR" and e.get("src")}
    b = baseline.run(db, case)
    b_flagged = {canon(a) for a in b["flagged_accounts"]}
    feats = engine.account_features(db, case)
    s_flagged = {canon(a) for a in feats if engine.rules_triage(feats[a])["label"].startswith("possible")}
    # accounts PS05-X places downstream on a reconstructed (reference/amount/time-checked) fund path: the safeguarded analogue of traversal
    p_flagged = {canon(a) for p in engine.reconstruct_paths(db, case) for a in p["accounts"][1:]}
    co_edges = db.execute(select(Relationship).where(Relationship.case_id == case.id, Relationship.relationship_type == "COMMON_OPERATOR")).scalars().all()

    def score(flagged: set[str]) -> dict:
        return {"flagged_accounts": len(flagged), "mule_recall": round(len(flagged & mules) / len(mules), 3) if mules else None,
                "mule_precision": round(len(flagged & mules) / len(flagged), 3) if flagged else None, "innocent_or_victim_accounts_flagged": len(flagged & innocents)}

    return {"label": "SYNTHETIC — same case, same sealed truth; the baseline is the deliberately unsafeguarded comparison point",
            "baseline_definition": b["definition"],
            "graph_only_baseline": {**score(b_flagged), "common_operator_pairs_asserted": len(b["asserted_common_operator_pairs"]),
                                    "decoy_pairs_asserted": sum(1 for a, c in b["asserted_common_operator_pairs"] if a in decoys or c in decoys)},
            "ps05x": {**score(s_flagged), "common_operator_pairs_asserted": len(co_edges), "decoy_pairs_asserted": 0 if not co_edges else None,
                      "note": "rule triage is a cue, not a finding; shared infrastructure stays a CANDIDATE with alternatives"},
            "ps05x_paths": {**score(p_flagged), "common_operator_pairs_asserted": len(co_edges),
                            "note": "accounts downstream on reconstructed fund paths (reference, amount and time checked; unresolved hops explicit) — the like-for-like comparison with naive traversal"}}
