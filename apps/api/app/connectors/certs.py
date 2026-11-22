"""Certificate Transparency search, and the subdomain names certificates reveal.

CT logs are append-only public records of the certificates that authorities issued. For an investigator chasing
a phishing domain they are useful twice over: they show when a certificate for the name first appeared, which
often dates the setup of the site, and their Subject Alternative Names reveal sibling names the complaint never
mentioned.

Two distinctions matter enough to encode rather than describe.

A log entry timestamp is not the certificate's validity period and neither is evidence that a page was serving.
A certificate can be issued and never deployed. So a name found this way is a *discovered name*, a lead to check,
not an observation that anything was hosted there — and the module labels it that way at the point of discovery
rather than leaving the reader to remember.

A shared certificate does not make two domains the same operator's. Certificates covering many names are what
hosting platforms and CDNs issue by default, so names appearing together are a candidate relationship with that
alternative attached, never a finding of common control.

No name discovered here is resolved, probed or connected to. Discovery is passive: this module reads a public log
search and nothing else.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

CT_MODULE_VERSION = "1.0.0"
CT_HOST = "crt.sh"
CT_SEARCH = "https://crt.sh/"
MAX_ENTRIES = 200

LIMITATIONS = [
    "a_ct_log_entry_records_issuance_not_that_a_site_was_serving",
    "the_log_entry_time_is_not_the_certificates_validity_period",
    "names_on_a_shared_or_platform_certificate_do_not_indicate_a_shared_operator",
    "ct_search_coverage_depends_on_which_logs_the_source_indexes",
]

_NAME = re.compile(r"^[a-z0-9_*]([a-z0-9_-]{0,61}[a-z0-9])?(\.[a-z0-9_]([a-z0-9_-]{0,61}[a-z0-9])?)+$", re.I)


@dataclass
class Certificate:
    """One certificate as the log search reports it. Fields the source does not supply stay absent."""

    entry_id: str | None
    issuer_name: str | None
    common_name: str | None
    san_names: list[str] = field(default_factory=list)
    not_before: str | None = None
    not_after: str | None = None
    serial_number: str | None = None
    entry_timestamp: str | None = None

    @property
    def key(self) -> str:
        """A stable identifier for the certificate entity. crt.sh's JSON carries no SHA-256 fingerprint, so the
        log entry id is used and named as such rather than a fingerprint being invented."""
        return f"crtsh:{self.entry_id}" if self.entry_id else f"serial:{self.serial_number or 'unknown'}"

    def validity_state(self, now: datetime | None = None) -> str:
        """Whether the certificate's own validity window has passed, where the source gave one."""
        if not self.not_after:
            return "validity_not_supplied"
        try:
            end = datetime.fromisoformat(self.not_after.replace("Z", "+00:00"))
        except ValueError:
            return "validity_unparseable"
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        ref = now or datetime.now(timezone.utc)
        if end < ref:
            return "expired"
        start = None
        if self.not_before:
            try:
                start = datetime.fromisoformat(self.not_before.replace("Z", "+00:00"))
                if start.tzinfo is None:
                    start = start.replace(tzinfo=timezone.utc)
            except ValueError:
                start = None
        if start and start > ref:
            return "not_yet_valid"
        return "within_validity_window"

    def as_fields(self) -> dict:
        return {
            "certificate_key": self.key,
            "entry_id": self.entry_id,
            "issuer_name": self.issuer_name,
            "common_name": self.common_name,
            "san_names": self.san_names,
            "san_count": len(self.san_names),
            "not_before": self.not_before,
            "not_after": self.not_after,
            "serial_number": self.serial_number,
            "log_entry_timestamp": self.entry_timestamp,
            "validity_state": self.validity_state(),
            "fingerprint": None,
            "fingerprint_note": "This log search does not supply a SHA-256 fingerprint; the log entry id identifies the record.",
            "module_version": CT_MODULE_VERSION,
        }


def _clean_name(raw: str) -> str | None:
    name = (raw or "").strip().rstrip(".").lower()
    if not name or " " in name or "@" in name:
        return None
    return name if _NAME.match(name) else None


def parse_entries(payload: list, parent: str) -> list[Certificate]:
    """Read the log search result, keeping each certificate's own names."""
    parent = (parent or "").strip().rstrip(".").lower()
    out: list[Certificate] = []
    for item in (payload or [])[:MAX_ENTRIES]:
        if not isinstance(item, dict):
            continue
        names: list[str] = []
        for part in str(item.get("name_value") or "").splitlines():
            name = _clean_name(part)
            if name and name not in names:
                names.append(name)
        cn = _clean_name(str(item.get("common_name") or ""))
        if cn and cn not in names:
            names.insert(0, cn)
        out.append(Certificate(
            entry_id=str(item["id"]) if item.get("id") is not None else None,
            issuer_name=(str(item.get("issuer_name")) or None) if item.get("issuer_name") else None,
            common_name=cn,
            san_names=names,
            not_before=str(item["not_before"]) if item.get("not_before") else None,
            not_after=str(item["not_after"]) if item.get("not_after") else None,
            serial_number=str(item["serial_number"]) if item.get("serial_number") else None,
            entry_timestamp=str(item["entry_timestamp"]) if item.get("entry_timestamp") else None,
        ))
    return out


def discovered_names(certs: list[Certificate], parent: str) -> list[dict]:
    """The names these certificates mention, as leads with their evidence attached.

    A wildcard is kept as the wildcard it is rather than expanded into names nobody observed, and each name
    carries the certificate that revealed it and the earliest log entry that mentioned it.
    """
    parent = (parent or "").strip().rstrip(".").lower()
    found: dict[str, dict] = {}
    for c in certs:
        for name in c.san_names:
            bare = name[2:] if name.startswith("*.") else name
            if not (bare == parent or bare.endswith("." + parent)):
                continue          # a name on the same certificate but outside the domain is a candidate link, not a subdomain
            row = found.setdefault(name, {
                "name": name,
                "parent_domain": parent,
                "is_wildcard": name.startswith("*."),
                "is_parent_itself": bare == parent,
                "discovery_source": "certificate_transparency",
                "discovery_method": "subject_alternative_name",
                "certificates": [],
                "first_log_entry": c.entry_timestamp,
                "status": "discovered_name_not_confirmed_active",
            })
            row["certificates"].append(c.key)
            if c.entry_timestamp and (row["first_log_entry"] is None or c.entry_timestamp < row["first_log_entry"]):
                row["first_log_entry"] = c.entry_timestamp
    return sorted(found.values(), key=lambda r: (not r["is_parent_itself"], r["name"]))


def related_names(certs: list[Certificate], parent: str) -> list[dict]:
    """Names sharing a certificate with the domain but lying outside it: candidates, with the ordinary explanation."""
    parent = (parent or "").strip().rstrip(".").lower()
    out: dict[str, dict] = {}
    for c in certs:
        outside = [n for n in c.san_names
                   if not ((n[2:] if n.startswith("*.") else n) == parent
                           or (n[2:] if n.startswith("*.") else n).endswith("." + parent))]
        for name in outside:
            row = out.setdefault(name, {"name": name, "shares_certificate_with": parent, "certificates": [],
                                        "evidence_level": "candidate",
                                        "alternatives": [
                                            "A hosting platform or CDN issues one certificate covering many unrelated customers' names.",
                                            "A reseller or managed service may group names it does not control.",
                                        ]})
            row["certificates"].append(c.key)
            row["names_on_that_certificate"] = len(c.san_names)
    return sorted(out.values(), key=lambda r: r["name"])[:100]


def search_url(domain: str, include_subdomains: bool = True) -> str:
    """The log search URL. `%` is the wildcard the source uses for a name suffix."""
    name = (domain or "").strip().rstrip(".").lower()
    q = f"%.{name}" if include_subdomains else name
    return f"{CT_SEARCH}?q={q}&output=json"
