from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_case_or_404, get_current_user
from app.db.session import get_db
from app.graph import engine
from app.graph.rules import rebuild_derived
from app.models import (AuditEvent, Case, CaseMembership, Entity, EvidenceLevel, ParseRun, Relationship, Role, SourceFile,
                        Transaction, User)
from app.schemas import (CaseCreate, CaseOut, CaseOverview, ColumnMappingRequest, ParseRunOut, PathsResponse, SourceFileOut,
                         TimelineEvent, TransactionOut, UploadResult)
from app.services import audit, ml_triage
from app.services.ingestion import ingest_upload

router = APIRouter(prefix="/cases", tags=["cases"])


def _case_out(c: Case) -> CaseOut:
    return CaseOut(id=c.id, title=c.title, internal_ref=c.internal_ref, summary=c.summary, status=c.status, is_synthetic=c.is_synthetic,
                   created_by=c.created_by, created_at=c.created_at, updated_at=c.updated_at)


def _sf_out(f: SourceFile) -> SourceFileOut:
    return SourceFileOut(id=f.id, original_name=f.original_name, mime_type=f.mime_type, detected_kind=f.detected_kind, size_bytes=f.size_bytes,
                         sha256=f.sha256, uploaded_at=f.uploaded_at, is_synthetic=f.is_synthetic, status=f.status)


def _run_out(r: ParseRun) -> ParseRunOut:
    return ParseRunOut(id=r.id, source_file_id=r.source_file_id, parser_name=r.parser_name, parser_version=r.parser_version, status=r.status,
                       column_mapping=r.column_mapping or {}, warnings=r.warnings or [], stats=r.stats or {}, started_at=r.started_at, finished_at=r.finished_at)


@router.get("", response_model=list[CaseOut])
def list_cases(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = select(Case).order_by(Case.updated_at.desc())
    if user.role != Role.admin:
        member_ids = select(CaseMembership.case_id).where(CaseMembership.user_id == user.id)
        q = q.where(or_(Case.created_by == user.id, Case.id.in_(member_ids)))
    return [_case_out(c) for c in db.execute(q).scalars().all()]


@router.post("", response_model=CaseOut, status_code=201)
def create_case(body: CaseCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = Case(title=body.title, internal_ref=body.internal_ref, summary=body.summary, created_by=user.id)
    db.add(c)
    db.flush()
    db.add(CaseMembership(case_id=c.id, user_id=user.id, role_in_case="owner"))
    audit.record(db, "case.created", actor_id=user.id, case_id=c.id)
    db.commit()
    db.refresh(c)
    return _case_out(c)


@router.get("/{case_id}", response_model=CaseOverview)
def case_overview(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    cnt = lambda model: db.execute(select(func.count()).select_from(model).where(model.case_id == case.id)).scalar() or 0  # noqa: E731
    indicators = db.execute(select(func.count()).select_from(Entity).where(Entity.case_id == case.id, Entity.entity_type.in_(["url", "domain", "ip", "asn", "hosting_provider"]))).scalar() or 0
    warnings = sum(len(r.warnings or []) for r in db.execute(select(ParseRun).where(ParseRun.case_id == case.id)).scalars())
    awaiting = db.execute(select(func.count()).select_from(Relationship).where(Relationship.case_id == case.id,
                          Relationship.evidence_level.in_([EvidenceLevel.candidate, EvidenceLevel.stale, EvidenceLevel.contradicted]),
                          Relationship.review_status == "unreviewed")).scalar() or 0
    last = db.execute(select(func.max(AuditEvent.created_at)).where(AuditEvent.case_id == case.id)).scalar()
    return CaseOverview(**_case_out(case).model_dump(), files_count=cnt(SourceFile), transactions_count=cnt(Transaction), entities_count=cnt(Entity),
                        relationships_count=cnt(Relationship), indicators_count=indicators, unresolved_warnings=warnings,
                        findings_awaiting_review=awaiting, last_activity=last)


@router.get("/{case_id}/files", response_model=list[SourceFileOut])
def list_files(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    return [_sf_out(f) for f in db.execute(select(SourceFile).where(SourceFile.case_id == case.id).order_by(SourceFile.uploaded_at)).scalars()]


@router.get("/{case_id}/parse-runs", response_model=list[ParseRunOut])
def list_runs(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    return [_run_out(r) for r in db.execute(select(ParseRun).where(ParseRun.case_id == case.id).order_by(ParseRun.started_at)).scalars()]


@router.post("/{case_id}/upload", response_model=list[UploadResult])
async def upload(files: list[UploadFile] = File(...), case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Multi-file upload. This is the same code path used by the Synthetic Case Factory."""
    if len(files) > 20:
        raise HTTPException(400, "Max 20 files per upload")
    results = []
    for f in files:
        data = await f.read()
        out = ingest_upload(db, case, user, f.filename or "upload", data)
        results.append(UploadResult(file=_sf_out(out.source_file), parse_run=_run_out(out.parse_run) if out.parse_run else None, preview=out.preview))
    rebuild_derived(db, case)
    db.commit()
    return results


@router.post("/{case_id}/files/{file_id}/remap", response_model=UploadResult)
def remap(file_id: str, body: ColumnMappingRequest, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    """Re-parse a statement with an analyst-corrected column mapping. The original file and hash are preserved."""
    from app.services.storage import get_storage
    sf = db.get(SourceFile, file_id)
    if sf is None or sf.case_id != case.id:
        raise HTTPException(404, "File not found")
    if sf.detected_kind not in {"csv", "xlsx"}:
        raise HTTPException(400, "Only tabular files can be remapped")
    data = get_storage().get(sf.storage_key)
    out = ingest_upload(db, case, user, sf.original_name, data, is_synthetic=sf.is_synthetic, mapping_override=body.mapping)
    audit.record(db, "file.remapped", actor_id=user.id, case_id=case.id, target_type="source_file", target_id=out.source_file.id, detail={"mapping": body.mapping, "previous_file": sf.id})
    rebuild_derived(db, case)
    db.commit()
    return UploadResult(file=_sf_out(out.source_file), parse_run=_run_out(out.parse_run) if out.parse_run else None, preview=out.preview)


@router.get("/{case_id}/transactions", response_model=list[TransactionOut])
def transactions(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db), limit: int = 500, offset: int = 0):
    rows = db.execute(select(Transaction).where(Transaction.case_id == case.id).order_by(Transaction.datetime_utc.nulls_last(), Transaction.id).offset(offset).limit(min(limit, 2000))).scalars().all()
    return [TransactionOut(**{k: getattr(t, k) for k in TransactionOut.model_fields}) for t in rows]


@router.get("/{case_id}/paths", response_model=PathsResponse)
def paths(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    feats = engine.account_features(db, case)
    recon = []
    for r in db.execute(select(ParseRun).where(ParseRun.case_id == case.id)).scalars():
        rc = (r.stats or {}).get("reconciliation")
        if rc:
            recon.append({"parse_run_id": r.id, "source_file_id": r.source_file_id, **rc})
    return PathsResponse(paths=engine.reconstruct_paths(db, case),
                         features={a: {**f, "triage": engine.rules_triage(f), "ml_triage": ml_triage.score(f)} for a, f in feats.items()},
                         reconciliation=recon)


@router.get("/{case_id}/timeline", response_model=list[TimelineEvent])
def timeline(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db), family: str | None = None):
    evs = engine.timeline(db, case)
    if family:
        evs = [e for e in evs if e["family"] == family]
    return [TimelineEvent(**e) for e in evs]


@router.get("/{case_id}/audit")
def audit_log(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    rows = db.execute(select(AuditEvent).where(AuditEvent.case_id == case.id).order_by(AuditEvent.created_at.desc()).limit(200)).scalars().all()
    return [{"id": a.id, "action": a.action, "actor_id": a.actor_id, "target_type": a.target_type, "target_id": a.target_id, "detail": a.detail, "created_at": a.created_at} for a in rows]
