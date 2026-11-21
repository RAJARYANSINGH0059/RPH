"""Case-scoped investigative intelligence endpoints (digital-twin increment). Every route is case-membership checked via
get_case_or_404; state-changing routes are audited; nothing here reads sealed ground truth."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_case_or_404, get_current_user
from app.db.session import get_db
from app.models import (AnalysisBranch, AnalysisRun, Case, EvidenceRequest, Hypothesis, IndependentReview, InvestigationEvent, PaymentInstruction, Relationship, Role, RoleReview,
                        SourceFile, User)
from app.reports.builder import simple_table_pdf
from app.services import (adversary, audit, bounded_flow, completeness, counterfactual, coverage, dependencies, integrity, intervention, lifecycle, payment_bridge, proof,
                          resilience, roles, temporal, twin)
from app.services import package as package_service
from app.services.storage import get_storage

router = APIRouter(prefix="/cases/{case_id}", tags=["intel"])


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    if len(s) > 6 and s[-6] == " " and s[-3] == ":":
        s = s[:-6] + "+" + s[-5:]  # "+00:00" arrives as " 00:00" when the plus is not URL-encoded
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        raise HTTPException(400, f"invalid timestamp: {s}")
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _run(db: Session, case: Case, user: User, kind: str, version: str, inputs: dict, outputs: dict, seed: int | None = None) -> AnalysisRun:
    run = AnalysisRun(case_id=case.id, kind=kind, algorithm_version=version, seed=seed, inputs=inputs, outputs=outputs, created_by=user.id)
    db.add(run)
    db.flush()
    audit.record(db, f"analysis.{kind}", actor_id=user.id, case_id=case.id, target_type="analysis_run", target_id=run.id, detail={"version": version})
    return run


# ------------------------------------------------------------------ digital twin / journey / replay

@router.get("/twin")
def digital_twin(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db), as_of: str | None = None, layers: str | None = None):
    return twin.assemble(db, case, as_of=_dt(as_of), layers=set(layers.split(",")) if layers else None)


@router.get("/twin/journey")
def journey(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    return twin.victim_journey(db, case)


@router.get("/twin/replay")
def replay(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db), at: str | None = None, compare_to: str | None = None):
    return twin.replay(db, case, at=_dt(at), compare_to=_dt(compare_to))


class EventIn(BaseModel):
    event_type: str = Field(min_length=3, max_length=48)
    layer: Literal["victim_journey", "artefact", "payment", "financial", "infrastructure", "investigation", "account_control"] = "victim_journey"
    description: str = Field(min_length=3, max_length=2000)
    event_time: str | None = None
    time_precision: Literal["second", "minute", "day", "month", "unknown", "ambiguous"] = "unknown"
    reported_by: str = Field(default="analyst", max_length=120)
    source_evidence_item_id: str | None = None
    attributes: dict = {}


@router.post("/twin/events", status_code=201)
def add_event(body: EventIn, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.event_type not in twin.EVENT_TYPES:
        raise HTTPException(400, f"event_type must be one of {twin.EVENT_TYPES}")
    ie = InvestigationEvent(case_id=case.id, event_type=body.event_type, layer=body.layer, evidence_class="reported", event_time=_dt(body.event_time), time_precision=body.time_precision,
                            observed_at=datetime.now(timezone.utc), reported_by=body.reported_by, reported_at=datetime.now(timezone.utc), description=body.description,
                            source_evidence_item_id=body.source_evidence_item_id, attributes=body.attributes, created_by=user.id)
    db.add(ie)
    db.flush()
    audit.record(db, "twin.event_added", actor_id=user.id, case_id=case.id, target_type="investigation_event", target_id=ie.id, detail={"event_type": body.event_type})
    db.commit()
    return {"id": ie.id, "evidence_class": "reported", "note": "Manually entered events are `reported`, never `directly_observed`."}


# ------------------------------------------------------------------ payment instruction bridge

class InstructionIn(BaseModel):
    raw_payload: str = Field(min_length=1, max_length=4000)
    observed_at: str | None = None
    source_file_id: str | None = None
    source_locator: dict = {}


@router.get("/payment-instructions")
def list_instructions(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    pis = payment_bridge.list_instructions(db, case)
    return {"instructions": [payment_bridge.instruction_out(p) for p in pis], "decoder": __import__("app.parsers.qr", fromlist=["status"]).status(), "levels": payment_bridge.LEVELS}


@router.post("/payment-instructions", status_code=201)
def register_instruction(body: InstructionIn, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.source_file_id and (db.get(SourceFile, body.source_file_id) or SourceFile(case_id="")).case_id != case.id:
        raise HTTPException(404, "source file not found")
    pi = payment_bridge.register_instruction(db, case, user, raw_payload=body.raw_payload, extraction_method="uri_text" if body.raw_payload.strip().lower().startswith("upi") else "manual",
                                             source_file_id=body.source_file_id, source_locator=body.source_locator, observed_at=_dt(body.observed_at))
    res = payment_bridge.match_instruction(db, case, pi)
    db.commit()
    return res


@router.post("/payment-instructions/decode-image", status_code=201)
async def decode_image(file: UploadFile = File(...), case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Upload a QR image through the ordinary ingestion path, then decode every QR region and match each instruction."""
    from app.graph.rules import rebuild_derived
    from app.services.ingestion import ingest_upload
    data = await file.read()
    out = ingest_upload(db, case, user, file.filename or "qr.png", data)
    if out.source_file.detected_kind not in {"png", "jpeg"}:
        raise HTTPException(415, "QR decoding needs a PNG/JPEG image")
    pis = payment_bridge.decode_image_instructions(db, case, user, out.source_file, data)
    results = [payment_bridge.match_instruction(db, case, p) for p in pis]
    rebuild_derived(db, case)
    db.commit()
    return {"file_id": out.source_file.id, "sha256": out.source_file.sha256, "decoded": len(pis), "results": results,
            "warnings": [] if pis else ["no_qr_code_decoded: the image is stored as evidence; try a sharper crop or enter the payload text manually"]}


@router.post("/payment-instructions/{instruction_id}/match")
def rematch(instruction_id: str, tolerance_hours: int = 72, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pi = db.get(PaymentInstruction, instruction_id)
    if pi is None or pi.case_id != case.id:
        raise HTTPException(404, "instruction not found")
    res = payment_bridge.match_instruction(db, case, pi, tolerance_hours=max(1, min(tolerance_hours, 24 * 30)))
    audit.record(db, "payment_instruction.matched", actor_id=user.id, case_id=case.id, target_type="payment_instruction", target_id=pi.id, detail={"status": res["match_status"]})
    db.commit()
    return res


@router.get("/payment-instructions/report.pdf")
def instructions_pdf(case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = []
    for pi in payment_bridge.list_instructions(db, case):
        r = payment_bridge.match_instruction(db, case, pi, persist=False)
        best = r["candidates"][0] if r["candidates"] else None
        rows.append([pi.payload_type, pi.payee_vpa or "-", f"{pi.amount_minor / 100:.2f}" if pi.amount_minor is not None else "-", pi.reference or "-", r["match_status"],
                     ",".join(best["matched_fields"]) if best else "-", ",".join(best["conflicting_fields"]) if best else "-"])
    pdf = simple_table_pdf(f"Payment instruction → transaction bridge — {case.title}", [payment_bridge.LIMITATION, "SYNTHETIC DATA" if case.is_synthetic else "UPLOADED DATA"],
                           [("Instructions and best match", ["Type", "Payee", "Amount", "Reference", "Match", "Matched fields", "Conflicts"], rows)])
    audit.record(db, "report.exported", actor_id=user.id, case_id=case.id, detail={"format": "pdf", "kind": "payment_bridge"})
    db.commit()
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="payment_bridge_{case.id[:8]}.pdf"'})


# ------------------------------------------------------------------ coverage / integrity / proof / temporal

@router.get("/coverage")
def coverage_report(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    return coverage.coverage_report(db, case)


@router.get("/integrity")
def integrity_report(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    return integrity.case_report(db, case)


@router.get("/integrity/files/{file_id}")
def integrity_file(file_id: str, case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    sf = db.get(SourceFile, file_id)
    if sf is None or sf.case_id != case.id:
        raise HTTPException(404, "file not found")
    return integrity.file_report(db, case, sf)


@router.get("/temporal")
def temporal_fusion(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db), window_from: str | None = None, window_to: str | None = None, tolerance_hours: int = 72):
    return temporal.fusion(db, case, window_from=_dt(window_from), window_to=_dt(window_to), tolerance_hours=max(1, min(tolerance_hours, 24 * 30)))


@router.get("/paths/{path_index}/proof.json")
def proof_manifest(path_index: int, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        m = proof.build_manifest(db, case, path_index)
    except IndexError:
        raise HTTPException(404, "path index out of range")
    audit.record(db, "proof.exported", actor_id=user.id, case_id=case.id, detail={"path_index": path_index, "manifest_sha256": m["integrity"]["manifest_sha256"]})
    db.commit()
    return m


@router.get("/paths/{path_index}/proof.pdf")
def proof_pdf(path_index: int, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        m = proof.build_manifest(db, case, path_index)
    except IndexError:
        raise HTTPException(404, "path index out of range")
    rows = [[str(h["hop"]), h["from_account"], h["to_account"], f"{h['amount_minor'] / 100:.2f}", h["reference"] or "-", (h["event_time"] or "-")[:19], h["hop_class"], (h["source_name"] or "-")[:28], (h["source_sha256"] or "")[:12], str((h["locator"] or {}).get("row", "-"))]
            for h in m["hops"]]
    pdf = simple_table_pdf(f"Proof certificate — path {path_index} — {case.title}",
                           [f"Manifest SHA-256 {m['integrity']['manifest_sha256']}", f"Rules: path {m['rules']['path_algorithm_version']}, method {m['rules']['relationship_method_version']}, parser {m['rules']['parser_version']}",
                            "Verify offline: python scripts/verify_proof.py proof.json --files <dir>", *m["limitations"][:2]],
                           [("Hops", ["Hop", "From", "To", "Amount", "Reference", "Event time", "Class", "Source", "SHA-256", "Row"], rows)])
    db.commit()
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="proof_{case.id[:8]}_path{path_index}.pdf"'})


@router.get("/files/{file_id}/download")
def download_original(file_id: str, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Original bytes for offline verification. Audited; demo users may download only synthetic files (all their files are)."""
    sf = db.get(SourceFile, file_id)
    if sf is None or sf.case_id != case.id:
        raise HTTPException(404, "file not found")
    data = get_storage().get(sf.storage_key)
    audit.record(db, "file.downloaded", actor_id=user.id, case_id=case.id, target_type="source_file", target_id=sf.id)
    db.commit()
    return Response(data, media_type=sf.mime_type, headers={"Content-Disposition": f'attachment; filename="{sf.original_name}"'})


# ------------------------------------------------------------------ lifecycle / roles / control timeline

@router.get("/lifecycle")
def lifecycle_map(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    return lifecycle.build(db, case)


class RoleUpdate(BaseModel):
    propositions: dict[str, dict[str, Any]]
    note: str = Field(default="", max_length=2000)


class RoleDecision(BaseModel):
    status: Literal["INDETERMINATE", "HUMAN_REVIEWED", "REVIEW_REQUIRED", "CONFLICTING_EVIDENCE"]
    rationale: str = Field(min_length=10, max_length=4000)


@router.get("/roles/{account_ref}")
def role_review(account_ref: str, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rr = roles.get_or_create(db, case, user, account_ref)
    db.commit()
    return roles.review_out(db, case, rr)


@router.post("/roles/{account_ref}")
def role_update(account_ref: str, body: RoleUpdate, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rr = roles.get_or_create(db, case, user, account_ref)
    errors = roles.validate_update(body.propositions, db, case)
    if errors:
        raise HTTPException(400, {"errors": errors})
    merged = dict(rr.propositions or {})
    for k, v in body.propositions.items():
        merged[k] = {**merged.get(k, {}), **v}
    rr.propositions = merged
    rr.status = roles.derive_status(merged, rr.reviewer_id)
    rr.history = (rr.history or []) + [{"at": datetime.now(timezone.utc).isoformat(), "by": user.id, "change": f"propositions updated: {sorted(body.propositions)}", "note": body.note}]
    audit.record(db, "role_review.updated", actor_id=user.id, case_id=case.id, target_type="role_review", target_id=rr.id, detail={"keys": sorted(body.propositions), "status": rr.status})
    db.commit()
    return roles.review_out(db, case, rr)


@router.post("/roles/{account_ref}/decision")
def role_decision(account_ref: str, body: RoleDecision, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in {Role.supervisor, Role.admin}:
        raise HTTPException(403, "A trained reviewer (supervisor/admin) records the human review decision")
    rr = roles.get_or_create(db, case, user, account_ref)
    rr.reviewer_id, rr.reviewer_rationale, rr.status = user.id, body.rationale, body.status
    rr.history = (rr.history or []) + [{"at": datetime.now(timezone.utc).isoformat(), "by": user.id, "change": f"reviewer decision {body.status}", "note": body.rationale[:500]}]
    audit.record(db, "role_review.decided", actor_id=user.id, case_id=case.id, target_type="role_review", target_id=rr.id, detail={"status": body.status})
    db.commit()
    return roles.review_out(db, case, rr)


class RoleClaimIn(BaseModel):
    role_dimension: str
    actor_label: str = Field(min_length=1, max_length=200)
    claim_state: str
    description: str = Field(min_length=3, max_length=2000)
    event_time: str | None = None
    time_precision: str = "unknown"
    source_evidence_item_id: str | None = None
    counter_evidence: str = Field(default="", max_length=2000)


@router.get("/roles/{account_ref}/control-timeline")
def control_timeline(account_ref: str, case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    return roles.control_timeline(db, case, account_ref)


@router.post("/roles/{account_ref}/control-timeline", status_code=201)
def add_role_claim(account_ref: str, body: RoleClaimIn, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        ie = roles.add_role_claim(db, case, user, account_ref=account_ref, role_dimension=body.role_dimension, actor_label=body.actor_label, claim_state=body.claim_state, description=body.description,
                                  event_time=_dt(body.event_time), time_precision=body.time_precision, source_evidence_item_id=body.source_evidence_item_id, counter_evidence=body.counter_evidence)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    db.commit()
    return {"id": ie.id, **roles.control_timeline(db, case, account_ref)}


# ------------------------------------------------------------------ dependency map / IVOI / preservation / requests

@router.get("/dependencies")
def dependency_map(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    return dependencies.dependency_map(db, case)


@router.get("/ivoi")
def ivoi(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    return dependencies.ivoi_rank(db, case)


@router.get("/preservation")
def preservation(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    return dependencies.preservation_desk(db, case)


class RequestIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    organisation_type: str = "bank"
    catalogue_key: str | None = None
    target_record: str = ""
    target_entity: str = ""
    window_from: str | None = None
    window_to: str | None = None
    required_fields: list[str] = []
    rationale: str = Field(default="", max_length=4000)
    could_resolve: list[str] = []
    would_not_establish: list[str] = []
    ranking: dict = {}
    retention: dict = {}
    legal_authority: str = Field(default="", max_length=200)
    requesting_officer: str = Field(default="", max_length=120)
    is_simulated: bool = False


class RequestStatusIn(BaseModel):
    status: str
    note: str = Field(default="", max_length=2000)
    actual_dispatch_details: str | None = Field(default=None, max_length=1000)
    legal_authority: str | None = None
    requesting_officer: str | None = None
    retention: dict | None = None


def _req_out(r: EvidenceRequest) -> dict:
    return dependencies.request_out(r)


@router.get("/requests")
def list_requests(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    rows = db.execute(select(EvidenceRequest).where(EvidenceRequest.case_id == case.id).order_by(EvidenceRequest.created_at)).scalars().all()
    return {"requests": [_req_out(r) for r in rows], "statuses": dependencies.REQUEST_STATUSES, "transitions": {k: sorted(v) for k, v in dependencies.TRANSITIONS.items()}, "catalogue": dependencies.CATALOGUE}


@router.post("/requests", status_code=201)
def create_request(body: RequestIn, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ranking = dict(body.ranking)
    if body.catalogue_key:
        if body.catalogue_key not in dependencies.CATALOGUE:
            raise HTTPException(400, f"unknown catalogue_key; allowed {sorted(dependencies.CATALOGUE)}")
        ranking["catalogue_key"] = body.catalogue_key
    rq = EvidenceRequest(case_id=case.id, title=body.title, organisation_type=body.organisation_type, target_record=body.target_record, target_entity=body.target_entity, window_from=_dt(body.window_from),
                         window_to=_dt(body.window_to), required_fields=body.required_fields, rationale=body.rationale, could_resolve=body.could_resolve, would_not_establish=body.would_not_establish,
                         ranking=ranking, retention=body.retention, legal_authority=body.legal_authority, requesting_officer=body.requesting_officer, status="draft", is_simulated=body.is_simulated or case.is_synthetic,
                         status_history=[{"from": "identified", "to": "draft", "by": user.id, "at": datetime.now(timezone.utc).isoformat(), "note": "draft created; nothing transmitted"}], created_by=user.id)
    db.add(rq)
    db.flush()
    audit.record(db, "evidence_request.created", actor_id=user.id, case_id=case.id, target_type="evidence_request", target_id=rq.id, detail={"title": body.title, "organisation_type": body.organisation_type})
    db.commit()
    return _req_out(rq)


@router.post("/requests/{request_id}/status")
def request_status(request_id: str, body: RequestStatusIn, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rq = db.get(EvidenceRequest, request_id)
    if rq is None or rq.case_id != case.id:
        raise HTTPException(404, "request not found")
    if body.status in {"authorised", "sent_manual"} and user.role not in {Role.supervisor, Role.admin}:
        raise HTTPException(403, "authorisation and dispatch recording require a supervisor/admin")
    if body.legal_authority is not None:
        rq.legal_authority = body.legal_authority
    if body.requesting_officer is not None:
        rq.requesting_officer = body.requesting_officer
    if body.retention is not None:
        rq.retention = body.retention
    try:
        dependencies.advance_request(db, case, user, rq, body.status, body.note, actual_dispatch_details=body.actual_dispatch_details)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    db.commit()
    return _req_out(rq)


class RequestResponseIn(BaseModel):
    source_file_id: str = Field(min_length=1)
    covers: list[str] = Field(default_factory=list, max_length=40)
    remaining: str | None = Field(default=None, max_length=1000)
    note: str = Field(default="", max_length=1000)


@router.post("/requests/{request_id}/response")
def request_response(request_id: str, body: RequestResponseIn, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Attach a received record (an already-uploaded case file) to a request. A partial response keeps the unresolved remainder
    visible; the request history is append-only and nothing is transmitted."""
    rq = db.get(EvidenceRequest, request_id)
    if rq is None or rq.case_id != case.id:
        raise HTTPException(404, "request not found")
    sf = db.get(SourceFile, body.source_file_id)
    if sf is None or sf.case_id != case.id:
        raise HTTPException(404, "source file not found in this case; upload the returned record to this case first")
    new_status = "partial_response" if body.remaining else "received"
    response = {"source_file_id": sf.id, "name": sf.original_name, "sha256": sf.sha256, "covers": body.covers, "remaining": body.remaining, "attached_at": datetime.now(timezone.utc).isoformat(), "by": user.id}
    try:
        dependencies.advance_request(db, case, user, rq, new_status, body.note or ("partial response attached" if body.remaining else "response attached"), response=response)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    audit.record(db, "evidence_request.response_attached", actor_id=user.id, case_id=case.id, target_type="evidence_request", target_id=rq.id, detail={"source_file_id": sf.id, "partial": bool(body.remaining)})
    db.commit()
    return _req_out(rq)


@router.get("/requests/{request_id}/draft.pdf")
def request_draft_pdf(request_id: str, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rq = db.get(EvidenceRequest, request_id)
    if rq is None or rq.case_id != case.id:
        raise HTTPException(404, "request not found")
    rows = [["Title", rq.title], ["Custodian type", rq.organisation_type + " (suggested; possession of the record not confirmed)"], ["Target", f"{rq.target_entity} {rq.target_record}".strip()],
            ["Period", f"{rq.window_from.isoformat() if rq.window_from else '-'} → {rq.window_to.isoformat() if rq.window_to else '-'}"], ["Fields sought", ", ".join(rq.required_fields) or "-"],
            ["Purpose / rationale", rq.rationale[:600] or "[REQUIRES AUTHORISED COMPLETION]"], ["Could resolve", "; ".join(rq.could_resolve) or "-"], ["Would not establish", "; ".join(rq.would_not_establish) or "-"],
            ["Legal authority", rq.legal_authority or "[REQUIRES AUTHORISED COMPLETION]"], ["Requesting officer", rq.requesting_officer or "[REQUIRES AUTHORISED COMPLETION]"], ["Recipient / signatory / final wording", "[REQUIRES AUTHORISED COMPLETION]"],
            ["Retention", (rq.retention or {}).get("display") or ("verified: " + str((rq.retention or {}).get("source_url")) if (rq.retention or {}).get("verified") else "RETENTION NOT VERIFIED")], ["Status", rq.status + (" (SIMULATED)" if rq.is_simulated else "")]]
    pdf = simple_table_pdf(f"DRAFT evidence request — {case.title}", ["DRAFT ONLY — not transmitted by PS05-X. Legal basis, scope, recipient and wording must be validated by an authorised officer.",
                                                                       "SYNTHETIC DATA" if case.is_synthetic else "UPLOADED DATA"], [("Request draft", ["Field", "Value"], rows)])
    audit.record(db, "evidence_request.draft_exported", actor_id=user.id, case_id=case.id, target_type="evidence_request", target_id=rq.id)
    db.commit()
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="request_draft_{rq.id[:8]}.pdf"'})


# ------------------------------------------------------------------ bounded flow / intervention / chokepoints / resilience

@router.get("/bounded-flow")
def bounded(case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db), path_index: int | None = None, scenario: str | None = None):
    if scenario not in {None, "fifo", "lifo"}:
        raise HTTPException(400, "scenario must be fifo or lifo (assumption-based) or omitted")
    res = bounded_flow.analyse(db, case, path_index=path_index, scenario=scenario)
    _run(db, case, user, "bounded_flow", bounded_flow.FLOW_VERSION, {"path_index": path_index, "scenario": scenario}, {k: res.get(k) for k in ("attribution_status", "hops", "assumptions", "inconsistencies", "missing_evidence")})
    db.commit()
    return res


@router.get("/intervention/{account_ref}")
def intervention_impact(account_ref: str, acknowledged: bool = False, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    res = intervention.exposure(db, case, account_ref)
    if not acknowledged:
        res["scenarios"] = []
        res["warnings"] = (res.get("warnings") or []) + ["scenarios withheld until the viewer acknowledges this is a simulation (acknowledged=true)"]
    else:
        _run(db, case, user, "intervention_impact", intervention.INTERVENTION_VERSION, {"account": account_ref, "acknowledged": True}, {"ledger": res["ledger"], "scenarios": res["scenarios"]})
        db.commit()
    return res


@router.get("/chokepoints")
def chokepoints(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    return resilience.chokepoints(db, case)


class SimulateIn(BaseModel):
    remove_accounts: list[str] = []
    remove_function: Literal["collection", "layering", "exit"] | None = None
    substitutions: dict[str, str] = {}
    label: str = Field(default="", max_length=120)


@router.post("/resilience/simulate")
def simulate(body: SimulateIn, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    res = resilience.simulate(db, case, remove_accounts=body.remove_accounts, remove_function=body.remove_function, substitutions=body.substitutions)
    run = _run(db, case, user, "resilience_scenario", resilience.RESILIENCE_VERSION, {**body.model_dump()}, {"diff": res["diff"], "assumptions": res["assumptions"]})
    db.commit()
    return {**res, "scenario_run_id": run.id}


@router.get("/resilience/scenarios")
def scenarios(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    rows = db.execute(select(AnalysisRun).where(AnalysisRun.case_id == case.id, AnalysisRun.kind == "resilience_scenario").order_by(AnalysisRun.created_at.desc()).limit(50)).scalars().all()
    return [{"id": r.id, "inputs": r.inputs, "diff": (r.outputs or {}).get("diff"), "assumptions": (r.outputs or {}).get("assumptions"), "created_at": r.created_at.isoformat()} for r in rows]


# ------------------------------------------------------------------ counterfactual lab / branches

class LabIn(BaseModel):
    profile: str
    seed: int = Field(default=42001, ge=0, le=2**31 - 1)
    hypothesis_id: str | None = None


@router.get("/lab/profiles")
def lab_profiles(case: Case = Depends(get_case_or_404)):
    return {"profiles": counterfactual.PROFILES, "labels": counterfactual.ROBUSTNESS}


@router.post("/lab/run")
def lab_run(body: LabIn, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        res = counterfactual.run(db, case, profile=body.profile, seed=body.seed, hypothesis_id=body.hypothesis_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    run = _run(db, case, user, "counterfactual", counterfactual.LAB_VERSION, body.model_dump(), {k: res[k] for k in ("robustness", "findings_stable", "findings_weakened", "findings_disappeared", "findings_appeared", "triage_changes")}, seed=body.seed)
    db.commit()
    return {**res, "run_id": run.id}


@router.get("/lab/runs")
def lab_runs(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    rows = db.execute(select(AnalysisRun).where(AnalysisRun.case_id == case.id, AnalysisRun.kind == "counterfactual").order_by(AnalysisRun.created_at.desc()).limit(50)).scalars().all()
    return [{"id": r.id, "profile": (r.inputs or {}).get("profile"), "seed": r.seed, "robustness": (r.outputs or {}).get("robustness"), "created_at": r.created_at.isoformat()} for r in rows]


class BranchIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    hypothesis_statement: str = Field(default="", max_length=2000)
    assumptions: dict = {}
    rationale: str = Field(default="", max_length=2000)


@router.get("/branches")
def list_branches(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    rows = db.execute(select(AnalysisBranch).where(AnalysisBranch.case_id == case.id).order_by(AnalysisBranch.created_at)).scalars().all()
    return {"base_snapshot_hash": counterfactual.snapshot_hash(db, case), "branches": [{"id": b.id, "name": b.name, "hypothesis_statement": b.hypothesis_statement, "assumptions": b.assumptions, "rationale": b.rationale,
            "base_snapshot_hash": b.base_snapshot_hash, "created_at": b.created_at.isoformat()} for b in rows],
            "allowed_assumptions": {"exclude_transaction_ids": "list", "exclude_accounts": "list", "date_interpretation": "as_parsed|swap_ambiguous", "treat_as_same_account": "[[keep, merge_into_keep], ...] (explicit analyst assumption)"}}


@router.post("/branches", status_code=201)
def create_branch(body: BranchIn, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    allowed = {"exclude_transaction_ids", "exclude_accounts", "date_interpretation", "treat_as_same_account"}
    if set(body.assumptions) - allowed:
        raise HTTPException(400, f"assumptions may only contain {sorted(allowed)}")
    b = AnalysisBranch(case_id=case.id, name=body.name, hypothesis_statement=body.hypothesis_statement, base_snapshot_hash=counterfactual.snapshot_hash(db, case), assumptions=body.assumptions, rationale=body.rationale, created_by=user.id)
    db.add(b)
    db.flush()
    audit.record(db, "branch.created", actor_id=user.id, case_id=case.id, target_type="analysis_branch", target_id=b.id, detail={"name": body.name, "assumptions": sorted(body.assumptions)})
    db.commit()
    return {"id": b.id, "base_snapshot_hash": b.base_snapshot_hash}


@router.get("/branches/{branch_id}/compare")
def compare_branch(branch_id: str, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    b = db.get(AnalysisBranch, branch_id)
    if b is None or b.case_id != case.id:
        raise HTTPException(404, "branch not found")
    base = counterfactual.branch_findings(db, case, {})
    other = counterfactual.branch_findings(db, case, b.assumptions or {})
    cmp = counterfactual.compare_branches(base, other)
    current_hash = counterfactual.snapshot_hash(db, case)
    _run(db, case, user, "branch_compare", counterfactual.LAB_VERSION, {"branch_id": b.id}, cmp)
    db.commit()
    return {"branch": {"id": b.id, "name": b.name, "hypothesis_statement": b.hypothesis_statement, "assumptions": b.assumptions, "rationale": b.rationale}, "base": base, "branch_findings": other, "comparison": cmp,
            "source_immutable": True, "base_snapshot_hash_at_branch": b.base_snapshot_hash, "current_snapshot_hash": current_hash, "evidence_changed_since_branch": current_hash != b.base_snapshot_hash,
            "limitations": ["Branches change analysis assumptions only; original files, hashes and audit events are untouched.", "Nothing is merged automatically; comparisons are reproducible from the stored assumptions."]}


# ------------------------------------------------------------------ hypotheses / independent review / adversary

class HypothesisIn(BaseModel):
    kind: Literal["relationship", "path", "role", "campaign", "other"] = "other"
    title: str = Field(min_length=3, max_length=200)
    statement: str = Field(default="", max_length=4000)
    subject_refs: dict = {}
    supporting_evidence_ids: list[str] = []
    alternatives: list[str] = []


class HypothesisUpdate(BaseModel):
    statement: str | None = None
    status: Literal["open", "under_review", "supported", "disputed", "unresolved", "withdrawn"] | None = None
    alternatives: list[str] | None = None
    supporting_evidence_ids: list[str] | None = None
    reason: str = Field(min_length=3, max_length=2000)


def _hyp_out(h: Hypothesis, reviews: list[IndependentReview]) -> dict:
    return {"id": h.id, "kind": h.kind, "title": h.title, "statement": h.statement, "subject_refs": h.subject_refs, "supporting_evidence_ids": h.supporting_evidence_ids, "alternatives": h.alternatives,
            "status": h.status, "version": h.version, "history": h.history, "created_by": h.created_by, "created_at": h.created_at.isoformat(), "updated_at": h.updated_at.isoformat(),
            "reviews": [{"id": r.id, "hypothesis_version": r.hypothesis_version, "reviewer_id": r.reviewer_id, "mode": r.mode, "decision": r.decision, "rationale": r.rationale, "evidence_reviewed": r.evidence_reviewed,
                         "requested_evidence": r.requested_evidence, "is_dissent": r.is_dissent, "created_at": r.created_at.isoformat()} for r in reviews],
            "dissent_on_file": any(r.is_dissent for r in reviews), "disclaimer": "A hypothesis and its review are investigative records, not legal determinations."}


@router.get("/hypotheses")
def list_hypotheses(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    hs = db.execute(select(Hypothesis).where(Hypothesis.case_id == case.id).order_by(Hypothesis.created_at)).scalars().all()
    rv = db.execute(select(IndependentReview).where(IndependentReview.case_id == case.id).order_by(IndependentReview.created_at)).scalars().all()
    return [_hyp_out(h, [r for r in rv if r.hypothesis_id == h.id]) for h in hs]


@router.post("/hypotheses", status_code=201)
def create_hypothesis(body: HypothesisIn, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    h = Hypothesis(case_id=case.id, kind=body.kind, title=body.title, statement=body.statement, subject_refs=body.subject_refs, supporting_evidence_ids=body.supporting_evidence_ids, alternatives=body.alternatives,
                   history=[{"version": 1, "statement": body.statement, "status": "open", "changed_by": user.id, "changed_at": datetime.now(timezone.utc).isoformat(), "reason": "created"}], created_by=user.id)
    db.add(h)
    db.flush()
    audit.record(db, "hypothesis.created", actor_id=user.id, case_id=case.id, target_type="hypothesis", target_id=h.id, detail={"title": body.title, "kind": body.kind})
    db.commit()
    return _hyp_out(h, [])


@router.post("/hypotheses/{hypothesis_id}")
def update_hypothesis(hypothesis_id: str, body: HypothesisUpdate, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    h = db.get(Hypothesis, hypothesis_id)
    if h is None or h.case_id != case.id:
        raise HTTPException(404, "hypothesis not found")
    if body.status == "supported" and user.role not in {Role.supervisor, Role.admin} and not h.supporting_evidence_ids and not body.supporting_evidence_ids:
        raise HTTPException(400, "a hypothesis cannot be marked supported without supporting evidence")
    h.version += 1
    if body.statement is not None:
        h.statement = body.statement
    if body.status is not None:
        h.status = body.status
    if body.alternatives is not None:
        h.alternatives = body.alternatives
    if body.supporting_evidence_ids is not None:
        h.supporting_evidence_ids = body.supporting_evidence_ids
    h.history = (h.history or []) + [{"version": h.version, "statement": h.statement, "status": h.status, "changed_by": user.id, "changed_at": datetime.now(timezone.utc).isoformat(), "reason": body.reason}]
    audit.record(db, "hypothesis.revised", actor_id=user.id, case_id=case.id, target_type="hypothesis", target_id=h.id, detail={"version": h.version, "status": h.status, "reason": body.reason[:200]})
    db.commit()
    rv = db.execute(select(IndependentReview).where(IndependentReview.hypothesis_id == h.id).order_by(IndependentReview.created_at)).scalars().all()
    return _hyp_out(h, rv)


class ReviewIn(BaseModel):
    decision: Literal["agree", "disagree", "request_evidence", "unresolved"]
    rationale: str = Field(min_length=10, max_length=4000)
    mode: Literal["blind", "open"] = "open"
    evidence_reviewed: list[str] = []
    requested_evidence: list[str] = []


@router.get("/hypotheses/{hypothesis_id}/review-view")
def review_view(hypothesis_id: str, blind: bool = False, case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    """Structured review view. blind=true hides the analyst's conclusion/status so the reviewer assesses the evidence first."""
    h = db.get(Hypothesis, hypothesis_id)
    if h is None or h.case_id != case.id:
        raise HTTPException(404, "hypothesis not found")
    rels = [db.get(Relationship, rid) for rid in ((h.subject_refs or {}).get("relationship_ids") or [])]
    challenges = [adversary.challenge(db, case, r)["report"] for r in rels if r and r.case_id == case.id]
    view = {"hypothesis_id": h.id, "title": h.title, "kind": h.kind, "subject_refs": h.subject_refs, "supporting_evidence_ids": h.supporting_evidence_ids, "alternatives": h.alternatives, "challenges": challenges,
            "blind": blind, "analyst_conclusion": None if blind else {"statement": h.statement, "status": h.status, "version": h.version}}
    return view


@router.post("/hypotheses/{hypothesis_id}/reviews", status_code=201)
def add_review(hypothesis_id: str, body: ReviewIn, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    h = db.get(Hypothesis, hypothesis_id)
    if h is None or h.case_id != case.id:
        raise HTTPException(404, "hypothesis not found")
    if user.id == h.created_by and user.role not in {Role.admin}:
        raise HTTPException(403, "independent review must come from a different user")
    is_dissent = body.decision == "disagree"
    rv = IndependentReview(case_id=case.id, hypothesis_id=h.id, hypothesis_version=h.version, reviewer_id=user.id, mode=body.mode, decision=body.decision, rationale=body.rationale,
                           evidence_reviewed=body.evidence_reviewed, requested_evidence=body.requested_evidence, is_dissent=is_dissent)
    db.add(rv)
    if h.status == "open":
        h.status = "under_review"
    if is_dissent and h.status == "supported":
        h.status = "disputed"
        h.version += 1
        h.history = (h.history or []) + [{"version": h.version, "statement": h.statement, "status": h.status, "changed_by": user.id, "changed_at": datetime.now(timezone.utc).isoformat(), "reason": "reviewer dissent recorded"}]
    audit.record(db, "hypothesis.reviewed", actor_id=user.id, case_id=case.id, target_type="hypothesis", target_id=h.id, detail={"decision": body.decision, "dissent": is_dissent, "mode": body.mode})
    db.commit()
    rvs = db.execute(select(IndependentReview).where(IndependentReview.hypothesis_id == h.id).order_by(IndependentReview.created_at)).scalars().all()
    return _hyp_out(h, rvs)


@router.get("/adversary")
def adversary_summary(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db), limit: int = 60):
    return adversary.challenge_all(db, case, limit=max(1, min(limit, 200)))


@router.get("/adversary/{edge_id}")
def adversary_edge(edge_id: str, case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    r = db.get(Relationship, edge_id)
    if r is None or r.case_id != case.id:
        raise HTTPException(404, "edge not found")
    return adversary.challenge(db, case, r)


class AdversaryAction(BaseModel):
    action: Literal["accept", "reject", "retain_as_candidate", "add_competing_hypothesis", "record_dissent"]
    reason: str = Field(min_length=5, max_length=2000)
    hypothesis_title: str | None = None


@router.post("/adversary/{edge_id}/action")
def adversary_action(edge_id: str, body: AdversaryAction, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models import AnalystReview, ReviewStatus
    r = db.get(Relationship, edge_id)
    if r is None or r.case_id != case.id:
        raise HTTPException(404, "edge not found")
    if body.action == "accept":
        if r.evidence_level.value in {"candidate", "stale", "contradicted"} and user.role not in {Role.supervisor, Role.admin}:
            raise HTTPException(403, "Accepting a candidate/stale/contradicted relationship requires supervisor review")
        db.add(AnalystReview(case_id=case.id, relationship_id=r.id, reviewer_id=user.id, decision=ReviewStatus.supported, reason=body.reason))
        r.review_status = ReviewStatus.supported
    elif body.action == "reject":
        db.add(AnalystReview(case_id=case.id, relationship_id=r.id, reviewer_id=user.id, decision=ReviewStatus.rejected, reason=body.reason))
        r.review_status = ReviewStatus.rejected
    elif body.action == "retain_as_candidate":
        db.add(AnalystReview(case_id=case.id, relationship_id=r.id, reviewer_id=user.id, decision=ReviewStatus.needs_more_evidence, reason=body.reason))
        r.review_status = ReviewStatus.needs_more_evidence
    elif body.action in {"add_competing_hypothesis", "record_dissent"}:
        h = Hypothesis(case_id=case.id, kind="relationship", title=body.hypothesis_title or (("Dissent: " if body.action == "record_dissent" else "Alternative: ") + r.relationship_type.replace("_", " ").lower()),
                       statement=body.reason, subject_refs={"relationship_ids": [r.id]}, status="disputed" if body.action == "record_dissent" else "open",
                       history=[{"version": 1, "statement": body.reason, "status": "open", "changed_by": user.id, "changed_at": datetime.now(timezone.utc).isoformat(), "reason": body.action}], created_by=user.id)
        db.add(h)
    audit.record(db, f"adversary.{body.action}", actor_id=user.id, case_id=case.id, target_type="relationship", target_id=r.id, detail={"reason": body.reason[:300]})
    db.commit()
    return adversary.challenge(db, case, r)


# ------------------------------------------------------------------ completeness / saved views

@router.get("/completeness")
def completeness_check(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    return completeness.checklist(db, case)


class SavedViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    state: dict


@router.get("/views")
def list_views(case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(AnalysisRun).where(AnalysisRun.case_id == case.id, AnalysisRun.kind == "saved_view", AnalysisRun.created_by == user.id).order_by(AnalysisRun.created_at.desc()).limit(30)).scalars().all()
    return [{"id": r.id, "name": (r.inputs or {}).get("name"), "state": r.outputs, "created_at": r.created_at.isoformat()} for r in rows]


@router.post("/views", status_code=201)
def save_view(body: SavedViewIn, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if len(str(body.state)) > 20000:
        raise HTTPException(413, "view state too large")
    run = AnalysisRun(case_id=case.id, kind="saved_view", algorithm_version="1", inputs={"name": body.name}, outputs=body.state, created_by=user.id)
    db.add(run)
    db.commit()
    return {"id": run.id, "name": body.name}


@router.get("/role-reviews")
def list_role_reviews(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    rows = db.execute(select(RoleReview).where(RoleReview.case_id == case.id).order_by(RoleReview.updated_at.desc())).scalars().all()
    return [{"id": r.id, "account_ref": r.account_ref, "status": r.status, "reviewer_id": r.reviewer_id, "updated_at": r.updated_at.isoformat()} for r in rows]


# ------------------------------------------------------------------ proof-carrying investigation package

@router.get("/package.zip")
def investigation_package(case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Report, proof manifests, analyses with assumptions, hypotheses with dissent, requests with responses, role reviews, audit
    history and a SHA-256 manifest. Never includes sealed truth, credentials or raw uploads."""
    data, manifest = package_service.build(db, case, user)
    audit.record(db, "package.exported", actor_id=user.id, case_id=case.id, target_type="case", target_id=case.id, detail={"entries": len(manifest["entries"]), "package_sha256": manifest["package_sha256"]})
    db.commit()
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="investigation_package_{case.id[:8]}.zip"', "X-Package-SHA256": manifest["package_sha256"]})
