"""Shared normalisation helpers. Every function keeps the raw value available to the caller.

Money: integer minor units (paise). Never float.
Dates: ambiguous formats are flagged, never silently resolved.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

PARSER_VERSION = "0.1.0"

_AMOUNT_CLEAN = re.compile(r"[^\d.\-()]")
_DR_CR = re.compile(r"\b(DR|CR|Dr|Cr|dr|cr)\b\.?")


@dataclass
class MoneyResult:
    minor: int | None
    raw: str
    warnings: list[str] = field(default_factory=list)
    hint_direction: str | None = None  # from DR/CR suffixes


def parse_money(raw) -> MoneyResult:
    if raw is None:
        return MoneyResult(None, "", ["missing_amount"])
    s = str(raw).strip()
    if s == "" or s.lower() in {"nan", "none", "-", "--"}:
        return MoneyResult(None, s, ["missing_amount"])
    warnings: list[str] = []
    hint = None
    m = _DR_CR.search(s)
    if m:
        hint = "debit" if m.group(1).lower() == "dr" else "credit"
    negative = False
    if "(" in s and ")" in s:
        negative = True
    cleaned = _AMOUNT_CLEAN.sub("", s).replace("(", "").replace(")", "")
    if cleaned.startswith("-"):
        negative = True
        cleaned = cleaned[1:]
    if cleaned.count(".") > 1:
        # e.g. OCR noise "1.2.300"
        warnings.append("amount_multiple_decimal_points")
        return MoneyResult(None, s, warnings, hint)
    if cleaned == "" or cleaned == ".":
        return MoneyResult(None, s, ["amount_unparseable"], hint)
    if "." in cleaned:
        whole, frac = cleaned.split(".")
        frac = (frac + "00")[:2]
        if len(cleaned.split(".")[1]) > 2:
            warnings.append("amount_truncated_to_2dp")
    else:
        whole, frac = cleaned, "00"
    try:
        minor = int(whole or "0") * 100 + int(frac)
    except ValueError:
        return MoneyResult(None, s, ["amount_unparseable"], hint)
    if negative:
        minor = -minor
    if re.search(r"[OoIl|S]", s):
        warnings.append("amount_contains_letter_like_chars")
    return MoneyResult(minor, s, warnings, hint)


@dataclass
class DateResult:
    dt: datetime | None
    raw: str
    precision: str  # second|minute|day|month|ambiguous|unknown
    warnings: list[str] = field(default_factory=list)
    timezone_name: str | None = "Asia/Kolkata"


_DATE_FORMATS = [
    ("%Y-%m-%d %H:%M:%S", "second"),
    ("%Y-%m-%dT%H:%M:%S", "second"),
    ("%Y-%m-%dT%H:%M:%SZ", "second"),
    ("%Y-%m-%d %H:%M", "minute"),
    ("%Y-%m-%d", "day"),
    ("%d-%m-%Y %H:%M:%S", "second"),
    ("%d-%m-%Y %H:%M", "minute"),
    ("%d-%m-%Y", "day"),
    ("%d/%m/%Y %H:%M:%S", "second"),
    ("%d/%m/%Y %H:%M", "minute"),
    ("%d/%m/%Y", "day"),
    ("%d %b %Y %H:%M:%S", "second"),
    ("%d %b %Y", "day"),
    ("%d-%b-%Y", "day"),
    ("%d-%b-%y", "day"),
    ("%d %B %Y", "day"),
    ("%b %d, %Y", "day"),
]

_IST_OFFSET_SECONDS = 5 * 3600 + 30 * 60


def _to_utc(naive: datetime, tz_name: str | None) -> datetime:
    if tz_name == "Asia/Kolkata":
        from datetime import timedelta
        return (naive - timedelta(seconds=_IST_OFFSET_SECONDS)).replace(tzinfo=timezone.utc)
    return naive.replace(tzinfo=timezone.utc)


def parse_datetime(raw, assume_tz: str | None = "Asia/Kolkata") -> DateResult:
    if raw is None:
        return DateResult(None, "", "unknown", ["missing_date"], assume_tz)
    if isinstance(raw, datetime):
        dt = raw if raw.tzinfo else _to_utc(raw, assume_tz)
        return DateResult(dt.astimezone(timezone.utc), raw.isoformat(), "second", [], assume_tz)
    s = str(raw).strip()
    if s == "" or s.lower() in {"nan", "none"}:
        return DateResult(None, s, "unknown", ["missing_date"], assume_tz)
    warnings: list[str] = []
    # two-digit-year slash dates like 03/04/26 are ambiguous (dd/mm vs mm/dd)
    m2 = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2})(?:\s+(\d{1,2}):(\d{2}))?", s)
    if m2:
        a, b, yy = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
        if a <= 12 and b <= 12:
            warnings.append("ambiguous_date_dd_mm_vs_mm_dd")
            # keep a *provisional* day-first reading for ordering but flag it as ambiguous
            try:
                naive = datetime(2000 + yy, b, a, int(m2.group(4) or 0), int(m2.group(5) or 0))
                return DateResult(_to_utc(naive, assume_tz), s, "ambiguous", warnings, assume_tz)
            except ValueError:
                return DateResult(None, s, "ambiguous", warnings + ["date_unparseable"], assume_tz)
        try:
            naive = datetime(2000 + yy, b, a, int(m2.group(4) or 0), int(m2.group(5) or 0))
            warnings.append("two_digit_year_assumed_20xx")
            return DateResult(_to_utc(naive, assume_tz), s, "minute" if m2.group(4) else "day", warnings, assume_tz)
        except ValueError:
            return DateResult(None, s, "unknown", ["date_unparseable"], assume_tz)
    # dd/mm/yyyy where both <= 12 is also technically ambiguous but Indian statements are day-first; flag softly
    m4 = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})(.*)", s)
    if m4 and int(m4.group(1)) <= 12 and int(m4.group(2)) <= 12 and int(m4.group(1)) != int(m4.group(2)):
        warnings.append("day_first_assumed")
    for fmt, prec in _DATE_FORMATS:
        try:
            naive = datetime.strptime(s, fmt)
            if fmt.endswith("Z"):
                return DateResult(naive.replace(tzinfo=timezone.utc), s, prec, warnings, "UTC")
            return DateResult(_to_utc(naive, assume_tz), s, prec, warnings, assume_tz)
        except ValueError:
            continue
    try:
        iso = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if iso.tzinfo is None:
            iso = _to_utc(iso, assume_tz)
        return DateResult(iso.astimezone(timezone.utc), s, "second", warnings, assume_tz)
    except ValueError:
        pass
    return DateResult(None, s, "unknown", warnings + ["date_unparseable"], assume_tz)


CHANNEL_PATTERNS = [
    ("UPI", re.compile(r"\bUPI\b|@[a-z]{2,}\b", re.I)),
    ("IMPS", re.compile(r"\bIMPS\b", re.I)),
    ("NEFT", re.compile(r"\bNEFT\b", re.I)),
    ("RTGS", re.compile(r"\bRTGS\b", re.I)),
    ("card", re.compile(r"\bPOS\b|\bCARD\b|\bATM\b", re.I)),
    ("cash", re.compile(r"\bCASH\b", re.I)),
]


def infer_channel(narration: str | None) -> str:
    if not narration:
        return "unknown"
    for name, pat in CHANNEL_PATTERNS:
        if pat.search(narration):
            return name
    return "unknown"


# Header mapping: canonical field -> candidate header substrings (lowercase)
HEADER_SYNONYMS: dict[str, list[str]] = {
    "datetime": ["txn date", "transaction date", "date", "value date", "timestamp", "txn_date", "tran date", "posting date", "time"],
    "narration": ["narration", "description", "particulars", "remarks", "details", "transaction details", "desc"],
    "reference": ["utr", "ref no", "reference", "ref", "transaction id", "txn id", "rrn", "cheque no", "chq", "transaction reference"],
    "debit": ["debit", "withdrawal", "withdrawal amt", "dr amount", "dr", "paid out", "debit amount"],
    "credit": ["credit", "deposit", "deposit amt", "cr amount", "cr", "paid in", "credit amount"],
    "amount": ["amount", "amt", "transaction amount", "txn amount", "value"],
    "direction": ["type", "dr/cr", "cr/dr", "transaction type", "txn type"],
    "balance": ["balance", "closing balance", "running balance", "bal", "available balance"],
    "counterparty": ["counterparty", "beneficiary", "payee", "to account", "from account", "beneficiary account", "counter party", "other party", "vpa", "payer"],
    "counterparty_name": ["beneficiary name", "payee name", "counterparty name", "name", "remitter name"],
    "account": ["account", "account no", "account number", "acct", "a/c no", "a/c"],
    "channel": ["channel", "mode", "payment mode"],
}


def guess_column_mapping(headers: list[str]) -> tuple[dict[str, str], list[str]]:
    """Return {canonical_field: header} and list of unmapped headers. Exact-ish match first, then substring."""
    mapping: dict[str, str] = {}
    used: set[str] = set()
    lowered = {h: re.sub(r"[^a-z0-9/ ]", " ", str(h).lower()).strip() for h in headers}
    # pass 1: exact
    for field_name, syns in HEADER_SYNONYMS.items():
        for h, lh in lowered.items():
            if h in used:
                continue
            if lh in syns:
                mapping[field_name] = h
                used.add(h)
                break
    # pass 2: substring, longest synonym first to avoid "date" eating "value date"
    for field_name, syns in HEADER_SYNONYMS.items():
        if field_name in mapping:
            continue
        for syn in sorted(syns, key=len, reverse=True):
            hit = None
            for h, lh in lowered.items():
                if h in used:
                    continue
                if re.search(rf"(^|\s){re.escape(syn)}(\s|$)", lh):
                    hit = h
                    break
            if hit:
                mapping[field_name] = hit
                used.add(hit)
                break
    # 'account' must not steal a counterparty column
    if "account" in mapping and "counterparty" in mapping and mapping["account"] == mapping["counterparty"]:
        del mapping["account"]
    unmapped = [h for h in headers if h not in used]
    return mapping, unmapped


# ----- file kind detection (magic bytes) -----
_MAGIC = [
    (b"%PDF", "pdf"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
]


def detect_kind(data: bytes, filename: str) -> tuple[str, list[str]]:
    """Return (kind, warnings). kind in pdf|xlsx|docx|csv|json|txt|png|jpeg|unknown.

    The extension is a hint; magic bytes decide for binary types. Mismatches are flagged.
    """
    warnings: list[str] = []
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    head = data[:16]
    for magic, kind in _MAGIC:
        if head.startswith(magic):
            if ext and ext not in {kind, "jpg" if kind == "jpeg" else kind}:
                warnings.append(f"extension_mismatch:{ext}->{kind}")
            return kind, warnings
    if head.startswith(b"PK\x03\x04"):
        # zip container: xlsx or docx. Inspect central names.
        try:
            import io
            import zipfile
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
                total = sum(i.file_size for i in z.infolist())
                if total > 200 * 1024 * 1024:
                    warnings.append("archive_expansion_too_large")
                    return "unknown", warnings
                if any(n.startswith("xl/") for n in names):
                    if ext != "xlsx":
                        warnings.append(f"extension_mismatch:{ext}->xlsx")
                    return "xlsx", warnings
                if any(n.startswith("word/") for n in names):
                    if ext != "docx":
                        warnings.append(f"extension_mismatch:{ext}->docx")
                    return "docx", warnings
        except Exception:
            warnings.append("zip_container_unreadable")
        return "unknown", warnings
    # text-like
    sample = data[:4096]
    if b"\x00" in sample:
        return "unknown", warnings + ["binary_content_unrecognised"]
    try:
        text = sample.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = sample.decode("latin-1")
            warnings.append("non_utf8_text_decoded_as_latin1")
        except Exception:
            return "unknown", warnings
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        return "json", warnings
    if ext == "csv":
        return "csv", warnings
    # content-based CSV: most non-empty lines must share the same delimiter count (>= 2 commas); prose with commas stays text
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if ext != "txt" and len(lines) >= 3:
        counts = [ln.count(",") for ln in lines]
        common = max(set(counts), key=counts.count)
        if common >= 2 and counts.count(common) >= max(3, int(0.6 * len(counts))):
            return "csv", warnings
    return "txt", warnings
