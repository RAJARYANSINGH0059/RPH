"""Extraction of cyber and financial indicators from free text.

Indicators are stored as strings and are never visited by this module. Addresses of both families are
recognised, because a complaint that quotes an IPv6 address should not silently lose it.
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

URL_RE = re.compile(r"\bhttps?://[^\s<>\"')\]]+", re.I)
DOMAIN_RE = re.compile(r"\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,24})\b", re.I)
IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
# IPv6 is matched in two stages rather than with one expression. A single regex that accepts every valid form
# (compressed runs, an embedded IPv4 tail, a zone or prefix suffix) and rejects every invalid one is unreadable
# and still wrong at the edges, so candidate runs are found loosely and then validated by the standard library,
# which is the only authority on whether a string is an address.
_IPV6_CANDIDATE = re.compile(r"\[?[0-9A-Fa-f:]{2,}(?::[0-9A-Fa-f]{1,4})?(?:\.\d{1,3}){0,3}\]?")
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


def _ipv6_candidates(text: str):
    """Yield (address, span) for every substring the standard library accepts as an IPv6 address.

    A candidate is trimmed from the right while it fails to parse, so an address followed by punctuation, a port
    or a prefix length is still recognised as the address it contains.
    """
    for m in _IPV6_CANDIDATE.finditer(text):
        token = m.group(0)
        start = m.start()
        if token.startswith("["):
            token, start = token[1:], start + 1
        token = token.split("]")[0]
        if token.count(":") < 2:
            continue                      # one colon is a time, a port or a label, not a compressed address
        for end in range(len(token), 1, -1):
            cut = token[:end].rstrip(":")
            if cut.count(":") < 2:
                break
            try:
                addr = ipaddress.ip_address(cut)
            except ValueError:
                continue
            if addr.version == 6:
                yield str(addr), (start, start + len(cut))
            break


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
    for value, span in _ipv6_candidates(text):
        add("ip", value, span)
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
    else:
        # 2001:db8::/32 is the IPv6 documentation range (RFC 3849), the counterpart of the IPv4 ranges above.
        # Synthetic fixtures live here, so it is recognised before is_private and never looked up.
        if a in ipaddress.ip_network("2001:db8::/32"):
            return "documentation"
    # Order matters here, because the standard library's categories overlap: a link-local address is also
    # private, and so is a loopback address. Testing is_private first made the narrower labels unreachable and
    # told the reader "private" about an address whose actual category explains far more.
    if a.is_loopback:
        return "loopback"
    if a.is_link_local:
        return "link_local"
    if a.is_multicast:
        return "multicast"
    if a.is_private:
        return "private"
    if a.is_reserved:
        return "reserved"
    return "public"
