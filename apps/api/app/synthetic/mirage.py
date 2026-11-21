"""Operation Desert Mirage and the next-wave scenario families (identifier rotation, commingled funds, benign look-alike,
compromised account). Extends the existing generator/bundle; everything is fictional and watermarked. Ground truth gains
scenario-specific sections (attribution, missing periods, rotation, control hypotheses, decoys) that stay sealed.
"""
from __future__ import annotations

import io
import json
from datetime import timedelta

from app.synthetic.generator import Account, Generator, Truth, Tx

MIRAGE_SCENARIOS = ["desert_mirage", "identifier_rotation_campaign", "commingled_funds", "benign_lookalike", "compromised_account"]
DISTRICTS = ["Jaipur", "Jodhpur", "Udaipur", "Kota", "Ajmer", "Bikaner"]
WATERMARK_SHORT = "SYNTHETIC DATA - FICTIONAL - PS05 DEMO"


def upi_uri(acct: Account, amount_minor: int, ref: str, note: str) -> str:
    from urllib.parse import quote
    return f"upi://pay?pa={acct.vpa}&pn={quote(acct.holder)}&am={amount_minor / 100:.2f}&cu=INR&tn={quote(note)}&tr={ref}"


def qr_png(payload: str) -> bytes | None:
    try:
        import qrcode
    except Exception:  # pragma: no cover
        return None
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def shape_truth(gen: Generator, truth: Truth) -> Truth:
    """Scenario-specific adjustments to the generated truth (called right after build_truth)."""
    sc = gen.scenario_type
    victims = [a for a in truth.accounts if a.role == "victim"]
    l1 = [a for a in truth.accounts if a.role == "mule_l1"]
    unrelated = [a for a in truth.accounts if a.role == "unrelated"]
    if sc in {"desert_mirage", "commingled_funds"} and l1:
        m1 = l1[0]
        # commingling: a salary-like credit lands in the collection account shortly before the first onward transfer
        first_onward = min((t for t in truth.transactions if t.src is m1 and t.hop == 2), key=lambda t: t.when, default=None)
        if first_onward:
            employer = gen._acct("unrelated", "Fictional Employer Pvt Ltd")  # pays only salary; never receives victim money, so no chain passes through it
            truth.accounts.append(employer)
            r = gen._ref()
            truth.transactions.append(Tx(r, first_onward.when - timedelta(hours=3), employer, m1, 45_000_00 if sc == "commingled_funds" else 18_000_00, "NEFT", f"NEFT/{r}/SALARY MARCH", 0, -1))
            truth.chaos.append({"kind": "commingled_credit", "account": m1.acct_no, "ref": r})
            if sc == "commingled_funds":
                # a payment out of the collection account that is reversed the same day: must appear as gross vs net, never netted silently
                supplier = gen._acct("unrelated", "Fictional Supplies Traders")
                truth.accounts.append(supplier)
                r1, r2 = gen._ref(), gen._ref()
                truth.transactions.append(Tx(r1, first_onward.when - timedelta(hours=2), m1, supplier, 7_000_00, "IMPS", f"IMPS/{r1}/ADVANCE", 0, -1))
                truth.transactions.append(Tx(r2, first_onward.when - timedelta(hours=1), supplier, m1, 7_000_00, "IMPS", f"IMPS/{r2}/REV {r1} REVERSAL", 0, -1))
                truth.chaos.append({"kind": "reversal_pair", "account": m1.acct_no, "debit_ref": r1, "credit_ref": r2, "amount_minor": 7_000_00})
        # simulated allocation: the operator forwards victim funds in arrival order (sealed; used only to score bound coverage)
        alloc = []
        pool = []  # (victim_acct, remaining)
        for t in sorted(truth.transactions, key=lambda x: x.when):
            if t.dst is m1 and t.hop == 1:
                pool.append([t.src.acct_no, t.amount_minor])
            elif t.src is m1 and t.hop >= 2:
                need, parts = t.amount_minor, {}
                for slot in pool:
                    take = min(slot[1], need)
                    if take:
                        parts[slot[0]] = parts.get(slot[0], 0) + take
                        slot[1] -= take
                        need -= take
                    if need == 0:
                        break
                alloc.append({"ref": t.ref, "from": m1.acct_no, "to": t.dst.acct_no, "amount_minor": t.amount_minor, "victim_origin_by_victim": parts, "other_minor": need})
        truth.params["simulated_allocation"] = alloc
    if sc == "desert_mirage":
        truth.params["districts"] = {v.acct_no: DISTRICTS[i % len(DISTRICTS)] for i, v in enumerate(victims)}
        # identifier rotation: later victims pay a second collection account; second domain appears later
        camp = truth.params["campaign_domain"]
        camp2 = camp.replace(".test", "-renewal.test")
        rot_from = gen.t0 + timedelta(days=10)
        truth.domains.append({"domain": camp2, "role": "campaign_rotated", "ip": gen._ip(), "provider": "DemoHost VPS", "asn": 64501, "is_cdn": False,
                              "valid_from": rot_from.isoformat(), "valid_to": (gen.t0 + timedelta(days=40)).isoformat(), "current_only": True})
        truth.params["rotation"] = {"domains": [camp, camp2], "rotated_at": rot_from.isoformat(), "vpas": sorted({a.vpa for a in l1})}
        # account-control ambiguity: the collection account's registered holder vs an alleged operator named in messages
        if l1:
            truth.params["control"] = {"account": l1[0].acct_no, "registered_holder": l1[0].holder, "alleged_operator": gen._name(), "basis": "synthetic message export; hypothesis only"}
        # missing statement month for the intermediary (rows later removed from the public bundle; balances stay consistent so a gap shows)
        if l1:
            truth.params["missing_period"] = {"account": l1[0].acct_no, "from": (gen.t0 + timedelta(days=12)).isoformat(), "to": (gen.t0 + timedelta(days=40)).isoformat()}
            # activity inside and after the window: inside rows are pruned from the public statement, so the running balance jumps across the gap
            for d, kind in ((20, "in"), (31, "in"), (44, "after"), (47, "after")):
                r = gen._ref()
                other = unrelated[d % len(unrelated)] if unrelated else l1[0]
                if d % 2 == 0:
                    truth.transactions.append(Tx(r, gen.t0 + timedelta(days=d, hours=10), other, l1[0], gen.rng.randint(900, 4000) * 100, "UPI", f"UPI/{r}/{l1[0].vpa}/transfer", 0, -1))
                else:
                    truth.transactions.append(Tx(r, gen.t0 + timedelta(days=d, hours=15), l1[0], other, gen.rng.randint(500, 2500) * 100, "UPI", f"UPI/{r}/{other.vpa}/payment", 0, -1))
            truth.transactions.sort(key=lambda t: t.when)
        truth.params["benign_shared_provider"] = "SampleCloud CDN"
        truth.params["ocr_corrupted_row"] = {"victim": victims[-1].acct_no if victims else None}
        truth.params["no_balance_statement"] = victims[-1].acct_no if victims else None
        # stale observation always present in mirage
        truth.domains.append({"domain": camp, "role": "campaign_stale", "ip": gen._ip(), "provider": "DemoHost VPS", "asn": 64501, "is_cdn": False,
                              "valid_from": (gen.t0 - timedelta(days=300)).isoformat(), "valid_to": (gen.t0 - timedelta(days=200)).isoformat()})
    if sc == "identifier_rotation_campaign":
        camp = truth.params["campaign_domain"]
        camp2 = camp.rsplit(".", 1)[0] + "-v2.test"
        truth.domains.append({"domain": camp2, "role": "campaign_rotated", "ip": gen._ip(), "provider": "DemoHost VPS", "asn": 64501, "is_cdn": False,
                              "valid_from": (gen.t0 + timedelta(days=8)).isoformat(), "valid_to": (gen.t0 + timedelta(days=30)).isoformat()})
        truth.params["rotation"] = {"domains": [camp, camp2], "vpas": sorted({a.vpa for a in l1})}
    if sc == "compromised_account" and l1:
        truth.params["control"] = {"account": l1[0].acct_no, "registered_holder": l1[0].holder, "holder_reports_compromise": True, "basis": "synthetic complaint by the holder; hypothesis only"}
    if sc == "benign_lookalike":
        # no fraud at all: drop the scam chain, keep a busy legitimate shop with many small credits and supplier payouts on shared hosting
        shop = truth.accounts[len(victims)] if len(truth.accounts) > len(victims) else truth.accounts[0]
        shop.role = "unrelated"
        for a in truth.accounts:
            if a.role in {"victim", "mule_l1", "mule_l2", "exit"}:
                a.role = "unrelated"
        truth.transactions = [t for t in truth.transactions if t.hop == 0]
        for i in range(14):
            r = gen._ref()
            payer = gen.rng.choice([a for a in truth.accounts if a is not shop])
            truth.transactions.append(Tx(r, gen.t0 + timedelta(days=gen.rng.randint(0, 20), hours=gen.rng.randint(8, 20)), payer, shop, gen.rng.randint(120, 1800) * 100, "UPI", f"UPI/{r}/{shop.vpa}/shop purchase", 0, -1))
        for i in range(3):
            r = gen._ref()
            sup = gen.rng.choice([a for a in truth.accounts if a is not shop])
            truth.transactions.append(Tx(r, gen.t0 + timedelta(days=7 * (i + 1)), shop, sup, gen.rng.randint(3000, 9000) * 100, "NEFT", f"NEFT/{r}/SUPPLIER", 0, -1))
        truth.transactions.sort(key=lambda t: t.when)
        truth.paths, truth.true_edges, truth.mule_accounts = [], [], []
        truth.params["benign"] = True
        truth.params["campaign_vpa"] = shop.vpa
        truth.params["statement_focus"] = shop.acct_no
        truth.false_edges = [{"type": "COMMON_OPERATOR", "src": truth.params["campaign_domain"], "dst": d["domain"], "reason": "benign_lookalike_on_shared_cdn"} for d in truth.domains if d["role"] == "decoy"]
        truth.false_edges.append({"type": "MULE_PATTERN", "src": shop.acct_no, "reason": "legitimate high-volume shop account"})
    return truth


def extra_files(gen: Generator, truth: Truth, files: dict[str, bytes]) -> None:
    """Scenario-specific public artefacts appended to the bundle."""
    sc = gen.scenario_type
    victims = [a for a in truth.accounts if a.role == "victim"]
    hop1 = sorted([t for t in truth.transactions if t.hop == 1], key=lambda t: t.when)
    if sc in {"desert_mirage", "identifier_rotation_campaign", "commingled_funds"} and hop1:
        # QR image with the exact payment instruction for the first victim's payment
        first = hop1[0]
        payload = upi_uri(first.dst, first.amount_minor, first.ref, "Application Fee")
        png = qr_png(payload)
        if png:
            files["payment_qr_victim1.png"] = png
        truth.params["payment_instructions"] = [{"file": "payment_qr_victim1.png", "payload": payload, "matches_ref": first.ref, "amount_minor": first.amount_minor}]
        if len(hop1) > 1:
            last = hop1[-1]
            payload2 = upi_uri(last.dst, last.amount_minor, last.ref, "Renewal Fee")
            files["payment_link_victim_last.txt"] = (WATERMARK_SHORT + "\nPayment link copied from the renewal page (synthetic):\n" + payload2 + "\n").encode("utf-8")
            truth.params["payment_instructions"].append({"file": "payment_link_victim_last.txt", "payload": payload2, "matches_ref": last.ref, "amount_minor": last.amount_minor})
    if sc == "desert_mirage":
        ctl = truth.params.get("control", {})
        msgs = [WATERMARK_SHORT, "SYNTHETIC MESSAGE EXPORT (fictional) - supplied by complainant, lawfully obtained in the scenario", "",
                f"[{(gen.t0 - timedelta(days=9)).strftime('%d-%m-%Y')} 18:02] Recruiter: Part-time job, Rs 8000/month. Just share your bank account for company payments. No work needed.",
                f"[{(gen.t0 - timedelta(days=8)).strftime('%d-%m-%Y')} 09:40] {ctl.get('registered_holder', 'Holder')}: Which account? I only have one, I need it for my salary.",
                f"[{(gen.t0 - timedelta(days=8)).strftime('%d-%m-%Y')} 09:41] Recruiter: Give passbook, ATM card and the SIM used for the account. {ctl.get('alleged_operator', 'Agent')} will collect. You get 2000 advance.",
                f"[{(gen.t0 - timedelta(days=2)).strftime('%d-%m-%Y')} 21:15] {ctl.get('registered_holder', 'Holder')}: My phone shows OTP messages I did not request. What is happening?",
                "", "NOTE: This export supports several hypotheses (recruited/deceived holder; handover of possession; possible compromise). It does not establish knowledge or intent."]
        files["messages_export_SYNTHETIC.txt"] = ("\n".join(msgs) + "\n").encode("utf-8")
        # recruitment advert artefact
        files["job_advert_capture_SYNTHETIC.txt"] = (WATERMARK_SHORT + "\nWORK FROM HOME - EARN 8000 MONTHLY - SHARE BANK ACCOUNT DETAILS - NO INTERVIEW - VISA ASSISTANCE AVAILABLE\nContact on messaging app. (synthetic recruitment advert text)\n").encode("utf-8")
        # simulated preservation response
        files["preservation_response_SIMULATED.txt"] = (WATERMARK_SHORT + "\nSIMULATED PROVIDER RESPONSE (fictional) - DemoHost VPS abuse desk\n"
                                                       f"Re: preservation request for {truth.params['rotation']['domains'][1]}\nStatus: logs preserved for 90 days from request date (SIMULATED). No customer data disclosed without legal process.\n").encode("utf-8")
        # complaints for the other victims (districts)
        for i, v in enumerate(victims[1:], start=2):
            tx = next((t for t in hop1 if t.src is v), None)
            if tx is None:
                continue
            district = truth.params["districts"].get(v.acct_no, "Jaipur")
            dom = truth.params["rotation"]["domains"][1] if i == len(victims) else truth.params["campaign_domain"]
            txt = (WATERMARK_SHORT + f"\nComplaint Statement (Synthetic) - District {district}\nComplainant: {v.holder} (fictional)  Account: {v.acct_no} ({v.bank})\n"
                   f"Date of complaint: {tx.when.strftime('%d-%m-%Y')}\n\nI saw a job and renewal offer on https://{dom}/apply and paid Rs {tx.amount_minor / 100:.2f} by UPI to {tx.dst.vpa}. UTR {tx.ref}.\n"
                   "The contact number stopped responding. I request that the amount be traced.\n-- synthetic test data; no real person or event --\n")
            files[f"complaint_{district.lower()}_{i}.txt"] = txt.encode("utf-8")
        # website captures (two domains, generic template)
        for d in truth.params["rotation"]["domains"]:
            files[f"capture_{d.replace('.', '_')}_SYNTHETIC.txt"] = (WATERMARK_SHORT + f"\nSupplied page capture (text) of https://{d}/apply\nTitle: Verified Earning Program - Apply Now\nForm: name, phone, UPI id, 'Pay registration fee'\nFooter: Powered by generic template\n").encode("utf-8")
    if sc == "compromised_account":
        ctl = truth.params.get("control", {})
        files["holder_complaint_SYNTHETIC.txt"] = (WATERMARK_SHORT + f"\nComplaint by account holder {ctl.get('registered_holder')} (fictional): my account {ctl.get('account')} was operated without my knowledge after my phone was stolen on "
                                                   f"{(gen.t0 - timedelta(days=3)).strftime('%d-%m-%Y')}. I did not authorise these transfers.\n").encode("utf-8")


def hidden_refs(truth: Truth, acct: Account) -> set[str]:
    """References of the intermediary's transactions inside the sealed missing period (rows absent from the public statement)."""
    mp = truth.params.get("missing_period")
    if not mp or mp["account"] != acct.acct_no:
        return set()
    from datetime import datetime
    lo, hi = datetime.fromisoformat(mp["from"]), datetime.fromisoformat(mp["to"])
    return {t.ref for t in truth.transactions if (t.src is acct or t.dst is acct) and lo <= t.when <= hi}


def prune_missing_period(gen: Generator, truth: Truth, acct: Account, rows: list[list[str]], date_col: int = 0) -> list[list[str]]:
    """Remove the intermediary's rows inside the sealed missing period (balances already encode the removed activity, so a
    discontinuity remains visible). Only for desert_mirage / incomplete_evidence."""
    mp = truth.params.get("missing_period")
    if not mp or mp["account"] != acct.acct_no:
        return rows
    from datetime import datetime
    lo, hi = datetime.fromisoformat(mp["from"]), datetime.fromisoformat(mp["to"])
    kept = []
    removed = 0
    txs = sorted([t for t in truth.transactions if t.src is acct or t.dst is acct], key=lambda t: t.when)
    for row, t in zip(rows, txs):
        if lo <= t.when <= hi:
            removed += 1
            continue
        kept.append(row)
    if removed:
        truth.chaos.append({"kind": "missing_statement_period", "account": acct.acct_no, "rows_removed": removed, "from": mp["from"], "to": mp["to"]})
    return kept


def manifest_extra(gen: Generator, truth: Truth) -> dict:
    return {"scenario_family": gen.scenario_type, "note": "Desert Mirage pack: multiple complaints, QR/UPI instructions, rotated domains, commingled intermediary with a missing statement period, shared-CDN decoy, stale DNS, OCR-corrupted identifier, message export, simulated hold and preservation response. Ground truth sealed."
            if gen.scenario_type == "desert_mirage" else None, "json": json.dumps({"synthetic": True})}
