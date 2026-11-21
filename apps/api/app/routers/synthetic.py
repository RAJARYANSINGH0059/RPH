from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_case_or_404, get_current_user
from app.db.session import get_db
from app.models import Case, CaseMembership, SyntheticScenario, User
from app.routers.cases import _case_out, _run_out, _sf_out
from app.schemas import SyntheticRequest, SyntheticResult, UploadResult
from app.synthetic.generator import DIFFICULTIES, SCENARIOS, SIZES, GENERATOR_VERSION
from app.synthetic import challenge
from app.synthetic.service import generate_case

router = APIRouter(prefix="/synthetic", tags=["synthetic"])


@router.get("/options")
def options():
    return {"scenario_types": SCENARIOS, "difficulties": DIFFICULTIES, "sizes": list(SIZES), "generator_version": GENERATOR_VERSION,
            "watermark": "SYNTHETIC DATA", "note": "Public bundle only. Ground truth is sealed and not served by case APIs."}


@router.post("/generate", response_model=SyntheticResult, status_code=201)
def generate(body: SyntheticRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    case, scen, outcomes, manifest = generate_case(db, user, scenario_type=body.scenario_type, difficulty=body.difficulty, size=body.size, seed=body.seed, title=body.title)
    db.add(CaseMembership(case_id=case.id, user_id=user.id, role_in_case="owner"))
    db.commit()
    db.refresh(case)
    return SyntheticResult(case=_case_out(case), scenario_id=scen.id, public_manifest=manifest,
                           files=[UploadResult(file=_sf_out(o.source_file), parse_run=_run_out(o.parse_run) if o.parse_run else None, preview=o.preview) for o in outcomes])


@router.get("/cases/{case_id}/manifest")
def manifest(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    scen = db.execute(select(SyntheticScenario).where(SyntheticScenario.case_id == case.id)).scalar_one_or_none()
    if scen is None:
        return {"synthetic": False}
    # public fields only; sealed_truth_ref is deliberately not returned
    return {"synthetic": True, "scenario_type": scen.scenario_type, "difficulty": scen.difficulty, "size": scen.size, "seed": scen.seed,
            "scenario_version": scen.scenario_version, "generator_version": scen.generator_version, "public_manifest": scen.public_manifest}


class ChallengeSubmission(BaseModel):
    mule_pattern_accounts: list[str] = []
    common_operator_domains: list[str] = []
    unresolved_notes: str = ""
    hypotheses: list[str] = []


@router.get("/cases/{case_id}/challenge")
def challenge_status(case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sub = challenge.submission(db, case, user)
    return {"synthetic": case.is_synthetic, "submitted": sub is not None, "locked_at": (sub.inputs or {}).get("locked_at") if sub else None, "revealed": bool(sub and (sub.outputs or {}).get("revealed_at")),
            "instructions": ["Investigate the case with the ordinary tools.", "Record which accounts you consider mule-pattern and which domains (if any) you would assert share an operator.",
                             "Submit to lock your decisions; only then can the sealed truth be revealed and your decisions scored.", "This is a synthetic evaluation, not real-world accuracy."]}


@router.post("/cases/{case_id}/challenge/submit", status_code=201)
def challenge_submit(body: ChallengeSubmission, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        run = challenge.submit(db, case, user, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    db.commit()
    return {"submission_id": run.id, "locked_at": run.inputs["locked_at"], "next": "GET /challenge/reveal"}


@router.get("/cases/{case_id}/challenge/reveal")
def challenge_reveal(case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        out = challenge.reveal(db, case, user)
    except PermissionError as exc:
        raise HTTPException(409, str(exc))
    except (ValueError, LookupError) as exc:
        raise HTTPException(400, str(exc))
    db.commit()
    return out
