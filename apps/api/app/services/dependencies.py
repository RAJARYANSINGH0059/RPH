"""Missing-evidence dependency map, Evidence Acquisition Intelligence (requirements → custodians → scoped draft requests),
Investigative Value of Information (IVOI) ranking and preservation intelligence.

Questions → required evidence → available/missing evidence → affected findings. IVOI is a deterministic, transparent ranking
with component contributions (not a probability, not an expected recovery amount). Retention deadlines are shown only when a
request carries a verified policy source; otherwise RETENTION NOT VERIFIED. Nothing is transmitted by the system: the
lifecycle moves to `sent_manual` only when an authorised officer records an actual dispatch.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import Case, EvidenceItem, EvidenceRequest, Hypothesis, PaymentInstruction, Relationship, Transaction, User
from app.services import audit, claims, coverage
from app.services.contract import finding, result

IVOI_VERSION = "1.1.0"
REQUEST_STATUSES = ["identified", "draft", "under_review", "authorised", "sent_manual", "externally_confirmed", "partial_response", "received", "reviewed", "closed", "rejected", "unavailable", "expired"]
TRANSITIONS = {"identified": {"draft", "closed", "rejected"}, "suggested": {"draft", "closed", "rejected"}, "draft": {"under_review", "closed", "rejected"},
               "under_review": {"authorised", "draft", "rejected", "closed"}, "authorised": {"sent_manual", "closed", "rejected"},
               "sent_manual": {"externally_confirmed", "partial_response", "received", "unavailable", "expired", "closed"},
               "externally_confirmed": {"partial_response", "received", "unavailable", "expired", "closed"}, "partial_response": {"partial_response", "received", "reviewed", "unavailable", "closed"},
               "received": {"reviewed", "closed"}, "reviewed": {"closed"}, "rejected": {"draft", "closed"}, "unavailable": {"closed"}, "expired": {"draft", "closed"}, "closed": set()}
VOLATILITY = {"hosting": "high (logs/content rotate quickly)", "registrar": "medium", "telecom": "medium (CDR retention varies by operator and law)", "payment_app": "medium",
              "bank": "low (statements are durable records)", "isp": "high", "platform": "high", "police": "low", "other": "unknown"}
# Controlled catalogue of record categories and potential custodians. Procedural/legal fields are NOT asserted here: they are
# marked for authorised validation. Source: project research register (docs/GLOBAL_COMPETITIVE_LANDSCAPE.md) — no SOP text was supplied.
CATALOGUE = {
    "account_statement": {"custodian_type": "bank", "label": "Account statement (all credits/debits with UTR, counterparty, running balance)", "identifiers": ["account number", "IFSC/bank", "period"],
                          "source_ref": "research register §9 (banks execute holds/records through lawful process)", "legal_fields_requiring_validation": ["legal basis / section", "authorised signatory", "recipient nodal officer"]},
    "account_opening_kyc": {"custodian_type": "bank", "label": "Account-opening / KYC record (holder of record, documents submitted, opening date, introducer)", "identifiers": ["account number"],
                            "source_ref": "research register §6.3", "legal_fields_requiring_validation": ["legal basis / section", "authorised signatory"]},
    "channel_session_device": {"custodian_type": "bank", "label": "Channel/session/device records for specific transactions (login IP, device id, app, timestamp)", "identifiers": ["account number", "UTR", "timestamp window"],
                               "source_ref": "research register §6.3 (device/session records only when authorised)", "legal_fields_requiring_validation": ["legal basis / section", "authorised signatory", "data minimisation note"]},
    "upi_transaction_log": {"custodian_type": "payment_app", "label": "UPI app / PSP transaction log (payee VPA, UTR, device, timestamp)", "identifiers": ["VPA", "UTR", "period"],
                            "source_ref": "research register §2.4", "legal_fields_requiring_validation": ["legal basis / section", "authorised signatory"]},
    "hold_confirmation": {"custodian_type": "bank", "label": "Hold / lien confirmation with balance at hold time and subsequent debits", "identifiers": ["account number", "hold reference"],
                          "source_ref": "research register §9 (CFCFRMS/bank holds are executed by banks, not by this tool)", "legal_fields_requiring_validation": ["legal basis / section"]},
    "hosting_customer_records": {"custodian_type": "hosting", "label": "Hosting/CDN customer records for an IP or domain during a window", "identifiers": ["IP", "domain", "window"],
                                 "source_ref": "research register §6.5 (shared hosting is a pivot only)", "legal_fields_requiring_validation": ["legal basis / section", "jurisdiction of provider"]},
    "registrar_records": {"custodian_type": "registrar", "label": "Registrar registration and payment records for a domain", "identifiers": ["domain"], "source_ref": "research register §6.5",
                          "legal_fields_requiring_validation": ["legal basis / section", "jurisdiction of registrar"]},
    "subscriber_cdr": {"custodian_type": "telecom", "label": "Subscriber details / call-data records for a number (narrow window)", "identifiers": ["phone number", "window"],
                       "source_ref": "research register §11 (a number alone does not identify a person)", "legal_fields_requiring_validation": ["legal basis / section", "authorised signatory"]},
    "victim_app_history": {"custodian_type": "payment_app", "label": "Victim's own payment-app history for payments to the instructed payee", "identifiers": ["victim VPA", "payee VPA", "period"],
                           "source_ref": "research register §6.2", "legal_fields_requiring_validation": ["victim consent / authorisation"]},
}


def _req(rid, qid, catalogue_key, entity, window, could, could_not, extra_fields=None):
    cat = CATALOGUE[catalogue_key]
    return {"id": rid, "question_id": qid, "catalogue_key": catalogue_key, "evidence": cat["label"], "organisation_type": cat["custodian_type"], "custodian_note": "A suggested custodian type is not confirmation that the custodian holds the record.",
            "target_entity": entity, "window": window, "required_fields": list(cat["identifiers"]) + list(extra_fields or []), "could_resolve": could, "would_not_establish": could_not,
            "source_ref": cat["source_ref"], "legal_fields_requiring_validation": cat["legal_fields_requiring_validation"], "data_minimisation": "Narrowest period and minimum identifiers for the stated question."}


def dependency_map(db: Session, case: Case) -> dict:
    paths = engine.reconstruct_paths(db, case)
    cov = coverage.coverage_report(db, case)
    rec = claims.reconcile(db, case)
    rels = db.execute(select(Relationship).where(Relationship.case_id == case.id)).scalars().all()
    pis = db.execute(select(PaymentInstruction).where(PaymentInstruction.case_id == case.id)).scalars().all()
    hyps = db.execute(select(Hypothesis).where(Hypothesis.case_id == case.id)).scalars().all()
    reqs = db.execute(select(EvidenceRequest).where(EvidenceRequest.case_id == case.id)).scalars().all()
    questions, requirements, links = [], [], []
    req_by_target = {(r.target_entity, (r.ranking or {}).get("catalogue_key")): r for r in reqs}

    def add_q(qid, text, related, hypotheses, impact, priority):
        questions.append({"id": qid, "question": text, "related_entities": [x for x in related if x], "competing_hypotheses": hypotheses, "impact": impact, "priority": priority})

    def add_req(r):
        existing = req_by_target.get((r["target_entity"], r["catalogue_key"]))
        r["status"] = existing.status if existing else "identified"
        r["request_id"] = existing.id if existing else None
        r["responses"] = responses_of(existing) if existing else []
        r["unresolved_remainder"] = unresolved_remainder(existing) if existing else None
        requirements.append(r)
        links.append({"from": r["question_id"], "to": r["id"], "type": "REQUIRES_EVIDENCE"})

    for i, p in enumerate(paths):
        if p["status"] != "unresolved":
            continue
        last, prev = p["accounts"][-1], p["accounts"][-2] if len(p["accounts"]) > 1 else None
        t_last = p["hops"][-1]["time"]
        qid = f"Q-hop-{i}"
        add_q(qid, f"Did funds move onward from {last} after {t_last[:10] if t_last else 'the last hop'}?", [last, prev],
              ["onward transfer happened", "funds remained", "funds were withdrawn as cash", "the hop is a duplicate or refers to a different transfer"], {"paths": [i], "recovery": "changes reconciliation for claims traced into this account"}, "high")
        win = [(datetime.fromisoformat(t_last) - timedelta(days=1)).isoformat(), (datetime.fromisoformat(t_last) + timedelta(days=30)).isoformat()] if t_last else None
        add_req(_req(f"R-stmt-{last}", qid, "account_statement", last, win, ["whether the amount moved onward and where", "amount remaining / withdrawn"], ["who operated the account", "knowledge or intent of the holder"]))
    for s in cov["statements"]:
        for g in s["gaps"]:
            qid = f"Q-gap-{s['subject']}-{g['from'][:10]}"
            add_q(qid, f"What happened in {s['subject']} between {g['from'][:10]} and {g['to'][:10]} (balance moves by {g['unexplained_balance_change_minor']} paise with no rows)?", [s["subject"]],
                  ["rows for the period are missing from the supplied file", "the export skipped a page", "the balance column is wrong"], {"coverage": "PARTIAL_COVERAGE → COMPLETE", "attribution": "narrows bounded attribution intervals"}, "high")
            add_req(_req(f"R-period-{s['subject']}-{g['from'][:10]}", qid, "account_statement", s["subject"], [g["from"], g["to"]], ["the unexplained balance change", "whether victim-origin funds left during the gap"], ["account control"]))
    # account-control questions for collection accounts (who initiated the onward transfers?)
    for p in paths:
        if len(p["accounts"]) > 1 and len(p["hops"]) > 1:
            acct = p["accounts"][1]
            qid = f"Q-control-{acct}"
            if any(q["id"] == qid for q in questions):
                continue
            hop = p["hops"][1]
            add_q(qid, f"Who initiated the onward transfer(s) from {acct}, and is the registered holder the same person?", [acct],
                  ["registered holder initiated knowingly", "holder was recruited/deceived and acted on instructions", "credentials/device controlled by another person", "account compromised"],
                  {"role_review": acct}, "medium")
            win = [(datetime.fromisoformat(hop["time"]) - timedelta(hours=6)).isoformat(), (datetime.fromisoformat(hop["time"]) + timedelta(hours=6)).isoformat()] if hop["time"] else None
            add_req(_req(f"R-kyc-{acct}", qid, "account_opening_kyc", acct, None, ["who is the holder of record"], ["who operated the account at the time"]))
            add_req(_req(f"R-session-{acct}", qid, "channel_session_device", acct, win, ["which device/session initiated the onward transfer"], ["the human behind the device", "knowledge or intent"], [f"UTR {hop['reference']}" if hop["reference"] else "UTR of the onward transfer"]))
    for r in rels:
        if r.relationship_type == "SHARED_INFRASTRUCTURE" and r.review_status.value == "unreviewed":
            a = r.attributes or {}
            qid = f"Q-infra-{r.id[:8]}"
            add_q(qid, f"Are the domains sharing IP {a.get('shared_ip')} operated together, or merely co-hosted?", [a.get("shared_ip")], ["common operator", "shared commercial hosting/CDN (default)", "IP reassigned between observations"],
                  {"relationship": r.id}, "low" if a.get("multi_tenant") else "medium")
            add_req(_req(f"R-host-{a.get('shared_ip')}", qid, "hosting_customer_records", str(a.get("shared_ip")), None, ["whether one customer controls both domains"], ["who physically operated the sites"]))
    for pi in pis:
        if not any(r.method_name == "payment_bridge" and (r.attributes or {}).get("instruction_id") == pi.id for r in rels) and (pi.payee_vpa or pi.reference):
            qid = f"Q-pi-{pi.id[:8]}"
            add_q(qid, f"Was the payment instructed to {pi.payee_vpa or pi.reference} actually made?", [pi.payee_vpa], ["payment made from an account whose statement is not supplied", "payment never made", "payee identifier differs by one character (OCR)"], {"bridge": pi.id}, "medium")
            add_req(_req(f"R-pi-{pi.id[:8]}", qid, "victim_app_history", str(pi.payee_vpa), None, ["whether and when the instructed payment was made"], ["who controls the payee account"]))
    for a in rec["accounts"]:
        if a["oversubscribed"]:
            qid = f"Q-hold-{a['account']}"
            add_q(qid, f"Which claims does the documented hold on {a['account']} relate to (traced inflow exceeds the held amount)?", [a["account"]], ["funds moved on before the hold", "hold covers part of several claims"], {"recovery": "allocation requires human/legal review"}, "medium")
            add_req(_req(f"R-hold-{a['account']}", qid, "hold_confirmation", a["account"], None, ["remaining balance available"], ["entitlement of any claimant"]))
    for h in hyps:
        if h.status in {"open", "under_review", "disputed"} and not h.supporting_evidence_ids:
            add_q(f"Q-hyp-{h.id[:8]}", f"Hypothesis '{h.title}' has no supporting evidence on file", list((h.subject_refs or {}).get("account_refs") or []), [h.statement] + list(h.alternatives or []), {"hypothesis": h.id}, "medium")
    available = [r["id"] for r in requirements if r["status"] in {"received", "reviewed", "partial_response"}]
    missing = [r["id"] for r in requirements if r["id"] not in available]
    partial = [{"id": r["id"], "remaining": r["unresolved_remainder"]} for r in requirements if r["status"] == "partial_response"]
    return result(case, "missing_evidence_dependency_map", IVOI_VERSION, findings=[finding("open_questions", f"{len(questions)} open question(s), {len(missing)} missing record(s)", evidence_class="derived")],
                  uncertainties=[q["question"] for q in questions][:20], limitations=["A requested record could establish the listed points; it is not guaranteed to resolve a hypothesis.",
                  "Nothing is sent anywhere; requests are drafts until an officer records a manual dispatch.", "Legal/procedural fields are marked for authorised validation; no legal power or deadline is asserted."],
                  questions=questions, requirements=requirements, available=available, missing=missing, partial=partial, links=links, what_remains_unproven=[q["question"] for q in questions], catalogue=CATALOGUE)


def ivoi_rank(db: Session, case: Case) -> dict:
    dm = dependency_map(db, case)
    reqs = {r.id: r for r in db.execute(select(EvidenceRequest).where(EvidenceRequest.case_id == case.id)).scalars()}
    q_by_id = {q["id"]: q for q in dm["questions"]}
    by_req: dict[str, dict] = {}
    for r in dm["requirements"]:
        slot = by_req.setdefault(r["catalogue_key"] + "|" + str(r["target_entity"]), {**r, "questions": []})
        slot["questions"].append(r["question_id"])
    weights = {"unresolved_links_affected": 2, "hypotheses_distinguished": 1, "broken_path_or_coverage_impact": 3, "reconciliation_or_attribution_impact": 2, "contradiction_resolution": 1,
               "uniquely_obtainable_from_one_source": 1, "verified_preservation_urgency": 2, "duplicate_of_existing_request": -4}
    ranked = []
    for r in by_req.values():
        qs = [q_by_id[q] for q in r["questions"] if q in q_by_id]
        existing = reqs.get(r.get("request_id") or "")
        retention = (existing.retention if existing else {}) or {}
        comp = {"unresolved_links_affected": weights["unresolved_links_affected"] * len(qs), "hypotheses_distinguished": sum(len(q["competing_hypotheses"]) for q in qs),
                "broken_path_or_coverage_impact": weights["broken_path_or_coverage_impact"] * (sum(len(q["impact"].get("paths", [])) for q in qs) + sum(1 for q in qs if "coverage" in q["impact"])),
                "reconciliation_or_attribution_impact": weights["reconciliation_or_attribution_impact"] * sum(1 for q in qs if "recovery" in q["impact"] or "attribution" in q["impact"]),
                "contradiction_resolution": sum(1 for q in qs if "relationship" in q["impact"]), "uniquely_obtainable_from_one_source": 1 if r["organisation_type"] in {"bank", "hosting", "registrar", "telecom"} else 0,
                "verified_preservation_urgency": 2 if retention.get("verified") else 0, "duplicate_of_existing_request": -4 if existing and existing.status not in {"identified", "suggested", "closed", "rejected", "expired"} else 0}
        score = sum(comp.values())
        ranked.append({**r, "score_not_probability": score, "priority_label": "high" if score >= 8 else "medium" if score >= 4 else "low", "components": comp,
                       "authorisation_caution": "Obtainable only through lawful process by an authorised officer; the system does not send requests.",
                       "retention": retention if retention else {"verified": False, "display": "RETENTION NOT VERIFIED"},
                       "draft": {"title": r["evidence"], "catalogue_key": r["catalogue_key"], "organisation_type": r["organisation_type"], "target_entity": r["target_entity"], "window": r["window"], "required_fields": r["required_fields"],
                                 "rationale": "; ".join(q["question"] for q in qs)[:900], "could_resolve": r["could_resolve"], "would_not_establish": r["would_not_establish"],
                                 "fields_requiring_authorised_completion": r["legal_fields_requiring_validation"] + ["purpose statement", "recipient", "final wording"]}})
    ranked.sort(key=lambda x: (-x["score_not_probability"], x["evidence"]))
    return result(case, "ivoi_next_best_evidence", IVOI_VERSION, findings=[finding("ivoi", f"{len(ranked)} evidence request suggestions ranked", evidence_class="derived")],
                  limitations=["The score is a transparent sum of component weights; it is not a probability of success, an expected recovery amount or a prediction of cooperation.",
                               "Preservation urgency counts only when a verified retention source is recorded on the request."], ranked=ranked, weights=weights)


def preservation_desk(db: Session, case: Case) -> dict:
    txs = db.execute(select(Transaction).where(Transaction.case_id == case.id, Transaction.datetime_utc.is_not(None))).scalars().all()
    first_tx = min((t.datetime_utc for t in txs), default=None)
    complaint = db.execute(select(EvidenceItem).where(EvidenceItem.case_id == case.id, EvidenceItem.source_type == "complaint").order_by(EvidenceItem.observed_at)).scalars().first()
    ingested = db.execute(select(EvidenceItem.ingested_at).where(EvidenceItem.case_id == case.id).order_by(EvidenceItem.ingested_at)).scalars().first()
    now = datetime.now(timezone.utc)
    clock = {"first_transaction": first_tx.isoformat() if first_tx else None, "first_report_ingested": complaint.observed_at.isoformat() if complaint and complaint.observed_at else None,
             "first_evidence_ingested": ingested.isoformat() if ingested else None, "now": now.isoformat(),
             "elapsed_since_first_transaction_hours": round((now - first_tx).total_seconds() / 3600, 1) if first_tx else None,
             "note": "Elapsed time is informational. No universal 24/72-hour statutory deadline is asserted; retention depends on provider, record class and jurisdiction."}
    queue = []
    for r in db.execute(select(EvidenceRequest).where(EvidenceRequest.case_id == case.id).order_by(EvidenceRequest.created_at)).scalars():
        ret = r.retention or {}
        verified = bool(ret.get("verified") and ret.get("source_url") and ret.get("period_days"))
        deadline = (first_tx + timedelta(days=int(ret["period_days"]))).isoformat() if verified and first_tx else None
        queue.append({"request_id": r.id, "title": r.title, "organisation_type": r.organisation_type, "status": r.status, "is_simulated": r.is_simulated, "volatility": VOLATILITY.get(r.organisation_type, "unknown"),
                      "retention": {"verified": verified, "source_url": ret.get("source_url"), "effective_date": ret.get("effective_date"), "period_days": ret.get("period_days"), "display": deadline or "RETENTION NOT VERIFIED"},
                      "urgency": "verified_deadline" if verified else "RETENTION_NOT_VERIFIED",
                      "explanation": "Deadline computed from the verified policy source recorded on this request." if verified else "No verified retention policy recorded: no deadline is shown or implied.",
                      "window": [r.window_from.isoformat() if r.window_from else None, r.window_to.isoformat() if r.window_to else None], "required_fields": r.required_fields, "legal_authority": r.legal_authority,
                      "requesting_officer": r.requesting_officer, "status_history": r.status_history})
    order = {"high": 0, "medium": 1, "low": 2}
    queue.sort(key=lambda q: (0 if q["urgency"] == "verified_deadline" else 1, order.get(q["volatility"].split(" ")[0], 3), q["title"]))
    return result(case, "preservation_desk", IVOI_VERSION, findings=[finding("queue", f"{len(queue)} request(s) in the preservation queue", evidence_class="derived")],
                  limitations=["No hold, freeze, lien, takedown, disclosure or dispatch is performed by the system.", "'sent_manual' means a human recorded an actual dispatch; it is never set automatically."],
                  clock=clock, queue=queue, statuses=REQUEST_STATUSES, transitions={k: sorted(v) for k, v in TRANSITIONS.items()})


def advance_request(db: Session, case: Case, user: User, rq: EvidenceRequest, new_status: str, note: str, *, actual_dispatch_details: str | None = None, response: dict | None = None) -> EvidenceRequest:
    if new_status not in TRANSITIONS.get(rq.status, set()):
        raise ValueError(f"cannot move from {rq.status} to {new_status}")
    if new_status == "sent_manual" and not actual_dispatch_details:
        raise ValueError("recording a manual dispatch requires the actual dispatch details (channel, date, reference) entered by the officer")
    if new_status == "authorised" and not (rq.legal_authority and rq.requesting_officer):
        raise ValueError("authorisation requires legal_authority and requesting_officer fields validated by an authorised investigator")
    rq.status_history = (rq.status_history or []) + [{"from": rq.status, "to": new_status, "by": user.id, "at": datetime.now(timezone.utc).isoformat(), "note": note, "dispatch_details": actual_dispatch_details, "response": response}]
    rq.status = new_status
    audit.record(db, "evidence_request.status", actor_id=user.id, case_id=case.id, target_type="evidence_request", target_id=rq.id, detail={"to": new_status, "note": note[:200]})
    return rq


def responses_of(r: EvidenceRequest) -> list[dict]:
    return [h["response"] for h in (r.status_history or []) if h.get("response")]


def unresolved_remainder(r: EvidenceRequest) -> str | None:
    """What the latest response left open; None once a full response is recorded."""
    rs = responses_of(r)
    if not rs:
        return None
    return rs[-1].get("remaining") or None


def request_out(r: EvidenceRequest) -> dict:
    return {"id": r.id, "title": r.title, "organisation_type": r.organisation_type, "catalogue_key": (r.ranking or {}).get("catalogue_key"), "target_record": r.target_record, "target_entity": r.target_entity,
            "window_from": r.window_from.isoformat() if r.window_from else None, "window_to": r.window_to.isoformat() if r.window_to else None, "required_fields": r.required_fields, "rationale": r.rationale,
            "could_resolve": r.could_resolve, "would_not_establish": r.would_not_establish, "ranking": r.ranking, "retention": r.retention or {"verified": False, "display": "RETENTION NOT VERIFIED"},
            "legal_authority": r.legal_authority, "requesting_officer": r.requesting_officer, "status": r.status, "status_history": r.status_history, "is_simulated": r.is_simulated,
            "created_at": r.created_at.isoformat() if r.created_at else None, "fields_requiring_authorised_completion": [f for f in ("legal_authority", "requesting_officer") if not getattr(r, f)] + ["recipient", "final wording"],
            "responses": responses_of(r), "unresolved_remainder": unresolved_remainder(r),
            "transmission": "never automatic; status sent_manual records a dispatch made by an officer outside this system"}
