from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_case_or_404, get_current_user
from app.db.session import get_db
from app.models import (Case, ClaimStatus, ClaimTransactionLink, EvidenceItem, FundsRecord, Role, SourceFile, Transaction, User, VictimClaim)
from app.services import audit
from app.services.claims import reconcile

router = APIRouter(prefix="/cases/{case_id}/claims", tags=["claims"])

TRANSITIONS = {  # status -> (next status, roles allowed)
    "draft": ("investigator_checked", {Role.analyst, Role.supervisor, Role.admin}),
    "investigator_checked": ("supervisor_checked", {Role.supervisor, Role.admin}),
    "supervisor_checked": ("export_ready", {Role.supervisor, Role.admin}),
}


class ClaimIn(BaseModel):
    victim_label: str = Field(min_length=1, max_length=120)
    complaint_ack_no: str = Field(default="", max_length=80)
    fir_reference: str = Field(default="", max_length=80)
    claimed_loss_minor: int = Field(gt=0)
    notes: str = Field(default="", max_length=4000)


class LinkIn(BaseModel):
    transaction_id: str
    amount_minor: int | None = Field(default=None, gt=0)


class FundsIn(BaseModel):
    kind: Literal["held", "restored"]
    account_ref: str = Field(min_length=1, max_length=120)
    amount_minor: int = Field(gt=0)
    source_evidence_item_id: str
    source_kind: Literal["bank_notice", "police_record", "synthetic_simulated"]
    reference: str = Field(default="", max_length=120)


@router.get("")
def list_claims(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    return reconcile(db, case)


@router.post("", status_code=201)
def create_claim(body: ClaimIn, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = VictimClaim(case_id=case.id, created_by=user.id, **body.model_dump())
    db.add(c)
    db.flush()
    audit.record(db, "claim.created", actor_id=user.id, case_id=case.id, target_type="victim_claim", target_id=c.id, detail={"claimed_loss_minor": body.claimed_loss_minor})
    db.commit()
    return {"id": c.id, "status": c.status.value}


@router.post("/{claim_id}/links", status_code=201)
def link_transaction(claim_id: str, body: LinkIn, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.get(VictimClaim, claim_id)
    if c is None or c.case_id != case.id:
        raise HTTPException(404, "Claim not found")
    t = db.get(Transaction, body.transaction_id)
    if t is None or t.case_id != case.id:
        raise HTTPException(404, "Transaction not found in this case")
    if t.amount_minor is None:
        raise HTTPException(400, "Transaction has no parsed amount; cannot be attributed")
    amount = body.amount_minor or t.amount_minor
    if amount > t.amount_minor:
        raise HTTPException(400, "Attributed amount cannot exceed the transaction amount")
    if db.execute(select(ClaimTransactionLink).where(ClaimTransactionLink.claim_id == c.id, ClaimTransactionLink.transaction_id == t.id)).scalar_one_or_none():
        raise HTTPException(409, "Transaction already linked to this claim")
    db.add(ClaimTransactionLink(claim_id=c.id, transaction_id=t.id, amount_minor=amount))
    if c.status != ClaimStatus.draft:
        c.status = ClaimStatus.draft  # any edit re-opens review
    audit.record(db, "claim.transaction_linked", actor_id=user.id, case_id=case.id, target_type="victim_claim", target_id=c.id, detail={"transaction_id": t.id, "amount_minor": amount})
    db.commit()
    return {"ok": True}


@router.post("/{claim_id}/advance")
def advance(claim_id: str, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.get(VictimClaim, claim_id)
    if c is None or c.case_id != case.id:
        raise HTTPException(404, "Claim not found")
    nxt = TRANSITIONS.get(c.status.value)
    if nxt is None:
        raise HTTPException(400, "Claim is already export ready")
    if user.role not in nxt[1]:
        raise HTTPException(403, f"Advancing from {c.status.value} requires {'supervisor' if Role.analyst not in nxt[1] else 'investigator'} review")
    if not db.execute(select(ClaimTransactionLink).where(ClaimTransactionLink.claim_id == c.id)).first():
        raise HTTPException(400, "Link at least one source transaction before review")
    c.status = ClaimStatus(nxt[0])
    audit.record(db, "claim.status_advanced", actor_id=user.id, case_id=case.id, target_type="victim_claim", target_id=c.id, detail={"to": c.status.value})
    db.commit()
    return {"status": c.status.value}


@router.post("/funds", status_code=201)
def record_funds(body: FundsIn, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ev = db.get(EvidenceItem, body.source_evidence_item_id)
    if ev is None or ev.case_id != case.id:
        raise HTTPException(404, "Source evidence item not found in this case (a hold or restoration needs a documented source)")
    if ev.source_type == "bank_statement":
        raise HTTPException(400, "A statement row is not evidence of a hold; attach the bank/police notice as a document and reference it")
    simulated = body.source_kind == "synthetic_simulated" or case.is_synthetic
    f = FundsRecord(case_id=case.id, kind=body.kind, account_ref=body.account_ref, amount_minor=body.amount_minor, source_evidence_item_id=ev.id,
                    source_kind=body.source_kind, is_simulated=simulated, reference=body.reference, recorded_by=user.id)
    db.add(f)
    db.flush()
    audit.record(db, "funds.recorded", actor_id=user.id, case_id=case.id, target_type="funds_record", target_id=f.id, detail={"kind": body.kind, "amount_minor": body.amount_minor, "simulated": simulated})
    db.commit()
    return {"id": f.id, "is_simulated": simulated}


@router.get("/evidence-candidates")
def evidence_candidates(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    """Non-statement evidence items an operator may cite as the source of a hold/restoration record."""
    rows = db.execute(select(EvidenceItem, SourceFile).join(SourceFile, SourceFile.id == EvidenceItem.source_file_id)
                      .where(EvidenceItem.case_id == case.id, EvidenceItem.source_type != "bank_statement", EvidenceItem.extraction_method.notin_(["json_field"]))
                      .order_by(SourceFile.original_name)).all()
    return [{"evidence_item_id": e.id, "file": f.original_name, "locator": e.source_locator, "snippet": (e.raw_value or "")[:160]} for e, f in rows if not e.extraction_method.startswith("regex_")][:200]


@router.get("/pack.json")
def pack_json(case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rec = reconcile(db, case)
    files = db.execute(select(SourceFile).where(SourceFile.case_id == case.id)).scalars().all()
    rec["case"] = {"id": case.id, "title": case.title, "data_status": "SYNTHETIC DATA" if case.is_synthetic else "UPLOADED DATA"}
    rec["sources"] = [{"name": f.original_name, "sha256": f.sha256} for f in files]
    rec["manual_review_checklist"] = ["Verify complaint acknowledgement and FIR references against originals", "Confirm each hold with the bank notice (not a statement row)",
                                      "Resolve competing claims through the authorised process; this pack does not allocate", "Confirm victim identity through the case file, not this pack"]
    audit.record(db, "claims.pack_exported", actor_id=user.id, case_id=case.id, detail={"format": "json", "claims": len(rec["claims"])})
    db.commit()
    return rec


@router.get("/pack.pdf")
def pack_pdf(case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.reports.builder import simple_table_pdf
    rec = reconcile(db, case)
    sections = [
        ("Claims (claimed / traced / unresolved, paise)", ["Victim", "Ack no", "FIR", "Status", "Claimed", "Traced", "Unresolved", "Competing"],
         [[r["victim_label"], r["complaint_ack_no"] or "—", r["fir_reference"] or "—", r["status"], r["claimed_minor"], r["traced_minor"], r["unresolved_minor"], "yes" if r["competing"] else "no"] for r in rec["claims"]]),
        ("Accounts (traced inflow vs documented held / restored)", ["Account", "Traced inflow", "Documented held", "Restored", "Simulated?", "Claims", "Oversubscribed"],
         [[a["account"], a["traced_inflow_minor"], a["documented_held_minor"], a["documented_restored_minor"], "yes" if a["held_is_simulated"] else "no", len(a["claims"]), "yes" if a["oversubscribed"] else "no"] for a in rec["accounts"]]),
        ("Documented funds records", ["Kind", "Account", "Amount", "Source kind", "Simulated", "Source locator"],
         [[f["kind"], f["account"], f["amount_minor"], f["source_kind"], "yes" if f["is_simulated"] else "no", str(f["source_locator"])] for f in rec["funds_records"]]),
    ]
    pdf = simple_table_pdf(f"Restitution readiness pack — {case.title}", ["SYNTHETIC DATA" if case.is_synthetic else "UPLOADED DATA", rec["disclaimer"]], sections)
    audit.record(db, "claims.pack_exported", actor_id=user.id, case_id=case.id, detail={"format": "pdf"})
    db.commit()
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="restitution_pack_{case.id[:8]}.pdf"'})
