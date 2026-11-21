"""Train and evaluate the account-triage model with scenario-level splits.

Usage: python ml/training/train.py [--seeds 12] [--size small]
Outputs: ml/artifacts/triage_model.joblib (+ .sha256), ml/artifacts/feature_schema.json, ml/evaluation/metrics.json
The model is retained ONLY if it beats the rules baseline on held-out scenarios (F1 and PR-AUC). Otherwise the
artefact is removed and metrics.json records why.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ml" / "training"))
from dataset import DATASET_VERSION, FEATURES, build_rows  # noqa: E402

ART = ROOT / "ml" / "artifacts"
EVAL = ROOT / "ml" / "evaluation"


def metrics(y, p, s) -> dict:
    from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score)
    out = {"precision": float(precision_score(y, p, zero_division=0)), "recall": float(recall_score(y, p, zero_division=0)),
           "f1": float(f1_score(y, p, zero_division=0)), "confusion_matrix": confusion_matrix(y, p, labels=[0, 1]).tolist(), "n": int(len(y)),
           "positives": int(sum(y))}
    if s is not None and len(set(y)) > 1:
        out["pr_auc"] = float(average_precision_score(y, s))
        out["roc_auc"] = float(roc_auc_score(y, s))
        out["brier"] = float(brier_score_loss(y, s))
        bins = np.linspace(0, 1, 6)
        cal = []
        for lo, hi in zip(bins[:-1], bins[1:]):
            m = (s >= lo) & (s < hi + (1e-9 if hi == 1 else 0))
            if m.sum():
                cal.append({"bin": f"{lo:.1f}-{hi:.1f}", "mean_score": float(s[m].mean()), "observed_rate": float(np.mean(np.array(y)[m])), "n": int(m.sum())})
        out["calibration"] = cal
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=12)
    ap.add_argument("--size", default="small")
    args = ap.parse_args()
    t0 = time.time()
    seeds = list(range(1000, 1000 + args.seeds))
    rows = build_rows(seeds, size=args.size)
    scen_ids = sorted({r["scenario_id"] for r in rows})
    # scenario-level split: by seed index (train 60% / val 20% / test 20%) AND hold out one typology entirely for the test set
    held_out_typology = "qr_marketplace"
    n = len(seeds)
    tr_seeds, va_seeds, te_seeds = set(seeds[: int(n * 0.6)]), set(seeds[int(n * 0.6): int(n * 0.8)]), set(seeds[int(n * 0.8):])

    def part(r):
        if r["scenario_type"] == held_out_typology:
            return "test"
        return "train" if r["seed"] in tr_seeds else ("val" if r["seed"] in va_seeds else "test")

    splits = {k: [r for r in rows if part(r) == k] for k in ("train", "val", "test")}
    X = {k: np.array([[float(r[f]) for f in FEATURES] for r in v]) for k, v in splits.items()}
    y = {k: np.array([r["label"] for r in v]) for k, v in splits.items()}

    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    candidates = {
        "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000, class_weight="balanced", random_state=0)),
        "random_forest": RandomForestClassifier(n_estimators=300, max_depth=8, class_weight="balanced", random_state=0, n_jobs=1),
        "hist_gradient_boosting": HistGradientBoostingClassifier(max_depth=4, learning_rate=0.08, max_iter=200, class_weight="balanced", random_state=0),
    }
    report = {"dataset_version": DATASET_VERSION, "generator_version": rows[0]["rules"] and __import__("app.synthetic.generator", fromlist=["GENERATOR_VERSION"]).GENERATOR_VERSION,
              "seeds": seeds, "size": args.size, "features": FEATURES, "held_out_typology": held_out_typology,
              "split_counts": {k: {"rows": len(v), "positives": int(sum(r["label"] for r in v)), "scenarios": len({r["scenario_id"] for r in v})} for k, v in splits.items()},
              "label_definition": "1 = synthetically generated mule-pattern participant (mule_l1/mule_l2/exit); 0 = victim/unrelated. Not a criminality label.",
              "models": {}}
    # rules baseline
    for k in ("val", "test"):
        p = np.array([1 if r["rules"]["label"] == "possible_mule_pattern_requires_review" else 0 for r in splits[k]])
        s = np.array([r["rules"]["heuristic_score"] / 100 for r in splits[k]])
        report["models"].setdefault("rules_baseline", {})[k] = metrics(y[k], p, s)
    fitted = {}
    for name, model in candidates.items():
        model.fit(X["train"], y["train"])
        fitted[name] = model
        for k in ("val", "test"):
            s = model.predict_proba(X[k])[:, 1]
            report["models"].setdefault(name, {})[k] = metrics(y[k], (s >= 0.5).astype(int), s)
    # model selection on VALIDATION only; compared to baseline on TEST afterwards
    best = max(candidates, key=lambda n: (report["models"][n]["val"].get("pr_auc", 0), report["models"][n]["val"]["f1"]))
    base_t, best_t = report["models"]["rules_baseline"]["test"], report["models"][best]["test"]
    improves = best_t["f1"] > base_t["f1"] and best_t.get("pr_auc", 0) > base_t.get("pr_auc", 0)
    # subgroup robustness by difficulty (test split, selected model)
    sub = {}
    for diff in sorted({r["difficulty"] for r in splits["test"]}):
        idx = [i for i, r in enumerate(splits["test"]) if r["difficulty"] == diff]
        if idx:
            s = fitted[best].predict_proba(X["test"][idx])[:, 1]
            sub[diff] = metrics(y["test"][idx], (s >= 0.5).astype(int), s)
    report.update({"selected_model": best, "selection_rule": "highest validation PR-AUC then F1", "retained": bool(improves),
                   "retention_rule": "retained only if test F1 AND test PR-AUC exceed the rules baseline on held-out scenarios",
                   "robustness_by_difficulty_test": sub, "training_seconds": round(time.time() - t0, 1),
                   "synthetic_only_statement": "All training and evaluation data are synthetic. No real police or bank data were used. Metrics do not transfer to operational data."})
    ART.mkdir(parents=True, exist_ok=True)
    EVAL.mkdir(parents=True, exist_ok=True)
    model_path = ART / "triage_model.joblib"
    if improves:
        import joblib
        joblib.dump({"model": fitted[best], "features": FEATURES, "model_name": best, "dataset_version": DATASET_VERSION, "threshold": 0.5}, model_path)
        digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
        (ART / "triage_model.sha256").write_text(digest + "\n")
        (ART / "feature_schema.json").write_text(json.dumps({"features": FEATURES, "dataset_version": DATASET_VERSION, "model_name": best, "threshold": 0.5,
                                                              "sha256": digest, "output_semantics": "triage score; requires human review; not a probability of guilt"}, indent=1))
        report["artifact"] = {"path": str(model_path.relative_to(ROOT)), "sha256": digest}
    else:
        for p in (model_path, ART / "triage_model.sha256", ART / "feature_schema.json"):
            if p.exists():
                p.unlink()
        report["artifact"] = None
        report["why_not_retained"] = f"{best} did not beat the rules baseline on held-out scenarios (test F1 {best_t['f1']:.3f} vs {base_t['f1']:.3f}; PR-AUC {best_t.get('pr_auc', 0):.3f} vs {base_t.get('pr_auc', 0):.3f})."
    (EVAL / "metrics.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: report[k] for k in ("selected_model", "retained", "split_counts", "training_seconds")}, indent=1))
    for n in report["models"]:
        t = report["models"][n]["test"]
        print(f"{n:24s} test F1={t['f1']:.3f} P={t['precision']:.3f} R={t['recall']:.3f} PR-AUC={t.get('pr_auc', float('nan')):.3f} ROC-AUC={t.get('roc_auc', float('nan')):.3f}")


if __name__ == "__main__":
    main()
