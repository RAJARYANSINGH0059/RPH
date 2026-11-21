"""Prevention-rule compiler (sandbox only).

Compiles a human-approved, source-linked typology into a versioned candidate rule (conjunction of feature thresholds) and
evaluates it on held-out synthetic seeds that are generated in memory from sealed truth (never the case under review).
Reports precision, recall, false-positive rate, alert volume and limits. Approval is explicit; nothing is deployed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.graph import engine
from app.models import CandidateRule, User
from app.services import audit
from app.services.counterfactual import _features
from app.synthetic.generator import SCENARIOS, Generator

RULE_VERSION = "1.0.0"
FEATURES = ["fan_in", "fan_out", "tx_in", "tx_out", "out_in_ratio", "median_holding_hours", "velocity_tx_per_day", "total_out_minor", "total_in_minor"]
OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, "<": lambda a, b: a < b, "==": lambda a, b: a == b}
TYPOLOGIES = {"collect_and_forward": [{"feature": "fan_in", "op": ">=", "value": 2}, {"feature": "out_in_ratio", "op": ">=", "value": 0.7}],
              "fast_pass_through": [{"feature": "median_holding_hours", "op": "<=", "value": 48}, {"feature": "median_holding_hours", "op": ">=", "value": 0}, {"feature": "tx_out", "op": ">=", "value": 1}],
              "fan_out_splitter": [{"feature": "fan_out", "op": ">=", "value": 3}, {"feature": "total_out_minor", "op": ">", "value": 0}]}


def validate(conditions: list[dict]) -> list[str]:
    errs = []
    for c in conditions:
        if c.get("feature") not in FEATURES:
            errs.append(f"unknown feature {c.get('feature')}; allowed {FEATURES}")
        if c.get("op") not in OPS:
            errs.append(f"unknown op {c.get('op')}")
        if not isinstance(c.get("value"), (int, float)):
            errs.append("value must be numeric")
    return errs


def fires(conditions: list[dict], feats: dict) -> bool:
    return all(OPS[c["op"]](feats.get(c["feature"], 0), c["value"]) for c in conditions)


def evaluate(conditions: list[dict], *, seeds: list[int], scenarios: list[str] | None = None, difficulty: str = "messy") -> dict:
    """Evaluate on held-out synthetic seeds generated in memory (truth transactions → features), never on live cases."""
    tp = fp = fn = tn = 0
    per_case = []
    for sc in (scenarios or SCENARIOS):
        for seed in seeds:
            gen = Generator(sc, difficulty, "small", seed)
            truth = gen.build_truth()
            edges = [{"src": t.src.acct_no, "dst": t.dst.acct_no, "amount_minor": t.amount_minor, "time": t.when, "tx_id": t.ref, "evidence_item_id": t.ref, "precision": "second", "duplicate": False, "corroborated": False, "reference": t.ref}
                     for t in truth.transactions]
            feats = _features(edges)
            mules = set(truth.mule_accounts)
            alerts = 0
            for acct, f in feats.items():
                fired = fires(conditions, f)
                alerts += int(fired)
                if fired and acct in mules:
                    tp += 1
                elif fired:
                    fp += 1
                elif acct in mules:
                    fn += 1
                else:
                    tn += 1
            per_case.append({"scenario": sc, "seed": seed, "accounts": len(feats), "alerts": alerts, "mule_accounts": len(mules)})
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    fpr = fp / (fp + tn) if fp + tn else None
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": round(prec, 3) if prec is not None else None, "recall": round(rec, 3) if rec is not None else None,
            "false_positive_rate": round(fpr, 3) if fpr is not None else None, "alert_volume_per_case": round(sum(c["alerts"] for c in per_case) / len(per_case), 2) if per_case else None,
            "cases": len(per_case), "seeds": seeds, "scenarios": scenarios or SCENARIOS, "difficulty": difficulty, "per_case": per_case,
            "limits": ["Synthetic-only evaluation; not real-world performance.", "Held-out seeds are generated in memory from the generator, never from live cases.",
                       "Labels are generator roles (mule_l1/l2/exit); a rule hit is a triage cue, never a determination about a person."]}


def compile_rule(db: Session, user: User, *, name: str, typology: str, conditions: list[dict] | None, source_hypothesis_id: str | None, seeds: list[int]) -> CandidateRule:
    conds = conditions or TYPOLOGIES.get(typology)
    if not conds:
        raise ValueError(f"no conditions; known typologies {sorted(TYPOLOGIES)}")
    errs = validate(conds)
    if errs:
        raise ValueError("; ".join(errs))
    ev = evaluate(conds, seeds=seeds)
    baseline = evaluate(TYPOLOGIES["collect_and_forward"], seeds=seeds)
    ev["baseline_collect_and_forward"] = {k: baseline[k] for k in ("precision", "recall", "false_positive_rate", "alert_volume_per_case")}
    ev["rules_engine_reference"] = engine.rules_triage.__doc__
    existing = [r for r in db.query(CandidateRule).filter(CandidateRule.name == name).all()]
    rule = CandidateRule(name=name, version=(max((r.version for r in existing), default=0) + 1), typology=typology, conditions=conds, source_hypothesis_id=source_hypothesis_id,
                         evaluation=ev, approval_status="draft", review_due=datetime.now(timezone.utc) + timedelta(days=90), created_by=user.id)
    db.add(rule)
    db.flush()
    audit.record(db, "candidate_rule.compiled", actor_id=user.id, target_type="candidate_rule", target_id=rule.id, detail={"name": name, "version": rule.version, "precision": ev["precision"], "recall": ev["recall"]})
    return rule


def rule_out(r: CandidateRule) -> dict:
    return {"id": r.id, "name": r.name, "version": r.version, "typology": r.typology, "conditions": r.conditions, "source_hypothesis_id": r.source_hypothesis_id,
            "evaluation": {k: v for k, v in (r.evaluation or {}).items() if k != "per_case"}, "per_case": (r.evaluation or {}).get("per_case", [])[:40], "approval_status": r.approval_status,
            "approved_by": r.approved_by, "review_due": r.review_due.isoformat() if r.review_due else None, "created_at": r.created_at.isoformat() if r.created_at else None,
            "deployment": "never: candidate rules are evaluated proposals only; no bank deployment, account blocking or production enforcement"}
