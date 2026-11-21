"""Regex extraction of cyber/financial indicators from free text. Indicators are stored as strings; never visited."""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

URL_RE = re.compile(r"\bhttps?://[^\s<>\"')\]]+", re.I)
DOMAIN_RE = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,24})\b", re.I)
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
EMAIL_RE = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.I)
VPA_RE = re.compile(r"\b[a-z0-9._-]{2,}@[a-z]{2,}(?:bank|upi|pay|axis|ybl|okicici|okhdfcbank|oksbi|paytm|ibl|apl|fictbank|testpay)?\b", re.I)
PHONE_RE = re.compile(r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)")
UTR_RE = re.compile(r"\b(?:UTR|RRN|Ref(?:erence)?\s*(?:No\.?)?)[:\s#-]*([A-Z0-9]{10,22})\b", re.I)
ACCOUNT_RE = re.compile(r"\b(?:A/?C|Acct|Account)(?:\s*(?:No\.?|Number))?[:\s#-]*([Xx*]{0,8}\d{4,18})\b", re.I)

# common false-positive "domains" (file extensions, etc.)
_DOMAIN_STOP = {"e.g", "i.e", "etc", "vs", "no", "rs", "inr"}
_STOP_TLDS = {"pdf", "csv", "xlsx", "docx", "png", "jpg", "jpeg", "json", "txt", "zip", "exe"}


@dataclass(frozen=True)
class Indicator:
    kind: str  # url|domain|ip|email|vpa|phone|utr|account
    value: str
    span: tuple[int, int]


def _domain_from_url(url: str) -> str | None:
    m = re.match(r"https?://([^/:?#]+)", url, re.I)
    return m.group(1).lower() if m else None


def extract_indicators(text: str) -> list[Indicator]:
    out: list[Indicator] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, value: str, span: tuple[int, int]):
        key = (kind, value.lower())
        if key not in seen:
            seen.add(key)
            out.append(Indicator(kind, value, span))

    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;")
        add("url", url, m.span())
        d = _domain_from_url(url)
        if d and not IPV4_RE.fullmatch(d):
            add("domain", d, m.span())
    for m in IPV4_RE.finditer(text):
        try:
            ipaddress.ip_address(m.group(0))
            add("ip", m.group(0), m.span())
        except ValueError:
            continue
    for m in EMAIL_RE.finditer(text):
        add("email", m.group(0).lower(), m.span())
    for m in VPA_RE.finditer(text):
        v = m.group(0).lower()
        if (("email", v) in seen) or "." in v.split("@")[1]:
            continue  # looks like an email, not a VPA
        add("vpa", v, m.span())
    for m in DOMAIN_RE.finditer(text):
        d = m.group(0).lower()
        tld = d.rsplit(".", 1)[-1]
        if d in _DOMAIN_STOP or tld in _STOP_TLDS:
            continue
        if any(("email", e) in seen and e.endswith("@" + d) for (k, e) in seen if k == "email"):
            continue
        if IPV4_RE.fullmatch(d):
            continue
        add("domain", d, m.span())
    for m in PHONE_RE.finditer(text):
        add("phone", re.sub(r"\D", "", m.group(0))[-10:], m.span())
    for m in UTR_RE.finditer(text):
        add("utr", m.group(1).upper(), m.span())
    for m in ACCOUNT_RE.finditer(text):
        add("account", m.group(1).upper(), m.span())
    return out


def ip_classification(ip: str) -> str:
    """Classify an IP for SSRF safety and investigator context."""
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return "invalid"
    if a.version == 4:
        for net in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24"):
            if a in ipaddress.ip_network(net):
                return "documentation"  # checked first: Python's is_private also covers these RFC 5737 ranges
        if a in ipaddress.ip_network("169.254.169.254/32"):
            return "metadata"
    if a.is_loopback:
        return "loopback"
    if a.is_private:
        return "private"
    if a.is_link_local:
        return "link_local"
    if a.is_multicast:
        return "multicast"
    if a.is_reserved:
        return "reserved"
    return "public"
