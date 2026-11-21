"""Turn Truth into public artefacts (statement CSV/XLSX, complaint PDF, technical observations JSON, optional PNG),
then corrupt them according to the difficulty profile. Chaos events are recorded in the truth for benchmarking."""
from __future__ import annotations

import csv
import io
import json
from datetime import timedelta, timezone

from app.synthetic.generator import Account, Generator, Truth

WATERMARK = "SYNTHETIC DATA - FICTIONAL - RAJASTHAN POLICE HACKATHON 2026 PS05 DEMO - NOT A REAL BANK RECORD"

_OCR_SUBS = {"0": "O", "1": "I", "5": "S", "8": "B"}

HEADER_SETS = [
    # set 3 (index 3) has no balance column: used for the "no balance" statement in incomplete-evidence scenarios
    ["Txn Date", "Narration", "Ref No", "Debit", "Credit", "Balance", "Account", "Counterparty", "Beneficiary Name"],
    ["Date", "Description", "UTR", "Withdrawal Amt", "Deposit Amt", "Closing Balance", "A/C No", "Beneficiary Account", "Payee Name"],
    ["Transaction Date", "Particulars", "Reference", "Amount", "Type", "Running Balance", "Account Number", "Counter Party", "Name"],
    ["Date", "Narration", "UTR", "Debit", "Credit", "Account", "Counterparty", "Beneficiary Name"],
]


def _fmt_date(gen: Generator, dt, ambiguous: bool) -> str:
    ist = dt.astimezone(timezone.utc)  # we keep UTC for simplicity of generated data; statements label IST
    from datetime import timedelta
    ist = ist + timedelta(hours=5, minutes=30)
    if ambiguous:
        return ist.strftime("%d/%m/%y %H:%M")
    return ist.strftime("%d-%m-%Y %H:%M:%S")


def _ocr(gen: Generator, s: str) -> str:
    chars = list(s)
    for i, ch in enumerate(chars):
        if ch in _OCR_SUBS and gen.rng.random() < 0.3:
            chars[i] = _OCR_SUBS[ch]
    return "".join(chars)


def statement_rows(gen: Generator, truth: Truth, acct: Account, header_set: int) -> tuple[list[str], list[list[str]]]:
    chaos = gen.chaos_level()
    headers = HEADER_SETS[header_set]
    rows: list[list[str]] = []
    bal = acct.opening_balance_minor
    txs = [t for t in truth.transactions if t.src is acct or t.dst is acct]
    from app.synthetic import mirage
    hidden = mirage.hidden_refs(truth, acct)
    for t in txs:
        is_debit = t.src is acct
        other = t.dst if is_debit else t.src
        amt = t.amount_minor
        bal = bal - amt if is_debit else bal + amt
        if t.ref in hidden:
            continue  # missing statement period: the balance keeps moving, the row is absent from the public file
        ambiguous = gen.rng.random() < chaos["ambig"]
        date_s = _fmt_date(gen, t.when, ambiguous)
        if ambiguous:
            truth.chaos.append({"kind": "ambiguous_date", "ref": t.ref, "account": acct.acct_no})
        cp_ref = other.vpa if t.channel == "UPI" else other.acct_no
        cp_name = other.holder
        if gen.rng.random() < chaos["missing"]:
            cp_name = ""
            truth.chaos.append({"kind": "missing_field", "field": "counterparty_name", "ref": t.ref})
        if chaos["ocr"] and gen.rng.random() < chaos["ocr"]:
            cp_ref = _ocr(gen, cp_ref)
            truth.chaos.append({"kind": "ocr_substitution", "ref": t.ref, "field": "counterparty"})
        if chaos["similar"] and other.role.startswith("mule") and gen.rng.random() < 0.3:
            cp_name = cp_name.replace("a", "aa", 1) if "a" in cp_name else cp_name + " ."
            truth.chaos.append({"kind": "similar_name", "ref": t.ref})
        amt_s = f"{amt / 100:.2f}"
        bal_s = f"{bal / 100:.2f}"
        if header_set == 3:
            row = [date_s, t.narration, t.ref, amt_s if is_debit else "", "" if is_debit else amt_s, acct.acct_no, cp_ref, cp_name]
        elif header_set in (0, 1):
            row = [date_s, t.narration, t.ref, amt_s if is_debit else "", "" if is_debit else amt_s, bal_s, acct.acct_no, cp_ref, cp_name]
        else:
            row = [date_s, t.narration, t.ref, amt_s, "DR" if is_debit else "CR", bal_s, acct.acct_no, cp_ref, cp_name]
        rows.append(row)
        if gen.rng.random() < chaos["dup"]:
            rows.append(list(row))
            truth.chaos.append({"kind": "duplicate_row", "ref": t.ref, "account": acct.acct_no})
    if header_set != 3 and chaos["balance"] and rows and gen.rng.random() < 0.5:
        # perturb one balance to create a reconciliation mismatch
        i = gen.rng.randrange(len(rows))
        try:
            rows[i][5] = f"{float(rows[i][5]) + 10.00:.2f}"
            truth.chaos.append({"kind": "balance_mismatch", "account": acct.acct_no, "row": i + 2})
        except ValueError:
            pass
    return headers, rows


def statement_csv(headers: list[str], rows: list[list[str]], acct: Account) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([WATERMARK])
    w.writerow([f"Statement of Account {acct.acct_no} ({acct.bank}) - holder {acct.holder} - FICTIONAL"])
    w.writerow(headers)
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def statement_xlsx(headers: list[str], rows: list[list[str]], acct: Account) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    from datetime import datetime as _dt
    wb.properties.created = _dt(2026, 1, 1)
    wb.properties.modified = _dt(2026, 1, 1)
    wb.properties.creator = "PS05-X synthetic case factory"
    ws = wb.active
    ws.title = "Statement"
    ws.append([WATERMARK])
    ws.append([f"Statement of Account {acct.acct_no} ({acct.bank}) - FICTIONAL"])
    ws.append(headers)
    for r in rows:
        ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    # pin zip entry timestamps so the same seed yields byte-identical files
    import zipfile
    src = zipfile.ZipFile(io.BytesIO(out.getvalue()))
    dst_buf = io.BytesIO()
    with zipfile.ZipFile(dst_buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            zi = zipfile.ZipInfo(info.filename, date_time=(2026, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            payload = src.read(info.filename)
            if info.filename == "docProps/core.xml":
                # openpyxl stamps save time here regardless of wb.properties; pin it
                import re
                payload = re.sub(rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*(</dcterms:(?:created|modified)>)", rb"\g<1>2026-01-01T00:00:00Z\g<2>", payload)
            dst.writestr(zi, payload)
    return dst_buf.getvalue()


def complaint_pdf(gen: Generator, truth: Truth) -> bytes:  # noqa: C901
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas
    from app.synthetic.generator import SCENARIO_TEXT

    victims = [a for a in truth.accounts if a.role == "victim"]
    v = victims[0]
    first_tx = next(t for t in truth.transactions if t.src is v and t.hop == 1)
    district = (truth.params.get("districts") or {}).get(v.acct_no)
    mule = first_tx.dst
    camp = truth.params["campaign_domain"]
    story, _ = SCENARIO_TEXT[gen.scenario_type]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1)
    c.setAuthor("PS05-X synthetic case factory")
    c.setTitle("Synthetic complaint")
    w, h = A4
    c.setFont("Helvetica-Bold", 9)
    c.setFillColorRGB(0.6, 0.1, 0.1)
    c.drawString(1.5 * cm, h - 1.2 * cm, WATERMARK)
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, h - 2.5 * cm, "Complaint Statement (Synthetic Demonstration)")
    c.setFont("Helvetica", 10.5)
    lines = [
        f"Complainant: {v.holder} (fictional)      Account: {v.acct_no} ({v.bank})" + (f"      District: {district}" if district else ""),
        f"Date of complaint: {(first_tx.when).strftime('%d-%m-%Y')}",
        "",
        f"I {story}. The website shown to me was https://{camp}/login and I was asked to",
        f"make a payment of Rs {first_tx.amount_minor / 100:.2f} through UPI to {mule.vpa}.",
        f"The transaction reference was UTR {first_tx.ref}. Afterwards the number {gen.rng.choice(['9', '8', '7'])}{''.join(str(gen.rng.randint(0, 9)) for _ in range(9))} stopped responding.",
        "",
        f"I later noticed the account name shown was {mule.holder}. I request that the amount be traced.",
        "",
        "Signature: (synthetic)   -- This document is generated test data and describes no real person or event. --",
    ]
    y = h - 3.6 * cm
    for ln in lines:
        c.drawString(2 * cm, y, ln)
        y -= 0.6 * cm
    c.showPage()
    c.save()
    return buf.getvalue()


def technical_observations_json(gen: Generator, truth: Truth) -> bytes:
    from datetime import datetime, timedelta
    obs = []
    for d in truth.domains:
        vf = datetime.fromisoformat(d["valid_from"])
        observed = vf + timedelta(days=gen.rng.randint(1, 10))
        obs.append({"type": "dns", "domain": d["domain"], "ip": d["ip"], "ttl": 300 if d["is_cdn"] else 3600,
                    "observed_at": observed.isoformat(), "valid_from": d["valid_from"], "valid_to": d["valid_to"],
                    "resolver": "synthetic-resolver.test", "source": "synthetic_passive_dns_fixture"})
        obs.append({"type": "cdn" if d["is_cdn"] else "hosting", "domain": d["domain"], "ip": d["ip"], "provider": d["provider"], "asn": d["asn"],
                    "observed_at": observed.isoformat(), "multi_tenant": d["is_cdn"], "source": "synthetic_hosting_fixture"})
    camp = truth.params["campaign_domain"]
    obs.append({"type": "url", "url": f"https://{camp}/login", "observed_at": truth.params["t0"], "source": "complaint_screenshot_fixture"})
    # rotated domains observed only by a current lookup (no historical observation for the earlier period)
    for d in truth.domains:
        if d.get("current_only"):
            obs[:] = [o for o in obs if o.get("domain") != d["domain"]]
            obs.append({"type": "dns", "domain": d["domain"], "ip": d["ip"], "ttl": 300, "observed_at": (gen.t0 + timedelta(days=45)).isoformat(), "resolver": "synthetic-resolver.test",
                        "source": "current_lookup_fixture", "note": "current lookup only; historical mapping unknown"})

    obs.append({"type": "rdap", "domain": camp, "registrar": "Example Registrar (fictional)", "created": (gen.t0 - timedelta(days=7)).isoformat(),
                "observed_at": (gen.t0 + timedelta(days=3)).isoformat(), "source": "synthetic_rdap_fixture"})
    if gen.base_difficulty == "adversarial" or gen.difficulty == "temporal_conflict":
        # conflicting source: claims decoy domain resolves to campaign IP at a time it did not
        decoys = [d for d in truth.domains if d["role"] == "decoy"]
        if decoys:
            obs.append({"type": "dns", "domain": decoys[0]["domain"], "ip": truth.domains[0]["ip"], "observed_at": (gen.t0 - timedelta(days=250)).isoformat(),
                        "source": "unverified_forum_post_fixture", "note": "conflicting / stale observation planted for adversarial testing"})
            truth.chaos.append({"kind": "stale_conflicting_dns", "domain": decoys[0]["domain"]})
    return json.dumps({"_watermark": WATERMARK, "observations": obs}, indent=1).encode("utf-8")


def screenshot_png(gen: Generator, truth: Truth) -> bytes | None:
    try:
        from PIL import Image, ImageDraw
    except Exception:  # pragma: no cover
        return None
    img = Image.new("RGB", (640, 220), (245, 245, 245))
    d = ImageDraw.Draw(img)
    d.text((10, 10), WATERMARK[:70], fill=(150, 20, 20))
    d.text((10, 60), f"https://{truth.params['campaign_domain']}/login", fill=(0, 0, 120))
    d.text((10, 100), f"Pay to: {truth.params['campaign_vpa']}", fill=(0, 0, 0))
    # noise
    for _ in range(400):
        d.point((gen.rng.randint(0, 639), gen.rng.randint(0, 219)), fill=(gen.rng.randint(0, 255),) * 3)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def build_bundle(gen: Generator) -> tuple[dict[str, bytes], Truth, dict]:
    """Return ({filename: bytes}, truth, public_manifest)."""
    truth = gen.build_truth()
    files: dict[str, bytes] = {}
    chaos = gen.chaos_level()
    # statements: victims' and first-layer mules' statements (what an investigator might obtain)
    victims = [a for a in truth.accounts if a.role == "victim"]
    mules_l1 = [a for a in truth.accounts if a.role == "mule_l1"]
    if truth.params.get("statement_focus"):
        mules_l1 = [a for a in truth.accounts if a.acct_no == truth.params["statement_focus"]]
    truth.params["statement_accounts"] = [a.acct_no for a in victims + mules_l1]  # which accounts' statements are in the public bundle
    from app.synthetic import mirage
    for i, acct in enumerate(victims + mules_l1):
        header_set = (i % 3) if chaos["drift"] else 0
        if acct.acct_no == truth.params.get("no_balance_statement") or (gen.difficulty == "incomplete_evidence" and acct.role == "victim" and i == len(victims) - 1):
            header_set = 3
        headers, rows = statement_rows(gen, truth, acct, header_set)
        if mirage.hidden_refs(truth, acct):
            truth.chaos.append({"kind": "missing_statement_period", "account": acct.acct_no, "rows_removed": len(mirage.hidden_refs(truth, acct)), **truth.params["missing_period"]})
        if acct.acct_no == (truth.params.get("ocr_corrupted_row") or {}).get("victim") and rows:
            # planted OCR substitution on the victim's first-hop counterparty (one character) so the bridge sees a near-miss
            for row in rows:
                cp_idx = 7 if header_set != 3 else 6
                local = str(row[cp_idx]).split("@")[0] if "@" in str(row[cp_idx]) else ""
                if local and any(ch in local for ch in "01oa"):
                    subs = {"0": "O", "1": "I", "o": "0", "a": "@"}
                    ch = next(c for c in "01oa" if c in local)
                    row[cp_idx] = row[cp_idx].replace(ch, subs[ch], 1)
                    truth.chaos.append({"kind": "ocr_substitution_planted", "account": acct.acct_no, "field": "counterparty"})
                    break
        if gen.difficulty != "clean" and i % 2 == 1:
            files[f"statement_{acct.acct_no[-4:]}_{acct.role}.xlsx"] = statement_xlsx(headers, rows, acct)
        else:
            files[f"statement_{acct.acct_no[-4:]}_{acct.role}.csv"] = statement_csv(headers, rows, acct)
    if truth.params.get("benign"):
        files["shop_owner_note.txt"] = (WATERMARK + "\nNo complaint: this bundle is a legitimate shop account supplied for comparison (synthetic).\n").encode("utf-8")
    else:
        files["complaint.pdf"] = complaint_pdf(gen, truth)
    files["technical_observations.json"] = technical_observations_json(gen, truth)
    if gen.scenario_type in {"multi_victim_network", "desert_mirage"}:
        # simulated bank hold notice for the first-layer account: partially held, remainder already moved on
        m1 = [a for a in truth.accounts if a.role == "mule_l1"][0]
        inflow = sum(t.amount_minor for t in truth.transactions if t.dst is m1 and t.hop == 1)
        held = (inflow * gen.rng.randint(30, 60) // 100) // 100 * 100
        truth.params["simulated_holds"] = [{"account": m1.acct_no, "held_minor": held, "inflow_minor": inflow, "source": "bank_hold_notice.txt"}]
        notice_lines = [WATERMARK, "SIMULATED BANK HOLD NOTICE (fictional, generated for testing)", f"Bank: {m1.bank}", f"Account: {m1.acct_no}",
                        f"Holder: {m1.holder}", f"Amount placed on hold: Rs {held / 100:.2f}", f"Reference: HOLD-SYN-{gen.seed}",
                        f"Date: {(gen.t0 + timedelta(days=3)).strftime('%d-%m-%Y')}", "Remaining credits were transferred out before the hold request was received."]
        notice = chr(10).join(notice_lines) + chr(10)
        files["bank_hold_notice.txt"] = notice.encode("utf-8")
    png = screenshot_png(gen, truth)
    if png:
        files["screenshot.png"] = png
    mirage.extra_files(gen, truth, files)
    if gen.difficulty == "incomplete_evidence" and not truth.params.get("missing_period"):
        m1 = [a for a in truth.accounts if a.role == "mule_l1"]
        if m1:
            truth.params["missing_period_note"] = "incomplete_evidence: last victim statement has no balance column"
    manifest = {"synthetic": True, "watermark": WATERMARK, "scenario_type": gen.scenario_type, "difficulty": gen.difficulty, "size": gen.size,
                "seed": gen.seed, "scenario_version": truth.params["scenario_version"], "generator_version": truth.params["generator_version"],
                "files": sorted(files), "transactions_generated": len(truth.transactions), "accounts_generated": len(truth.accounts),
                "note": "Ground truth is sealed in the benchmark store and is not available through case APIs.", "scenario_note": mirage.manifest_extra(gen, truth)["note"]}
    files["case_manifest.json"] = json.dumps(manifest, indent=1).encode("utf-8")
    return files, truth, manifest


def truth_to_dict(truth: Truth) -> dict:
    return {"params": truth.params, "mule_accounts": truth.mule_accounts,
            "accounts": [{"acct_no": a.acct_no, "holder": a.holder, "vpa": a.vpa, "role": a.role} for a in truth.accounts],
            "transactions": [{"ref": t.ref, "when": t.when.isoformat(), "src": t.src.acct_no, "dst": t.dst.acct_no, "amount_minor": t.amount_minor,
                              "channel": t.channel, "hop": t.hop, "path_id": t.path_id} for t in truth.transactions],
            "paths": truth.paths, "domains": truth.domains, "true_edges": truth.true_edges, "false_edges": truth.false_edges, "chaos": truth.chaos}
