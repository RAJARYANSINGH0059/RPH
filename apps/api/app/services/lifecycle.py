"""Operation lifecycle and functional-dependency reconstruction.

Taxonomy: the seven-stage lifecycle published by the FATF in *Combating End-to-End Illicit Financial Flows Linked to Scam
Compounds* (5 November 2026), grouped upstream / payment window / downstream, with its functional-dependency concept
(54 dependencies, 14 potentially critical depending on the operation). PS05-X applies that attributed framework to case
evidence; it did not invent it. A stage with no supplied evidence is NOT_SUPPLIED, never "did not happen". A bank, telco,
cloud/CDN, registrar or payment provider is never labelled a criminal dependency because it appears in the evidence.
"""
from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import Case, Entity, EvidenceItem, Relationship, SourceFile, Transaction
from app.services.contract import finding, result

LIFECYCLE_VERSION = "1.0.0"
ATTRIBUTION = {"framework": "FATF seven-stage scam-operation lifecycle and functional dependencies",
               "source": "FATF, Combating End-to-End Illicit Financial Flows Linked to Scam Compounds, 5 November 2026",
               "url": "https://www.fatf-gafi.org/en/publications/Methodsandtrends/combating-illicit-financial-flows-linked-to-scam-compounds.html",
               "note": "Stage labels below paraphrase the report's grouping (upstream set-up/recruitment/victim acquisition; payment-window scam execution; downstream collection, movement/laundering, cash-out/reinvestment). PS05-X applies the framework; it does not claim authorship of it."}
STAGES = [
    {"key": "S1", "label": "Establishing the operation", "group": "upstream", "hint": "infrastructure set-up: domains, hosting, registration, tooling"},
    {"key": "S2", "label": "Recruiting workers", "group": "upstream", "hint": "job offers, recruitment contacts, forced-labour indicators (human review only)"},
    {"key": "S3", "label": "Acquiring victims", "group": "upstream", "hint": "advertising, messages, calls, lures"},
    {"key": "S4", "label": "Executing the scam", "group": "payment_window", "hint": "deception, payment pages, instructions shown to the victim"},
    {"key": "S5", "label": "Collecting payments", "group": "downstream", "hint": "victim-origin credits into collection accounts"},
    {"key": "S6", "label": "Moving and laundering funds", "group": "downstream", "hint": "onward transfers, splits, layering"},
    {"key": "S7", "label": "Cashing out and reinvesting", "group": "downstream", "hint": "cash withdrawals, exits, asset purchases, reinvestment"},
]
STATES = ["DIRECTLY_OBSERVED", "CORROBORATED", "DERIVED", "CANDIDATE", "CONTRADICTED", "NOT_SUPPLIED", "PARTIAL", "NOT_APPLICABLE", "UNASSESSED"]
DEPENDENCY_CLASSES = ["recruitment_labour_sourcing", "victim_acquisition_advertising", "digital_platform_domain_hosting", "telecom_connectivity", "payment_collection",
                      "mule_intermediary_accounts", "financial_institutions_payment_intermediaries", "specialist_service_providers", "virtual_assets_vasp_otc",
                      "laundering_cash_out", "corporate_legal_beneficial_ownership", "physical_logistics_access_movement", "reinvestment_asset_holding"]
LEVERAGE = ["OBSERVED_USE", "CANDIDATE_DEPENDENCY", "CORROBORATED_DEPENDENCY", "IMPORTANCE_UNASSESSED", "POTENTIALLY_HIGH_LEVERAGE_REQUIRES_REVIEW"]
_RECRUIT = re.compile(r"\b(job|recruit|salary|work from home|vacancy|visa|data entry|hiring|offer letter|passport|agent fee)\b", re.I)
_LURE = re.compile(r"\b(sms|whatsapp|telegram|call|message|advert|link|group|customer care|parcel|kyc|lottery|loan|investment|trading)\b", re.I)


def _stage(key: str, state: str, events: list[dict], missing: list[str], hypotheses: list[str]) -> dict:
    s = next(x for x in STAGES if x["key"] == key)
    return {**s, "state": state, "events": events, "evidence_count": len(events), "missing_evidence": missing, "unresolved_hypotheses": hypotheses}


def build(db: Session, case: Case) -> dict:
    files = {f.id: f for f in db.execute(select(SourceFile).where(SourceFile.case_id == case.id)).scalars()}
    evs = db.execute(select(EvidenceItem).where(EvidenceItem.case_id == case.id)).scalars().all()
    txs = db.execute(select(Transaction).where(Transaction.case_id == case.id)).scalars().all()
    ents = {e.id: e for e in db.execute(select(Entity).where(Entity.case_id == case.id)).scalars()}
    rels = db.execute(select(Relationship).where(Relationship.case_id == case.id)).scalars().all()
    alias = engine.alias_map(db, case)
    paths = engine.reconstruct_paths(db, case)
    holders = {alias.get(t.account_ref, t.account_ref) for t in txs}

    def ev_ref(e: EvidenceItem, label: str, cls: str) -> dict:
        f = files.get(e.source_file_id)
        return {"evidence_id": e.id, "label": label, "class": cls, "file": f.original_name if f else None, "sha256": f.sha256 if f else None, "locator": e.source_locator,
                "event_time": e.event_time_start.isoformat() if e.event_time_start else None, "observed_at": e.observed_at.isoformat() if e.observed_at else None}

    by_stage: dict[str, list[dict]] = defaultdict(list)
    stage_state: dict[str, str] = {}
    # S1 establishing: registration + hosting observations
    for e in evs:
        nv = e.normalised_value or {}
        if e.source_type == "technical_observation":
            if nv.get("type") == "rdap":
                by_stage["S1"].append(ev_ref(e, f"registration observed for {nv.get('domain')} (registrar {nv.get('registrar')}; created {nv.get('created')})", "DIRECTLY_OBSERVED"))
            elif nv.get("type") in {"hosting", "cdn", "dns"}:
                rel = next((r for r in rels if r.observed_at == e.observed_at and r.relationship_type in {"RESOLVES_TO", "HOSTED_ON"} and (ents.get(r.source_entity_id) or Entity()).key == str(nv.get("domain") or "").lower()), None)
                cls = "CONTRADICTED" if rel and rel.evidence_level.value in {"stale", "contradicted"} else "DIRECTLY_OBSERVED"
                by_stage["S1"].append(ev_ref(e, f"{nv.get('type')} observation {nv.get('domain') or ''} → {nv.get('ip') or nv.get('provider') or ''}", cls))
        if e.source_type in {"complaint", "document"} and e.extraction_method in {"text_layer", "ocr", "paragraph", "line", "text", "plain", "docx_paragraph"} and e.raw_value:
            txt = e.raw_value
            if _RECRUIT.search(txt):
                by_stage["S2"].append(ev_ref(e, "document mentions recruitment / job / travel terms (reported; human review required before any inference)", "CANDIDATE"))
            if _LURE.search(txt):
                by_stage["S3"].append(ev_ref(e, "complaint describes how contact was made (reported by complainant)", "CANDIDATE" if e.extraction_method == "ocr" else "DIRECTLY_OBSERVED"))
                by_stage["S4"].append(ev_ref(e, "complaint describes the deception and payment request (reported)", "CANDIDATE" if e.extraction_method == "ocr" else "DIRECTLY_OBSERVED"))
        if e.source_type == "payment_instruction":
            by_stage["S4"].append(ev_ref(e, f"payment instruction extracted → {nv.get('payee_vpa')}", "DERIVED"))
        if e.source_type in {"complaint", "document"} and e.extraction_method.startswith("regex_") and (e.normalised_value or {}).get("indicator_kind") in {"url", "domain"}:
            by_stage["S3"].append(ev_ref(e, f"URL/domain named in document: {(e.normalised_value or {}).get('value')}", "DIRECTLY_OBSERVED"))
    # S5-S7 from paths and transactions
    victims = {p["accounts"][0] for p in paths}
    for p in paths:
        for i, h in enumerate(p["hops"]):
            e = next((x for x in evs if x.id == h["evidence_item_id"]), None)
            if e is None:
                continue
            cls = "CORROBORATED" if h["hop_class"] == "corroborated" else ("CANDIDATE" if h["hop_class"] == "uncertain_time" else "DIRECTLY_OBSERVED")
            if i == 0 and h["src"] in victims:
                by_stage["S5"].append(ev_ref(e, f"victim-origin transfer ₹{h['amount_minor'] / 100:,.2f} {h['src']} → {h['dst']}", cls))
            else:
                by_stage["S6"].append(ev_ref(e, f"onward transfer ₹{h['amount_minor'] / 100:,.2f} {h['src']} → {h['dst']} {' '.join(h['flags'])}", cls))
    for t in txs:
        if t.channel == "CASH" and t.direction == "debit" and t.amount_minor:
            e = next((x for x in evs if x.id == t.evidence_item_id), None)
            if e:
                by_stage["S7"].append(ev_ref(e, f"cash withdrawal ₹{t.amount_minor / 100:,.2f} from {t.account_ref}", "DIRECTLY_OBSERVED"))
    unresolved_ends = [p for p in paths if p["status"] == "unresolved"]
    stages = []
    for s in STAGES:
        items = by_stage.get(s["key"], [])
        classes = {i["class"] for i in items}
        if not items:
            state = "NOT_SUPPLIED"
        elif classes <= {"CANDIDATE"}:
            state = "CANDIDATE"
        elif "CONTRADICTED" in classes and len(classes) == 1:
            state = "CONTRADICTED"
        elif "CORROBORATED" in classes:
            state = "CORROBORATED"
        elif "DIRECTLY_OBSERVED" in classes:
            state = "DIRECTLY_OBSERVED"
        else:
            state = "DERIVED"
        if s["key"] == "S7" and unresolved_ends and not items:
            state = "PARTIAL"
        missing = {"S1": ["historical DNS / registration history for the campaign domain(s)"] if not items else [],
                   "S2": ["recruitment communications, job adverts or contracts (lawfully obtained) — none supplied"] if not items else ["human review of recruitment indicators"],
                   "S3": ["message/SMS/email export showing first contact"] if not items else [],
                   "S4": ["payment-page capture or QR image"] if not any("payment instruction" in i["label"] for i in items) else [],
                   "S5": ["victim statement(s)"] if not items else [],
                   "S6": [f"statement of {p['accounts'][-1]}" for p in unresolved_ends][:5],
                   "S7": ["statements of exit accounts; cash-out or asset records"] if state != "DIRECTLY_OBSERVED" else []}[s["key"]]
        hyps = {"S6": [f"onward movement from {p['accounts'][-1]} unknown" for p in unresolved_ends][:5], "S2": ["whether any account holder was recruited/deceived is UNASSESSED (see role review)"]}.get(s["key"], [])
        stage_state[s["key"]] = state
        stages.append(_stage(s["key"], state, items[:40], missing, hyps))

    # dependencies
    deps = []
    hosting = [r for r in rels if r.relationship_type == "HOSTED_ON"]
    for r in hosting:
        host = ents.get(r.target_entity_id)
        ip = ents.get(r.source_entity_id)
        if not host:
            continue
        multi = bool((host.attributes or {}).get("is_cdn") or (r.attributes or {}).get("multi_tenant"))
        domains = sorted({ents[x.source_entity_id].key for x in rels if x.relationship_type == "RESOLVES_TO" and x.target_entity_id == r.source_entity_id and x.source_entity_id in ents})
        deps.append({"dependency_class": "digital_platform_domain_hosting", "role": f"hosting/CDN for {', '.join(domains) or ip.key if ip else '?'}", "provider": host.label,
                     "stages": ["S1", "S3", "S4"], "status": "OBSERVED_USE", "leverage": "IMPORTANCE_UNASSESSED", "first_observed": r.observed_at.isoformat() if r.observed_at else None,
                     "evidence_ids": [], "repeat_use": len(domains), "benign_alternative": "Mainstream hosting/CDN providers serve many unrelated customers; use is not coordination or control." if multi else "A hosting provider serves unrelated customers; use is not control.",
                     "replaceability": "unknown (no evidence supplied on cost/time to re-host)", "known_unknowns": ["provider abuse-desk records not supplied", "who paid for the hosting is unknown"],
                     "review_status": "unreviewed", "authorised_next_step": "Draft a preservation/information request to the provider (Preservation Desk); no takedown or disclosure is performed here."})
    # payment collection + mule accounts from paths
    collection: dict[str, dict] = {}
    for p in paths:
        if not p["hops"]:
            continue
        first = p["hops"][0]
        d = collection.setdefault(first["dst"], {"victims": set(), "amount": 0, "ev": []})
        d["victims"].add(first["src"])
        d["amount"] += first["amount_minor"]
        d["ev"].append(first["evidence_item_id"])
    for acct, d in sorted(collection.items()):
        corroborated = any(h["corroborated"] for p in paths for h in p["hops"][:1] if h["dst"] == acct)
        n_v = len(d["victims"])
        lev = "POTENTIALLY_HIGH_LEVERAGE_REQUIRES_REVIEW" if (n_v >= 2 and corroborated) else "IMPORTANCE_UNASSESSED"
        deps.append({"dependency_class": "payment_collection", "role": f"collection account receiving victim-origin transfers from {n_v} victim account(s)", "provider": acct,
                     "stages": ["S5"], "status": "CORROBORATED_DEPENDENCY" if corroborated else "OBSERVED_USE", "leverage": lev, "evidence_ids": d["ev"][:10], "repeat_use": n_v,
                     "amount_minor_distinct": d["amount"], "benign_alternative": "The account received the funds; who operated it, and with what knowledge, is a separate question (Account Role & Context Review).",
                     "replaceability": "unknown", "known_unknowns": ["account-holder KYC/control records not supplied"], "review_status": "unreviewed",
                     "authorised_next_step": "Request account-opening and operation records through the Preservation Desk; no hold or freeze is initiated here.",
                     "leverage_reason": f"{n_v} independently evidenced victim paths converge here and the first hop is corroborated by two statements." if lev.startswith("POTENTIALLY") else "Single path or uncorroborated: importance unassessed."})
    for acct in sorted({h["dst"] for p in paths for h in p["hops"][1:]}):
        deps.append({"dependency_class": "mule_intermediary_accounts", "role": "intermediary account on an onward hop", "provider": acct, "stages": ["S6"], "status": "OBSERVED_USE",
                     "leverage": "IMPORTANCE_UNASSESSED", "evidence_ids": [h["evidence_item_id"] for p in paths for h in p["hops"][1:] if h["dst"] == acct][:5],
                     "repeat_use": sum(1 for p in paths for h in p["hops"][1:] if h["dst"] == acct), "benign_alternative": "Receipt of funds is not knowledge or intent; the holder may be a recruited, deceived or compromised party.",
                     "replaceability": "unknown", "known_unknowns": ["own statement " + ("supplied" if acct in holders else "NOT supplied")], "review_status": "unreviewed", "authorised_next_step": "Statement request draft."})
    banks = sorted({(t.account_ref, (e.attributes or {}).get("bank")) for t in txs for e in [ents.get(next((k for k, v in ents.items() if v.key == t.account_ref), ""), None)] if e} )
    if txs:
        deps.append({"dependency_class": "financial_institutions_payment_intermediaries", "role": "banks / UPI apps that carried the transfers (channels: " + ", ".join(sorted({t.channel for t in txs})) + ")",
                     "provider": "regulated payment system participants", "stages": ["S5", "S6", "S7"], "status": "OBSERVED_USE", "leverage": "IMPORTANCE_UNASSESSED", "evidence_ids": [],
                     "repeat_use": len(banks), "benign_alternative": "Regulated institutions processing customer instructions are not operation dependencies in any culpable sense.",
                     "replaceability": "not applicable", "known_unknowns": [], "review_status": "not_applicable", "authorised_next_step": "Information requests through lawful channels only."})
    phones = [e for e in ents.values() if e.entity_type == "phone"]
    if phones:
        deps.append({"dependency_class": "telecom_connectivity", "role": f"{len(phones)} phone number(s) named in documents", "provider": "telecom operators (unknown)", "stages": ["S3"], "status": "CANDIDATE_DEPENDENCY",
                     "leverage": "IMPORTANCE_UNASSESSED", "evidence_ids": [], "repeat_use": len(phones), "benign_alternative": "A number named in a complaint may be spoofed, recycled or unrelated.",
                     "replaceability": "unknown", "known_unknowns": ["subscriber and CDR records not supplied; a number alone does not identify a person"], "review_status": "unreviewed",
                     "authorised_next_step": "Draft a lawful subscriber-detail request; nothing is sent from here."})
    gaps = [{"stage": s["key"], "label": s["label"], "state": s["state"], "missing": s["missing_evidence"]} for s in stages if s["state"] in {"NOT_SUPPLIED", "PARTIAL", "CANDIDATE"}]
    findings = [finding("stage_state", f"{s['label']}: {s['state']}", evidence_class={"DIRECTLY_OBSERVED": "observed", "CORROBORATED": "corroborated", "DERIVED": "derived", "CANDIDATE": "candidate",
                        "CONTRADICTED": "contradicted"}.get(s["state"], "unresolved"), evidence_refs=[i["evidence_id"] for i in s["events"][:5]], stage=s["key"]) for s in stages]
    return result(case, "operation_lifecycle", LIFECYCLE_VERSION, findings=findings, input_evidence_ids=[i["evidence_id"] for s in stages for i in s["events"]],
                  uncertainties=[h for s in stages for h in s["unresolved_hypotheses"]], limitations=[ATTRIBUTION["note"], "NOT_SUPPLIED means no evidence was supplied for the stage, not that the stage did not occur.",
                  "No provider, platform, bank or telecom is labelled a criminal enabler because it appears here; 'potentially high leverage' is a review hypothesis with stated evidence."],
                  attribution=ATTRIBUTION, stages=stages, dependencies=deps, states=STATES, dependency_classes=DEPENDENCY_CLASSES, leverage_labels=LEVERAGE, evidence_gaps=gaps)
