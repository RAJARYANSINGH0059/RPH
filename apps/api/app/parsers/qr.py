"""QR decoding and payment-instruction payload parsing.

Decoder: OpenCV QRCodeDetector (already installed as a RapidOCR dependency). No URI is ever opened, followed or
executed; this is evidence decoding only. Unsupported payloads are classified, not guessed.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, unquote, urlsplit

DECODER_VERSION = "1.0.0"


@dataclass
class QrDecode:
    payload: str
    bbox: list[int] | None  # [x0, y0, x1, y1] in the supplied image
    method: str  # cv2_multi | cv2_single | cv2_rotated | cv2_upscaled
    confidence: int | None = None  # OpenCV gives no confidence; kept for OCR-backed text paths


def status() -> dict:
    try:
        import cv2  # noqa: F401
        return {"available": True, "engine": "opencv", "version": cv2.__version__, "decoder_version": DECODER_VERSION}
    except Exception as exc:  # pragma: no cover
        return {"available": False, "reason": f"opencv not importable ({type(exc).__name__})", "decoder_version": DECODER_VERSION}


def _bbox(pts) -> list[int] | None:
    try:
        xs = [float(p[0]) for p in pts.reshape(-1, 2)]
        ys = [float(p[1]) for p in pts.reshape(-1, 2)]
        return [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]
    except Exception:
        return None


def decode_qr(data: bytes) -> tuple[list[QrDecode], list[str]]:
    """Decode every QR code found in an image. Tries the multi-code detector, then single, then rotations and upscaling
    for damaged/rotated photographs. Returns ([], warnings) when nothing decodes."""
    warnings: list[str] = []
    try:
        import cv2
        import numpy as np
        from PIL import Image
    except Exception as exc:  # pragma: no cover
        return [], [f"qr_decoder_unavailable:{type(exc).__name__}"]
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as exc:
        return [], [f"image_unreadable:{type(exc).__name__}"]
    arr = np.array(img)
    det = cv2.QRCodeDetector()
    out: list[QrDecode] = []

    def _multi(a, method: str) -> bool:
        try:
            ok, texts, pts, _ = det.detectAndDecodeMulti(a)
        except Exception:
            ok, texts, pts = False, [], None
        found = False
        if ok and texts:
            for i, t in enumerate(texts):
                if t:
                    out.append(QrDecode(t, _bbox(pts[i]) if pts is not None else None, method))
                    found = True
        return found

    def _single(a, method: str) -> bool:
        try:
            t, pts, _ = det.detectAndDecode(a)
        except Exception:
            return False
        if t:
            out.append(QrDecode(t, _bbox(pts) if pts is not None else None, method))
            return True
        return False

    if not _multi(arr, "cv2_multi") and not _single(arr, "cv2_single"):
        for k, rot in ((cv2.ROTATE_90_CLOCKWISE, "90"), (cv2.ROTATE_180, "180"), (cv2.ROTATE_90_COUNTERCLOCKWISE, "270")):
            if _single(cv2.rotate(arr, k), "cv2_rotated"):
                warnings.append(f"decoded_after_rotation_{rot}_bbox_in_rotated_frame")
                break
        else:
            big = cv2.resize(arr, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            if _single(big, "cv2_upscaled"):
                warnings.append("decoded_after_2x_upscale_bbox_in_scaled_frame")
    if not out:
        warnings.append("no_qr_code_decoded")
    # de-duplicate identical payloads found twice
    seen, uniq = set(), []
    for q in out:
        if q.payload not in seen:
            seen.add(q.payload)
            uniq.append(q)
    return uniq, warnings


# ------------------------------------------------------------------ payload parsing

@dataclass
class ParsedInstruction:
    payload_type: str  # upi|url|text|unsupported|invalid
    raw_payload: str
    fields: dict = field(default_factory=dict)  # raw decoded params, unknown ones included
    payee_vpa: str | None = None
    payee_vpa_raw: str | None = None
    payee_name_raw: str | None = None
    amount_minor: int | None = None
    amount_raw: str | None = None
    currency: str | None = None
    reference: str | None = None
    note_raw: str | None = None
    warnings: list[str] = field(default_factory=list)


_VPA_RE = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z][a-zA-Z0-9.\-]{1,64}$")
_KNOWN = {"pa", "pn", "am", "cu", "tn", "tr", "tid", "mc", "mode", "purpose", "url", "orgid", "sign", "mam", "minam"}


def normalise_vpa(v: str | None) -> str | None:
    """Lower-case and trim only. No fuzzy changes: a one-character difference stays a different identifier."""
    if v is None:
        return None
    v = v.strip()
    return v.lower() if v else None


def _money_minor(raw: str | None, warnings: list[str]) -> int | None:
    if raw is None or not str(raw).strip():
        return None
    s = str(raw).strip().replace(",", "")
    try:
        d = Decimal(s)
    except InvalidOperation:
        warnings.append("amount_not_numeric")
        return None
    if d < 0:
        warnings.append("amount_negative")
        return None
    q = d.quantize(Decimal("0.01"))
    if q != d:
        warnings.append("amount_has_more_than_two_decimals_rounded_half_even")
    return int(q * 100)


def parse_payment_payload(raw: str) -> ParsedInstruction:
    """Classify and parse a payment payload. Preserves the raw payload and every parameter (unknown keys included)."""
    p = ParsedInstruction(payload_type="unsupported", raw_payload=raw)
    s = raw.strip()
    if not s:
        p.payload_type = "invalid"
        p.warnings.append("empty_payload")
        return p
    low = s.lower()
    query = None
    if low.startswith("upi://pay") or low.startswith("upi:pay"):
        p.payload_type = "upi"
        try:
            query = urlsplit(s).query
        except ValueError:
            p.payload_type = "invalid"
            p.warnings.append("uri_unparseable")
            return p
    elif low.startswith("http://") or low.startswith("https://"):
        p.payload_type = "url"
        try:
            parts = urlsplit(s)
        except ValueError:
            p.payload_type = "invalid"
            p.warnings.append("uri_unparseable")
            return p
        p.fields["host"] = parts.hostname
        p.fields["path"] = parts.path
        query = parts.query
        if "pa=" not in parts.query:
            p.warnings.append("url_payload_without_upi_parameters_stored_as_evidence_string_not_opened")
    elif re.search(r"(^|[?&\s])pa=[^&\s]+", s):
        p.payload_type = "text"
        query = s.split("?", 1)[1] if "?" in s else s
        query = re.sub(r"\s+", "&", query.strip())
    elif _VPA_RE.match(s):
        p.payload_type = "text"
        query = f"pa={s}"
        p.warnings.append("bare_vpa_without_parameters")
    else:
        p.payload_type = "unsupported"
        p.warnings.append("payload_format_not_recognised_as_payment_instruction")
        return p
    pairs = parse_qsl(query or "", keep_blank_values=True)
    for k, v in pairs:
        key = k.strip().lower()
        p.fields.setdefault(key, unquote(v))
        if key not in _KNOWN:
            p.warnings.append(f"unknown_parameter_preserved:{key}")
    p.payee_vpa_raw = p.fields.get("pa")
    p.payee_vpa = normalise_vpa(p.payee_vpa_raw)
    if p.payee_vpa and not _VPA_RE.match(p.payee_vpa):
        p.warnings.append("payee_identifier_not_vpa_shaped")
    if p.payee_vpa is None:
        p.warnings.append("payee_missing")
    p.payee_name_raw = p.fields.get("pn")
    p.amount_raw = p.fields.get("am")
    p.amount_minor = _money_minor(p.amount_raw, p.warnings)
    if p.amount_raw is None:
        p.warnings.append("amount_not_fixed_in_instruction")
    cu = p.fields.get("cu")
    p.currency = cu.strip().upper() if cu else None
    if p.currency is None and p.amount_minor is not None:
        p.warnings.append("currency_missing_not_assumed")
    elif p.currency and p.currency != "INR":
        p.warnings.append(f"unsupported_currency:{p.currency}")
    p.reference = (p.fields.get("tr") or p.fields.get("tid") or None)
    if p.reference:
        p.reference = p.reference.strip() or None
    p.note_raw = p.fields.get("tn")
    return p
