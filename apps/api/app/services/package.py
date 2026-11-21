"""Proof-carrying investigation package: one ZIP with the report, every path's proof manifest, the analytical results that carry
their own assumptions and limitations, hypotheses with dissent, evidence requests with their response history, role reviews, the
case audit history and a manifest of SHA-256 digests. It never contains sealed ground truth, credentials or raw uploaded bytes
(those are downloadable separately and their hashes are listed in report.json)."""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import AuditEvent, Case, EvidenceRequest, Hypothesis, IndependentReview, RoleReview, User
from app.reports.builder import build_report
from app.services import adversary, bounded_flow, completeness, coverage, dependencies, integrity, lifecycle, proof, temporal

PACKAGE_VERSION = "1.0.0"
# JSON keys that only exist in sealed truth; the build refuses to emit an entry containing any of them
FORBIDDEN_KEYS = ('"sealed_truth"', '"false_edges"', '"mule_accounts"', '"simulated_allocation"')
LIMITATIONS = """# Limitations of this package

* SHA-256 digests prove that each entry matches what the system produced at generation time; they do not prove the authenticity of any
  source, the truth of its contents or legal admissibility.
* Bounded attribution values are feasible ranges under recorded constraints; they are not traced rupees. FIFO/LIFO scenarios, where present,
  are assumptions.
* Missing evidence is reported as NOT_SUPPLIED, never as zero or absence. Current DNS/RDAP observations are current-only.
* Hypotheses, alternatives, challenge states and dissent are investigative reasoning, not findings of fact, control, knowledge or intent.
* Evidence requests are drafts; a status of sent_manual records a dispatch made by an officer outside this system.
* Nothing in this package was transmitted to any bank, portal or provider, and no account was frozen, notified or acted upon.
* Synthetic cases are fictional; nothing in them refers to a real person.
"""


def _row(obj) -> dict:
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns}


def build(db: Session, case: Case, user: User) -> tuple[bytes, dict]:
    entries: dict[str, bytes] = {}

    def put(name: str, obj) -> None:
        entries[name] = json.dumps(obj, indent=1, default=str, sort_keys=True).encode("utf-8")

    rep = build_report(db, case)
    put("report.json", rep)
    paths = engine.reconstruct_paths(db, case)
    for i in range(min(len(paths), 25)):
        try:
            put(f"proof/path_{i}.json", proof.build_manifest(db, case, i))
        except Exception as exc:  # never fabricate a certificate
            put(f"proof/path_{i}.json", {"error": f"{type(exc).__name__}: {exc}", "note": "proof manifest unavailable for this path"})
    analyses = [("analysis/bounded_flow.json", lambda: bounded_flow.analyse(db, case)), ("analysis/coverage.json", lambda: coverage.coverage_report(db, case)),
                ("analysis/lifecycle.json", lambda: lifecycle.build(db, case)), ("analysis/dependencies.json", lambda: dependencies.dependency_map(db, case)),
                ("analysis/ivoi.json", lambda: dependencies.ivoi_rank(db, case)), ("analysis/completeness.json", lambda: completeness.checklist(db, case)),
                ("analysis/adversary.json", lambda: adversary.challenge_all(db, case)), ("analysis/integrity.json", lambda: integrity.case_report(db, case)),
                ("analysis/temporal.json", lambda: temporal.fusion(db, case))]
    for name, fn in analyses:
        try:
            put(name, fn())
        except Exception as exc:
            put(name, {"error": f"{type(exc).__name__}: {exc}", "note": "analysis unavailable; omitted rather than fabricated"})
    hyps = db.execute(select(Hypothesis).where(Hypothesis.case_id == case.id).order_by(Hypothesis.created_at)).scalars().all()
    reviews = db.execute(select(IndependentReview).where(IndependentReview.case_id == case.id)).scalars().all()
    put("reasoning/hypotheses.json", {"hypotheses": [_row(h) for h in hyps], "independent_reviews": [_row(r) for r in reviews],
                                      "note": "versions and dissent are preserved; nothing here is a finding of fact"})
    reqs = db.execute(select(EvidenceRequest).where(EvidenceRequest.case_id == case.id).order_by(EvidenceRequest.created_at)).scalars().all()
    put("evidence_requests/requests.json", {"requests": [dependencies.request_out(r) for r in reqs], "transmission": "never automatic"})
    rrs = db.execute(select(RoleReview).where(RoleReview.case_id == case.id)).scalars().all()
    put("reasoning/role_reviews.json", {"role_reviews": [_row(r) for r in rrs], "note": "propositions and claims; no guilt, victim or trafficking score exists"})
    audit_rows = db.execute(select(AuditEvent).where(AuditEvent.case_id == case.id).order_by(AuditEvent.created_at)).scalars().all()
    put("audit/audit_history.json", [_row(a) for a in audit_rows])
    entries["LIMITATIONS.md"] = LIMITATIONS.encode("utf-8")
    for name, data in entries.items():
        for key in FORBIDDEN_KEYS:
            if key.encode("utf-8") in data:
                raise RuntimeError(f"package entry {name} would contain sealed-truth key {key}; refusing to build")
    listing = [{"path": n, "sha256": hashlib.sha256(d).hexdigest(), "bytes": len(d)} for n, d in sorted(entries.items())]
    package_sha = hashlib.sha256("\n".join(f"{e['path']}:{e['sha256']}" for e in listing).encode()).hexdigest()
    manifest = {"package_version": PACKAGE_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(), "generated_by": user.id,
                "case": {"id": case.id, "title": case.title, "data_status": "SYNTHETIC DATA" if case.is_synthetic else "UPLOADED DATA"},
                "entries": listing, "package_sha256": package_sha, "paths_included": min(len(paths), 25), "paths_total": len(paths),
                "excluded": ["sealed ground truth", "credentials and keys", "raw uploaded bytes (download separately; SHA-256 per file is in report.json)"],
                "verification": {"proof_manifests": "python scripts/verify_proof.py proof/path_N.json --files <directory with the original files>",
                                 "entries": "sha256 of each entry must equal the listed digest; package_sha256 = sha256 of 'path:sha256' lines joined by newlines in path order"},
                "disclaimer": rep.get("disclaimer")}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n, d in sorted(entries.items()):
            z.writestr(n, d)
        z.writestr("manifest.json", json.dumps(manifest, indent=1, default=str))
    return buf.getvalue(), manifest
