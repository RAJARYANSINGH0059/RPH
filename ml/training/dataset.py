"""Build a per-account triage dataset by running synthetic scenarios through the REAL ingestion pipeline.

Each row = one account (after identifier aliasing), features from app.graph.engine.account_features, label from the
sealed ground truth (1 = generated mule-pattern participant: mule_l1 / mule_l2 / exit; 0 = victim / unrelated).
Split is by scenario (seed + template), never by row.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "apps" / "api"
sys.path.insert(0, str(API))

_TMP = tempfile.mkdtemp(prefix="ps05x_ml_")
os.environ.setdefault("DATABASE_URL", "sqlite:///" + os.path.join(_TMP, "ml.db").replace("\\", "/"))
os.environ.setdefault("STORAGE_DIR", os.path.join(_TMP, "data"))
os.environ.setdefault("BENCHMARK_STORE_DIR", os.path.join(_TMP, "sealed"))

from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.graph import engine as gengine  # noqa: E402
from app.models import Role, User  # noqa: E402
from app.synthetic import sealed_store  # noqa: E402
from app.synthetic.generator import DIFFICULTIES, SCENARIOS  # noqa: E402
from app.synthetic.service import generate_case  # noqa: E402

FEATURES = ["in_degree", "out_degree", "tx_in", "tx_out", "total_in_minor", "total_out_minor", "out_in_ratio", "median_holding_hours",
            "unique_counterparties", "velocity_tx_per_day", "amount_concentration", "fan_in", "fan_out", "missing_field_ratio",
            "duplicate_count", "time_uncertain_ratio"]
DATASET_VERSION = "1"


def _user(db) -> User:
    u = db.query(User).filter(User.email == "ml@local").one_or_none()
    if u is None:
        u = User(email="ml@local", display_name="ML runner", password_hash="x", role=Role.admin)
        db.add(u)
        db.flush()
    return u


def build_rows(seeds: list[int], scenarios: list[str] | None = None, difficulties: list[str] | None = None, size: str = "small") -> list[dict]:
    Base.metadata.create_all(bind=engine)
    scenarios = scenarios or SCENARIOS
    difficulties = difficulties or DIFFICULTIES
    rows: list[dict] = []
    with SessionLocal() as db:
        user = _user(db)
        for seed in seeds:
            for sc in scenarios:
                for diff in difficulties:
                    case, scen, _, _ = generate_case(db, user, scenario_type=sc, difficulty=diff, size=size, seed=seed)
                    db.flush()
                    truth = sealed_store.unseal(scen.sealed_truth_ref)
                    role_by_key = {a["acct_no"]: a["role"] for a in truth["accounts"]}
                    role_by_key.update({a["vpa"]: a["role"] for a in truth["accounts"]})
                    feats = gengine.account_features(db, case)
                    for acct, f in feats.items():
                        role = role_by_key.get(acct, "unknown")
                        label = 1 if role in {"mule_l1", "mule_l2", "exit"} else 0
                        rows.append({"scenario_id": f"{sc}|{diff}|{seed}", "scenario_type": sc, "difficulty": diff, "seed": seed, "account": acct,
                                     "role": role, "label": label, "rules": gengine.rules_triage(f), **{k: f[k] for k in FEATURES}})
                    db.commit()
    return rows
