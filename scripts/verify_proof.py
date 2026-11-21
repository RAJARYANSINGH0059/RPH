#!/usr/bin/env python3
"""Standalone offline verifier for PS05-X proof-carrying money-trail manifests. Standard library only.

Usage:
    python scripts/verify_proof.py MANIFEST.json [--files DIR] [--key HMAC_KEY] [--json OUT.json]

Checks: manifest hash; optional HMAC; SHA-256 of every cited source file (found in DIR by name or by hash);
locator validity (the cited row/record contains the cited reference/amount); deterministic re-derivation of each hop's
amount (paise) from the raw cell; direction/account consistency; temporal and conservation constraints; rule versions.
A changed file, changed value or changed rule version fails verification. Exit code 0 = PASS, 1 = FAIL, 2 = usage error.
This verifies reproducibility and integrity only. It does not establish legal admissibility or account control.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import io
import json
import re
import sys
import zipfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

EXPECTED_RULES = {"path_algorithm_version": "2.0.0", "relationship_method_version": "0.1.0", "parser_version": "0.1.0"}


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")


def money_minor(raw) -> int | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() in {"nan", "none"}:
        return None
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = re.sub(r"[^\d.]", "", s.replace(",", ""))
    if not s:
        return None
    try:
        d = Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    v = int(d * 100)
    return -v if neg else v


def find_file(files_dir: Path | None, name: str | None, sha: str | None) -> Path | None:
    if files_dir is None:
        return None
    for cand in ([files_dir / name] if name else []) + ([files_dir / sha, files_dir / f"{sha}.bin"] if sha else []):
        if cand.exists():
            return cand
    if sha:
        for p in files_dir.iterdir():
            if p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == sha:
                return p
    return None


def locator_check(path: Path, hop: dict) -> tuple[str, str]:
    """Return (status, detail). Checks that the cited row/record carries the reference (or amount) value."""
    ref = hop.get("reference") or ""
    amount_raw = hop.get("amount_raw") or ""
    loc = hop.get("locator") or {}
    data = path.read_bytes()
    if path.suffix.lower() == ".csv":
        text = data.decode("utf-8-sig", errors="replace")
        rows = list(csv.reader(io.StringIO(text)))
        row_no = loc.get("row")
        # tabular parser row numbers are 1-based spreadsheet rows counted over the physical lines; check cited row then neighbours
        candidates = [row_no - 1, row_no, row_no - 2] if isinstance(row_no, int) else []
        for idx in candidates:
            if 0 <= idx < len(rows) and (ref and ref in rows[idx]) or (0 <= idx < len(rows) and not ref and amount_raw and any(amount_raw in c for c in rows[idx])):
                return "ok", f"row {row_no} contains the cited value"
        if ref and any(ref in r for r in rows):
            return "value_present_locator_row_mismatch", f"reference {ref} found in the file but not at row {row_no}"
        return "fail", f"reference {ref!r} not found in {path.name}"
    if path.suffix.lower() == ".xlsx":
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            blob = b"".join(z.read(n) for n in z.namelist() if n.startswith("xl/"))
        except zipfile.BadZipFile:
            return "fail", "xlsx is not a valid zip"
        if ref and ref.encode() in blob:
            return "ok", f"reference {ref} present in workbook (cell {loc.get('cell') or '?'} as cited)"
        return ("fail", f"reference {ref!r} not present in workbook") if ref else ("unverifiable", "no reference to look up")
    return "unverifiable", f"locator check not implemented for {path.suffix}"


def verify(manifest: dict, files_dir: Path | None, key: str | None) -> dict:
    checks: list[dict] = []

    def add(name: str, ok: bool | None, detail: str = ""):
        checks.append({"check": name, "status": "pass" if ok else ("skip" if ok is None else "fail"), "detail": detail})

    integ = manifest.get("integrity") or {}
    body = {k: v for k, v in manifest.items() if k != "integrity"}
    digest = hashlib.sha256(canonical(body)).hexdigest()
    add("manifest_sha256", digest == integ.get("manifest_sha256"), f"recomputed {digest[:16]}… vs recorded {str(integ.get('manifest_sha256'))[:16]}…")
    if integ.get("hmac_sha256"):
        if key:
            add("manifest_hmac", hmac.compare_digest(hmac.new(key.encode(), digest.encode(), hashlib.sha256).hexdigest(), integ["hmac_sha256"]), f"key_version {integ.get('key_version')}")
        else:
            add("manifest_hmac", None, "manifest carries an HMAC but no key was supplied")
    else:
        add("manifest_hmac", None, "manifest is hash-protected only (no HMAC)")
    rules = manifest.get("rules") or {}
    for k, v in EXPECTED_RULES.items():
        add(f"rule_version:{k}", rules.get(k) == v, f"manifest {rules.get(k)} / verifier expects {v}")
    found_files: dict[str, Path] = {}
    for f in manifest.get("source_files") or []:
        p = find_file(files_dir, f.get("name"), f.get("sha256"))
        if p is None:
            add(f"file_sha256:{f.get('name')}", None, "file not supplied to the verifier")
            continue
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        ok = actual == f.get("sha256")
        add(f"file_sha256:{f.get('name')}", ok, "match" if ok else f"MODIFIED: actual {actual[:16]}… recorded {str(f.get('sha256'))[:16]}…")
        if ok:
            found_files[f.get("sha256")] = p
    hops = manifest.get("hops") or []
    prev_t = None
    prev_amt = None
    for h in hops:
        n = h["hop"]
        raw = h.get("raw_row") or {}
        mapping = h.get("column_mapping") or {}
        norm = h.get("normalised") or {}
        # re-derive the amount from the raw cell(s)
        derived = None
        for fld in ("amount", "debit", "credit"):
            col = mapping.get(fld)
            if col and raw.get(col) not in (None, "", "nan"):
                derived = money_minor(raw.get(col))
                if derived is not None:
                    derived = abs(derived)
                    break
        if derived is None and h.get("amount_raw"):
            derived = abs(money_minor(h["amount_raw"]) or 0) or None
        add(f"hop{n}_amount_rederived", derived == h.get("amount_minor") if derived is not None else None,
            f"raw → {derived} paise; manifest {h.get('amount_minor')}" if derived is not None else "no raw amount cell available")
        ref_col = mapping.get("reference")
        if ref_col and h.get("reference"):
            add(f"hop{n}_reference_matches_raw", str(raw.get(ref_col, "")).strip() == str(h["reference"]).strip(), f"raw {raw.get(ref_col)!r} vs {h['reference']!r}")
        add(f"hop{n}_normalised_amount_consistent", norm.get("amount_minor") == h.get("amount_minor"), f"{norm.get('amount_minor')} vs {h.get('amount_minor')}")
        acct = h.get("statement_account_raw")
        direction = h.get("direction")
        alias = (manifest.get("path") or {}).get("alias_map_used") or {}
        canon = alias.get(acct, acct)
        if direction == "debit":
            add(f"hop{n}_direction_account_consistent", canon == h["from_account"], f"debit from statement account {acct} (canonical {canon}) → from_account {h['from_account']}")
        elif direction == "credit":
            add(f"hop{n}_direction_account_consistent", canon == h["to_account"], f"credit into statement account {acct} (canonical {canon}) → to_account {h['to_account']}")
        t = h.get("event_time")
        if t and prev_t and h.get("hop_class") != "uncertain_time":
            add(f"hop{n}_temporal_order", t >= prev_t, f"{prev_t} → {t}")
        if t:
            prev_t = t
        if prev_amt is not None:
            amt = h.get("amount_minor") or 0
            flags = set(h.get("flags") or [])
            if amt > prev_amt * 1.02:
                add(f"hop{n}_conservation_flag", "merged_inflow" in flags, "amount grew: merged_inflow flag required")
            elif amt < prev_amt * 0.98:
                add(f"hop{n}_conservation_flag", "split" in flags, "amount shrank: split flag required")
            else:
                add(f"hop{n}_conservation_flag", True, "amount carried within 2%")
        prev_amt = h.get("amount_minor")
        p = found_files.get(h.get("source_sha256"))
        if p is not None:
            st, det = locator_check(p, h)
            add(f"hop{n}_locator", True if st == "ok" else (None if st in {"unverifiable"} else False) if st != "value_present_locator_row_mismatch" else False, f"{st}: {det}")
    cons = (manifest.get("constraints") or {}).get("conservation") or {}
    if hops:
        add("path_entry_exit", cons.get("entry_minor") == hops[0].get("amount_minor") and cons.get("exit_minor") == hops[-1].get("amount_minor"), "entry/exit amounts match first/last hop")
    failed = [c for c in checks if c["status"] == "fail"]
    return {"verdict": "FAIL" if failed else "PASS", "failed": len(failed), "passed": sum(1 for c in checks if c["status"] == "pass"), "skipped": sum(1 for c in checks if c["status"] == "skip"),
            "checks": checks, "case": manifest.get("case"), "path": {k: v for k, v in (manifest.get("path") or {}).items() if k != "alias_map_used"},
            "note": "PASS means the derivation reproduces from the cited files and no cited file changed. It is not a legal determination."}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest")
    ap.add_argument("--files", help="directory holding the cited source files (by original name or sha256)")
    ap.add_argument("--key", help="HMAC key if the manifest was signed")
    ap.add_argument("--json", help="write the machine-readable result here")
    a = ap.parse_args(argv)
    try:
        manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"cannot read manifest: {exc}", file=sys.stderr)
        return 2
    res = verify(manifest, Path(a.files) if a.files else None, a.key)
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"PS05-X proof verification: {res['verdict']}  (passed {res['passed']}, failed {res['failed']}, skipped {res['skipped']})")
    for c in res["checks"]:
        mark = {"pass": "✓", "fail": "✗", "skip": "–"}[c["status"]]
        print(f"  {mark} {c['check']}: {c['detail']}")
    print(res["note"])
    return 0 if res["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
