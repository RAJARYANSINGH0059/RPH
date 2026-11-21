"""Fraud campaign evolution intelligence ("Campaign DNA").

Deterministic, versioned, explainable fingerprints per case across five dimensions; per-dimension similarity with
generic features down-weighted; qualitative LOW/MEDIUM/HIGH pattern-similarity labels, never a probability and never a
claim of common ownership or operator identity. Identifier rotation is detected only from time-ordered observations.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.graph import engine
from app.models import Case, Entity, EvidenceItem, PaymentInstruction, Relationship, Transaction, User
from app.services.contract import finding, result
from app.services.crosscase import authorised_cases

FINGERPRINT_VERSION = "campaign-fingerprint-1.0"
DIMENSIONS = ["page_structure", "payment_instruction_pattern", "financial_choreography", "message_template", "infrastructure_timeline"]
WEIGHTS = {"page_structure": 0.2, "payment_instruction_pattern": 0.2, "financial_choreography": 0.3, "message_template": 0.15, "infrastructure_timeline": 0.15}
GENERIC_TOKENS = {"login", "index", "home", "www", "http", "https", "com", "test", "pay", "secure", "support", "the", "and", "for", "was", "that", "with", "this", "from", "have", "been"}
_WORD = re.compile(r"[a-z]{3,}")
_IDENT = re.compile(r"[a-z0-9.\-_]+@[a-z][a-z0-9.\-]+|\b\d{9,}\b|\bSYN[A-Z0-9]{6,}\b|https?://\S+", re.I)


def _label(score: float | None) -> str:
    if score is None:
        return "insufficient"
    return "high" if score >= 0.6 else "medium" if score >= 0.42 else "low"


def _jaccard(a: set, b: set) -> float | None:
    if not a or not b:
        return None
    return len(a & b) / len(a | b)


def _bucket_amount(minor: int) -> str:
    v = minor / 100
    return "<1k" if v < 1000 else "1k-5k" if v < 5000 else "5k-25k" if v < 25000 else "25k-1L" if v < 100000 else ">1L"


def fingerprint(db: Session, case: Case) -> dict:
    """Versioned fingerprint. Raw personal identifiers are excluded; only structure is kept."""
    ents = db.execute(select(Entity).where(Entity.case_id == case.id)).scalars().all()
    rels = db.execute(select(Relationship).where(Relationship.case_id == case.id)).scalars().all()
    txs = db.execute(select(Transaction).where(Transaction.case_id == case.id)).scalars().all()
    paths = engine.reconstruct_paths(db, case)
    feats = engine.account_features(db, case)
    pis = db.execute(select(PaymentInstruction).where(PaymentInstruction.case_id == case.id)).scalars().all()
    docs = db.execute(select(EvidenceItem).where(EvidenceItem.case_id == case.id, EvidenceItem.source_type.in_(["complaint", "document"]),
                                                 EvidenceItem.extraction_method.in_(["text_layer", "ocr", "paragraph", "line", "text", "plain", "docx_paragraph"]))).scalars().all()
    html = db.execute(select(EvidenceItem).where(EvidenceItem.case_id == case.id, EvidenceItem.extraction_method == "html_structure")).scalars().all()
    urls = [e.key for e in ents if e.entity_type == "url"]
    path_tokens = {t for u in urls for t in re.split(r"[/?=&.\-_:]+", u.lower()) if t and t not in GENERIC_TOKENS and not t.isdigit()}
    tag_shingles = {s for h in html for s in ((h.normalised_value or {}).get("tag_shingles") or [])}
    page = {"url_path_tokens": sorted(path_tokens), "tag_shingles": sorted(tag_shingles), "captures": len(html)}
    vpas = [e.key for e in ents if e.entity_type == "vpa"]
    handles = Counter(v.split("@")[-1] for v in vpas if "@" in v)
    pi_params = {tuple(sorted(k for k in (p.fields or {}) if k not in {"pa_raw", "am_raw"})) for p in pis}
    note_words = {w for p in pis for w in _WORD.findall((p.note_raw or "").lower()) if w not in GENERIC_TOKENS}
    first_hops = [p["hops"][0] for p in paths if p["hops"]]
    pay = {"vpa_handles": sorted(handles), "instruction_param_sets": [list(s) for s in sorted(pi_params)], "note_words": sorted(note_words),
           "amount_buckets": sorted(Counter(_bucket_amount(h["amount_minor"]) for h in first_hops)), "channels": sorted({t.channel for t in txs if t.channel != "unknown"})}
    hold = []
    for p in paths:
        times = [h["time"] for h in p["hops"] if h["time"]]
        for a, b in zip(times, times[1:]):
            dh = (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 3600
            hold.append("<1h" if dh < 1 else "1-6h" if dh < 6 else "6-24h" if dh < 24 else "1-3d" if dh < 72 else ">3d")
    chore = {"hop_counts": sorted(Counter(p["hop_count"] for p in paths).items()), "flags": sorted({f for p in paths for f in p["flags"]}),
             "holding_buckets": sorted(Counter(hold).items()), "fan_in_max": max((f["fan_in"] for f in feats.values()), default=0), "fan_out_max": max((f["fan_out"] for f in feats.values()), default=0),
             "exit_channels": sorted({t.channel for p in paths for h in p["hops"][-1:] for t in txs if t.id == h["tx_id"]}), "victims": len({p["accounts"][0] for p in paths})}
    words = set()
    for d in docs:
        txt = _IDENT.sub(" ", (d.raw_value or "").lower())
        toks = [w for w in _WORD.findall(txt) if w not in GENERIC_TOKENS]
        words |= {" ".join(toks[i:i + 3]) for i in range(len(toks) - 2)}
    msg = {"trigram_count": len(words), "trigrams": sorted(words)[:400]}
    domains = [e for e in ents if e.entity_type == "domain"]
    name_tokens = {t for d in domains for t in re.split(r"[.\-]", d.key.lower()) if t and not t.isdigit() and t not in GENERIC_TOKENS}
    providers = []
    for r in rels:
        if r.relationship_type == "HOSTED_ON":
            tgt = next((e for e in ents if e.id == r.target_entity_id), None)
            if tgt:
                providers.append({"provider": tgt.label, "multi_tenant": bool((tgt.attributes or {}).get("is_cdn") or (r.attributes or {}).get("multi_tenant")), "observed_at": r.observed_at.isoformat() if r.observed_at else None})
    windows = [{"domain": next((e.key for e in ents if e.id == r.source_entity_id), "?"), "from": r.valid_from.isoformat() if r.valid_from else None, "to": r.valid_to.isoformat() if r.valid_to else None, "level": r.evidence_level.value}
               for r in rels if r.relationship_type == "RESOLVES_TO"]
    infra = {"tlds": sorted({d.key.rsplit(".", 1)[-1] for d in domains}), "name_tokens": sorted(name_tokens), "providers_non_generic": sorted({p["provider"] for p in providers if not p["multi_tenant"]}),
             "providers_generic_excluded": sorted({p["provider"] for p in providers if p["multi_tenant"]}), "observation_windows": windows}
    return {"version": FINGERPRINT_VERSION, "case_id": case.id, "dimensions": {"page_structure": page, "payment_instruction_pattern": pay, "financial_choreography": chore,
                                                                               "message_template": msg, "infrastructure_timeline": infra}, "identifiers_excluded": True}


def compare(fa: dict, fb: dict) -> dict:
    da, dbb = fa["dimensions"], fb["dimensions"]
    out: dict[str, dict] = {}
    s1 = _jaccard(set(da["page_structure"]["tag_shingles"]), set(dbb["page_structure"]["tag_shingles"]))
    s2 = _jaccard(set(da["page_structure"]["url_path_tokens"]), set(dbb["page_structure"]["url_path_tokens"]))
    sc = s1 if s1 is not None else s2
    out["page_structure"] = {"score": sc, "label": _label(sc), "basis": "tag-sequence shingles of supplied HTML captures" if s1 is not None else "URL path tokens only (no HTML capture supplied)",
                             "shared": sorted(set(da["page_structure"]["url_path_tokens"]) & set(dbb["page_structure"]["url_path_tokens"]))[:10]}
    pa, pb = da["payment_instruction_pattern"], dbb["payment_instruction_pattern"]
    parts = []
    if pa["instruction_param_sets"] and pb["instruction_param_sets"]:
        parts.append(_jaccard({tuple(x) for x in pa["instruction_param_sets"]}, {tuple(x) for x in pb["instruction_param_sets"]}) or 0.0)
    nw = _jaccard(set(pa["note_words"]), set(pb["note_words"]))
    if nw is not None:
        parts.append(nw)
    ab = _jaccard(set(pa["amount_buckets"]), set(pb["amount_buckets"]))
    if ab is not None:
        parts.append(ab * 0.5)
    sc = sum(parts) / len(parts) if parts else None
    out["payment_instruction_pattern"] = {"score": sc, "label": _label(sc), "basis": "instruction parameter sets, note template words, amount banding (weak); VPA handles are generic and excluded",
                                          "generic_excluded": sorted(set(pa["vpa_handles"]) & set(pb["vpa_handles"]))}
    ca, cb = da["financial_choreography"], dbb["financial_choreography"]
    parts = []
    hc = _jaccard({k for k, _ in ca["hop_counts"]}, {k for k, _ in cb["hop_counts"]})
    if hc is not None:
        parts.append(hc)
    hb = _jaccard({k for k, _ in ca["holding_buckets"]}, {k for k, _ in cb["holding_buckets"]})
    if hb is not None:
        parts.append(hb)
    parts.append(_jaccard(set(ca["flags"]) or {"none"}, set(cb["flags"]) or {"none"}) or 0.0)
    parts.append(1.0 if (ca["fan_in_max"] >= 2) == (cb["fan_in_max"] >= 2) and (ca["fan_out_max"] >= 2) == (cb["fan_out_max"] >= 2) else 0.0)
    ex = _jaccard(set(ca["exit_channels"]), set(cb["exit_channels"]))
    if ex is not None:
        parts.append(ex)
    sc = sum(parts) / len(parts) if parts else None
    out["financial_choreography"] = {"score": sc, "label": _label(sc), "basis": "hop depth, holding-time buckets, split/merge flags, fan-in/fan-out shape, exit channels",
                                     "caution": "Many unrelated frauds share a 3-hop UPI→IMPS→cash shape; choreography alone is weak."}
    mt = _jaccard(set(da["message_template"]["trigrams"]), set(dbb["message_template"]["trigrams"]))
    out["message_template"] = {"score": mt, "label": _label(mt), "basis": "word trigrams of complaint narratives with identifiers removed", "shared_count": len(set(da["message_template"]["trigrams"]) & set(dbb["message_template"]["trigrams"]))}
    ia, ib = da["infrastructure_timeline"], dbb["infrastructure_timeline"]
    parts = []
    nt = _jaccard(set(ia["name_tokens"]), set(ib["name_tokens"]))
    if nt is not None:
        parts.append(nt)
    pv = _jaccard(set(ia["providers_non_generic"]), set(ib["providers_non_generic"]))
    if pv is not None:
        parts.append(pv)
    sc = sum(parts) / len(parts) if parts else None
    out["infrastructure_timeline"] = {"score": sc, "label": _label(sc), "basis": "domain naming tokens and non-generic providers; shared CDN/multi-tenant hosting is excluded",
                                      "generic_excluded": sorted(set(ia["providers_generic_excluded"]) & set(ib["providers_generic_excluded"])), "shared_name_tokens": sorted(set(ia["name_tokens"]) & set(ib["name_tokens"]))[:10]}
    scored = {k: v["score"] for k, v in out.items() if v["score"] is not None}
    agg = sum(WEIGHTS[k] * s for k, s in scored.items()) / sum(WEIGHTS[k] for k in scored) if scored else None
    strong_dims = [k for k, s in scored.items() if s >= 0.6]
    if agg is None or len(scored) < 2:
        status = "INSUFFICIENT_EVIDENCE"
    elif agg >= 0.55 and len(strong_dims) >= 2:
        status = "CANDIDATE_PATTERN_SIMILARITY_HIGH"
    elif agg >= 0.42:
        status = "CANDIDATE_PATTERN_SIMILARITY_MEDIUM"
    else:
        status = "LOW_PATTERN_SIMILARITY"
    return {"dimension_results": out, "aggregate_label": _label(agg), "aggregate_score_not_probability": round(agg, 3) if agg is not None else None, "relationship_status": status,
            "weights": WEIGHTS, "dimensions_scored": sorted(scored), "strong_dimensions": strong_dims}


def rotation(fa: dict, fb: dict, ids_a: dict, ids_b: dict) -> dict:
    changed = {k: {"a": sorted(ids_a.get(k, [])), "b": sorted(ids_b.get(k, []))} for k in ("domains", "vpas", "accounts") if set(ids_a.get(k, [])) != set(ids_b.get(k, []))}
    same = {k: sorted(set(ids_a.get(k, [])) & set(ids_b.get(k, []))) for k in ("domains", "vpas", "accounts")}
    wa = [w for w in fa["dimensions"]["infrastructure_timeline"]["observation_windows"] if w["from"]]
    wb = [w for w in fb["dimensions"]["infrastructure_timeline"]["observation_windows"] if w["from"]]
    order = None
    if wa and wb:
        order = "a_before_b" if min(w["from"] for w in wa) <= min(w["from"] for w in wb) else "b_before_a"
    return {"changed_identifiers": changed, "shared_identifiers": {k: v for k, v in same.items() if v}, "time_order_of_observations": order,
            "rotation_candidate": bool(changed) and not any(same.values()),
            "note": "Rotation is reported only as a candidate when structural similarity is at least medium and no identifier is shared; time order comes from supplied observations."}


def compare_cases(db: Session, user: User, case_ids: list[str]) -> dict:
    cases = authorised_cases(db, user, case_ids)
    fps = {c.id: fingerprint(db, c) for c in cases}
    ids = {}
    for c in cases:
        ents = db.execute(select(Entity).where(Entity.case_id == c.id)).scalars().all()
        ids[c.id] = {"domains": [e.key for e in ents if e.entity_type == "domain"], "vpas": [e.key for e in ents if e.entity_type == "vpa"], "accounts": [e.key for e in ents if e.entity_type == "account"]}
    pairs = []
    for i in range(len(cases)):
        for j in range(i + 1, len(cases)):
            a, b = cases[i], cases[j]
            cmp = compare(fps[a.id], fps[b.id])
            rot = rotation(fps[a.id], fps[b.id], ids[a.id], ids[b.id])
            if rot["rotation_candidate"] and cmp["relationship_status"] in {"LOW_PATTERN_SIMILARITY", "INSUFFICIENT_EVIDENCE"}:
                rot["rotation_candidate"] = False
            pairs.append({"case_a": a.id, "case_b": b.id, "titles": [a.title, b.title], **cmp, "identifier_rotation": rot,
                          "alternative_explanations": ["Common third-party website template", "Common payment software / UPI collect pattern", "Common scam script circulated among unrelated groups",
                                                       "Shared commercial hosting or CDN (excluded from scoring)", "Coincidental timing"],
                          "limitations": ["Pattern similarity does not establish common ownership, common operator or a criminal organisation.", "Weights are versioned and unvalidated against real cases; labels are qualitative."],
                          "human_review_required": True})
    pairs.sort(key=lambda p: -(p["aggregate_score_not_probability"] or 0))
    findings = [finding("campaign_pair", f"{p['titles'][0]} ↔ {p['titles'][1]}: {p['relationship_status']}", evidence_class="candidate" if "CANDIDATE" in p["relationship_status"] else "derived",
                        case_ids=[p["case_a"], p["case_b"]]) for p in pairs]
    return result(None, "campaign_evolution", FINGERPRINT_VERSION, findings=findings, limitations=["No identity merge; no cross-case operator attribution.", "Generic templates, CDNs and popular payment handles are excluded or down-weighted."],
                  fingerprints={k: {"version": v["version"], "dimension_summary": {d: {kk: (len(vv) if isinstance(vv, (list, dict)) else vv) for kk, vv in dims.items()} for d, dims in v["dimensions"].items()}} for k, v in fps.items()},
                  pairs=pairs, dimensions=DIMENSIONS, cases=[{"id": c.id, "title": c.title, "synthetic": c.is_synthetic} for c in cases])
