from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_case_or_404, get_current_user
from app.db.session import get_db
from app.models import Case, Transaction, User
from app.reports.builder import build_report, report_pdf
from app.services import audit

router = APIRouter(prefix="/cases/{case_id}/report", tags=["reports"])


@router.get(".json")
def report_json(case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rep = build_report(db, case)
    audit.record(db, "report.exported", actor_id=user.id, case_id=case.id, detail={"format": "json"})
    db.commit()
    return rep


@router.get(".pdf")
def report_pdf_route(case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rep = build_report(db, case)
    pdf = report_pdf(rep)
    audit.record(db, "report.exported", actor_id=user.id, case_id=case.id, detail={"format": "pdf", "bytes": len(pdf)})
    db.commit()
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="ps05x_report_{case.id[:8]}.pdf"'})


@router.get("/transactions.csv")
def transactions_csv(case: Case = Depends(get_case_or_404), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(select(Transaction).where(Transaction.case_id == case.id).order_by(Transaction.datetime_utc)).scalars().all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["SYNTHETIC DATA" if case.is_synthetic else "UPLOADED DATA", "PS05-X export", "investigative aid; human verification required"])
    w.writerow(["id", "datetime_utc", "datetime_raw", "time_precision", "account", "direction", "amount_minor", "amount_raw", "counterparty", "reference", "channel", "balance_after_minor", "warnings", "evidence_item_id"])
    for t in rows:
        w.writerow([t.id, t.datetime_utc.isoformat() if t.datetime_utc else "", t.datetime_raw, t.time_precision, t.account_ref, t.direction, t.amount_minor, t.amount_raw,
                    t.counterparty_ref, t.external_reference, t.channel, t.balance_after_minor, "|".join(t.warnings or []), t.evidence_item_id])
    audit.record(db, "report.exported", actor_id=user.id, case_id=case.id, detail={"format": "csv"})
    db.commit()
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="ps05x_transactions_{case.id[:8]}.csv"'})
