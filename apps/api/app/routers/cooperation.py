"""Cross-state investigation cooperation pack: a manual handoff bundle aligned to the publicly described request fields.
No portal automation, no submission, no CAPTCHA handling. Supervisor endorsement is required before export-ready."""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_case_or_404, get_current_user
from app.db.session import get_db
from app.models import Case, CooperationPack, Role, SourceFile, User
from app.reports.builder import build_report, simple_table_pdf
from app.services import audit
from app.services.storage import get_storage

router = APIRouter(prefix="/cases/{case_id}/cooperation", tags=["cooperation"])

REQUIRED = ["officer_name", "officer_rank", "department", "officer_contact", "state", "district", "police_station", "fir_number", "fir_year",
            "supervising_officer_name", "supervising_officer_designation", "supervising_officer_contact", "fir_gist", "assistance_details"]
BOUNDED = {"fir_gist": (10, 500), "assistance_details": (10, 500)}


class PackIn(BaseModel):
    fields: dict = Field(default_factory=dict)
    attachment_file_ids: list[str] = Field(default_factory=list, max_length=20)
    fir_file_id: str | None = None
    endorsement_file_id: str | None = None


def validate(fields: dict, fir_file_id, endorsement_file_id) -> dict:
    missing = [k for k in REQUIRED if not str(fields.get(k, "")).strip()]
    bounds = {}
    for k, (lo, hi) in BOUNDED.items():
        n = len(str(fields.get(k, "")).strip())
        if n and not (lo <= n <= hi):
            bounds[k] = f"{n} characters; must be {lo}–{hi}"
    if fields.get("fir_year") and not str(fields["fir_year"]).isdigit():
        bounds["fir_year"] = "must be a year"
    attachments_missing = [x for x, v in (("fir_pdf", fir_file_id), ("supervisor_endorsement", endorsement_file_id)) if not v]
    return {"missing_fields": missing, "out_of_bounds": bounds, "missing_attachments": attachments_missing,
            "complete": not missing and not bounds and not attachments_missing}


def _pack_out(p: CooperationPack) -> dict:
    return {"id": p.id, "status": p.status, "fields": p.fields, "attachment_file_ids": p.attachment_file_ids, "fir_file_id": p.fir_file_id,
            "endorsement_file_id": p.endorsement_file_id, "endorsed_by": p.endorsed_by, "created_by": p.created_by, "created_at": p.created_at,
            "updated_at": p.updated_at, "exported_at": p.exported_at, "validation": validate(p.fields, p.fir_file_id, p.endorsement_file_id), "required_fields": REQUIRED, "bounds": BOUNDED}


@router.get("")
def list_packs(case: Case = Depends(get_case_or_404), db: Session = Depends(get_db)):
    return [_pack_out(p) for p in db.execute(select(CooperationPack).where(CooperationPack.case_id == case.id).order_by(CooperationPack.created_at)).scalars()]


@router.post("", status_code=201)
def create_or_update(body: PackIn, pack_id: str | None = None, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    for fid in body.attachment_file_ids + [x for x in (body.fir_file_id, body.endorsement_file_id) if x]:
        f = db.get(SourceFile, fid)
        if f is None or f.case_id != case.id:
            raise HTTPException(404, f"Attachment {fid} not found in this case")
    if pack_id:
        p = db.get(CooperationPack, pack_id)
        if p is None or p.case_id != case.id:
            raise HTTPException(404, "Pack not found")
        p.fields, p.attachment_file_ids, p.fir_file_id, p.endorsement_file_id = body.fields, body.attachment_file_ids, body.fir_file_id, body.endorsement_file_id
        p.status, p.endorsed_by = "draft", None  # any edit withdraws endorsement
        action = "cooperation.updated"
    else:
        p = CooperationPack(case_id=case.id, fields=body.fields, attachment_file_ids=body.attachment_file_ids, fir_file_id=body.fir_file_id,
                            endorsement_file_id=body.endorsement_file_id, created_by=user.id)
        db.add(p)
        db.flush()
        action = "cooperation.created"
    audit.record(db, action, actor_id=user.id, case_id=case.id, target_type="cooperation_pack", target_id=p.id, detail={"complete": validate(p.fields, p.fir_file_id, p.endorsement_file_id)["complete"]})
    db.commit()
    return _pack_out(p)


@router.post("/{pack_id}/endorse")
def endorse(pack_id: str, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in {Role.supervisor, Role.admin}:
        raise HTTPException(403, "Supervisor endorsement required")
    p = db.get(CooperationPack, pack_id)
    if p is None or p.case_id != case.id:
        raise HTTPException(404, "Pack not found")
    v = validate(p.fields, p.fir_file_id, p.endorsement_file_id)
    if not v["complete"]:
        raise HTTPException(400, {"detail": "Pack is incomplete", **v})
    p.status, p.endorsed_by = "export_ready", user.id
    audit.record(db, "cooperation.endorsed", actor_id=user.id, case_id=case.id, target_type="cooperation_pack", target_id=p.id)
    db.commit()
    return _pack_out(p)


@router.get("/{pack_id}/export.zip")
def export_zip(pack_id: str, case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.get(CooperationPack, pack_id)
    if p is None or p.case_id != case.id:
        raise HTTPException(404, "Pack not found")
    if p.status != "export_ready":
        raise HTTPException(400, "Pack must be supervisor-endorsed (export_ready) before export")
    rep = build_report(db, case)
    files = {f.id: f for f in db.execute(select(SourceFile).where(SourceFile.case_id == case.id)).scalars()}
    storage = get_storage()
    manifest = {"pack_id": p.id, "case_id": case.id, "data_status": "SYNTHETIC DATA" if case.is_synthetic else "UPLOADED DATA", "fields": p.fields,
                "generated_at": datetime.now(timezone.utc).isoformat(), "generated_by": user.id, "endorsed_by": p.endorsed_by,
                "attachments": [], "money_trail": rep["fund_paths"][:25], "infrastructure_observations": rep["infrastructure_observations"][:50],
                "relationships": rep["relationships"][:150], "counter_evidence": rep["counter_evidence"], "disclaimer": rep["disclaimer"],
                "note": "Manual handoff pack. Submit through the official cooperation request channel; nothing is transmitted by this tool."}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for label, fid in [("fir", p.fir_file_id), ("endorsement", p.endorsement_file_id)] + [("attachment", x) for x in p.attachment_file_ids]:
            f = files.get(fid or "")
            if not f:
                continue
            data = storage.get(f.storage_key, expected_sha256=f.sha256)
            name = f"{label}/{f.original_name}"
            z.writestr(name, data)
            manifest["attachments"].append({"role": label, "name": f.original_name, "sha256": f.sha256, "zip_path": name})
        z.writestr("manifest.json", json.dumps(manifest, indent=1, default=str))
        rows = [[k.replace("_", " "), str(p.fields.get(k, "")) or "—"] for k in REQUIRED]
        pdf = simple_table_pdf(f"Investigation cooperation request pack — {case.title}", [manifest["data_status"], manifest["note"], rep["disclaimer"]],
                               [("Request fields", ["Field", "Value"], rows),
                                ("Attachments (SHA-256)", ["Role", "File", "SHA-256"], [[a["role"], a["name"], a["sha256"]] for a in manifest["attachments"]]),
                                ("Money trail (first paths)", ["Hops", "Accounts", "Entry", "Exit", "Status"], [[x["hop_count"], " → ".join(x["accounts"]), x["total_in_minor"], x["exit_amount_minor"], x.get("status", "")] for x in rep["fund_paths"][:15]])])
        z.writestr("cooperation_request_summary.pdf", pdf)
    p.exported_at = datetime.now(timezone.utc)
    audit.record(db, "cooperation.exported", actor_id=user.id, case_id=case.id, target_type="cooperation_pack", target_id=p.id, detail={"attachments": len(manifest["attachments"])})
    db.commit()
    return Response(buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="cooperation_pack_{case.id[:8]}.zip"'})
