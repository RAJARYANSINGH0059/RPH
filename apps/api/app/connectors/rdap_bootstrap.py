"""RDAP through the IANA bootstrap registry, for domain registration and for IP address allocation.

The connector this replaces asked `rdap.org` for every domain. That service answers with a redirect to whichever
server is authoritative, and the fixed host allowlist could not follow it, so a real lookup produced
`redirect_not_followed` and no registration data at all. The screen offered registrar intelligence and the code
returned a note about its own plumbing.

RFC 7484 defines the way round this: IANA publishes a registry mapping each TLD, and each address block, to the
RDAP service that is authoritative for it. Reading that registry first means the request goes straight to the
server that holds the answer, and the answer carries the authority of the registry that gave it.

The address checks are not relaxed to make this work. A bootstrap entry is a hostname from a registry, not a
hostname from a user, but it is still resolved and still refused if it points anywhere private, loopback,
link-local or at cloud metadata — and so is every redirect hop after it.

What this module will not do: it will not present current registration as historical ownership, and it will not
try to see past redaction. Most registries now withhold the registrant, and a withheld field is reported as
withheld rather than guessed at or filled from somewhere else.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from datetime import datetime, timezone

BOOTSTRAP_HOST = "data.iana.org"
BOOTSTRAP = {
    "domain": f"https://{BOOTSTRAP_HOST}/rdap/dns.json",
    "ipv4": f"https://{BOOTSTRAP_HOST}/rdap/ipv4.json",
    "ipv6": f"https://{BOOTSTRAP_HOST}/rdap/ipv6.json",
}
RDAP_MODULE_VERSION = "1.0.0"
MAX_REDIRECTS = 3

# RDAP event names worth surfacing, mapped to the words an investigator uses.
EVENT_LABELS = {
    "registration": "registered",
    "expiration": "expires",
    "last changed": "last_changed",
    "last update of RDAP database": "rdap_database_updated",
    "transfer": "transferred",
    "deletion": "deleted",
    "reregistration": "reregistered",
    "last re-registration": "last_reregistration",
    "locked": "locked",
    "unlocked": "unlocked",
}

DOMAIN_LIMITATIONS = [
    "rdap_is_current_registration_not_historical_ownership",
    "registrant_contact_data_is_commonly_withheld_by_the_registry",
    "a_shared_registrar_does_not_indicate_a_shared_operator",
]
IP_LIMITATIONS = [
    "rdap_ip_allocation_describes_the_network_holder_not_the_person_using_an_address",
    "allocation_is_current_unless_the_registry_supplies_dated_events",
    "a_shared_network_or_asn_does_not_indicate_a_shared_operator",
]


@dataclass
class RdapResult:
    query: str
    kind: str                       # domain|ip
    status: str                     # answered|no_authoritative_server|unsupported|lookup_failed|not_found
    service_url: str | None = None
    fields: dict = field(default_factory=dict)
    raw_keys: list[str] = field(default_factory=list)
    error: str | None = None
    observed_at: datetime | None = None
    limitations: list[str] = field(default_factory=list)

    @property
    def answered(self) -> bool:
        return self.status == "answered"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ bootstrap registry

def _services(payload: dict) -> list[tuple[list[str], list[str]]]:
    out = []
    for entry in payload.get("services", []) or []:
        if isinstance(entry, list) and len(entry) >= 2:
            keys = [str(k).lower() for k in entry[0] if isinstance(k, (str, int))]
            urls = [str(u) for u in entry[1] if isinstance(u, str) and u.startswith("https://")]
            if keys and urls:
                out.append((keys, urls))
    return out


def domain_service(payload: dict, domain: str) -> str | None:
    """The RDAP base URL authoritative for a domain's TLD, choosing the longest matching suffix."""
    name = (domain or "").strip().rstrip(".").lower()
    labels = name.split(".")
    best: tuple[int, str] | None = None
    for keys, urls in _services(payload):
        for key in keys:
            klabels = key.split(".")
            if len(klabels) <= len(labels) and labels[-len(klabels):] == klabels:
                if best is None or len(klabels) > best[0]:
                    best = (len(klabels), urls[0])
    return best[1] if best else None


def ip_service(payload: dict, ip: str) -> str | None:
    """The RDAP base URL authoritative for the address block containing an address.

    The registry lists CIDR blocks per RIR; the most specific block that contains the address wins, which is the
    same rule routing uses and avoids asking the wrong registry for an answer it would decline.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    best: tuple[int, str] | None = None
    for keys, urls in _services(payload):
        for key in keys:
            try:
                net = ipaddress.ip_network(key, strict=False)
            except ValueError:
                continue
            if net.version != addr.version or addr not in net:
                continue
            if best is None or net.prefixlen > best[0]:
                best = (net.prefixlen, urls[0])
    return best[1] if best else None


# ------------------------------------------------------------------ field extraction

def _events(payload: dict) -> dict:
    out: dict = {}
    for e in payload.get("events", []) or []:
        if not isinstance(e, dict):
            continue
        action = str(e.get("eventAction", "")).lower()
        label = EVENT_LABELS.get(action, action.replace(" ", "_") or "unknown_event")
        if e.get("eventDate"):
            out[label] = e["eventDate"]
    return out


def _vcard_value(entity: dict, want: str) -> str | None:
    """Pull one field out of a jCard. A withheld field simply is not there, and that is reported as withheld."""
    arr = entity.get("vcardArray")
    if not (isinstance(arr, list) and len(arr) > 1 and isinstance(arr[1], list)):
        return None
    for item in arr[1]:
        if isinstance(item, list) and len(item) >= 4 and str(item[0]).lower() == want:
            val = item[3]
            if isinstance(val, list):
                return " ".join(str(v) for v in val if v).strip() or None
            return str(val) or None
    return None


def _entity(entities: list, role: str) -> dict | None:
    for ent in entities or []:
        if isinstance(ent, dict) and role in [str(r).lower() for r in (ent.get("roles") or [])]:
            return ent
    return None


def _public_ids(entity: dict) -> str | None:
    """The registrar's IANA ID, which is the only durable way to name a registrar."""
    for pid in entity.get("publicIds", []) or []:
        if isinstance(pid, dict) and "iana" in str(pid.get("type", "")).lower():
            return str(pid.get("identifier"))
    return None


def domain_fields(payload: dict) -> dict:
    entities = payload.get("entities") or []
    registrar = _entity(entities, "registrar") or {}
    reseller = _entity(entities, "reseller") or {}
    registrant = _entity(entities, "registrant")
    events = _events(payload)
    nameservers = sorted({str(ns.get("ldhName", "")).rstrip(".").lower()
                          for ns in payload.get("nameservers", []) or []
                          if isinstance(ns, dict) and ns.get("ldhName")})
    return {
        "domain": str(payload.get("ldhName") or payload.get("unicodeName") or "").rstrip(".").lower() or None,
        "handle": payload.get("handle"),
        "registry_status": [str(s) for s in payload.get("status", []) or []],
        "registered": events.get("registered"),
        "expires": events.get("expires"),
        "last_changed": events.get("last_changed"),
        "events": events,
        "registrar_name": _vcard_value(registrar, "fn") if registrar else None,
        "registrar_handle": registrar.get("handle") if registrar else None,
        "registrar_iana_id": _public_ids(registrar) if registrar else None,
        # A reseller is reported only where the registry actually supplies one; it is never inferred.
        "reseller": _vcard_value(reseller, "fn") if reseller else None,
        "nameservers": nameservers,
        "registrant_disclosed": registrant is not None and _vcard_value(registrant, "fn") is not None,
        "registrant_name": _vcard_value(registrant, "fn") if registrant else None,
        "redaction": "registrant_withheld_or_redacted_by_the_registry" if (
            registrant is None or _vcard_value(registrant, "fn") is None) else "registrant_disclosed_by_the_registry",
        "secure_dns": (payload.get("secureDNS") or {}).get("delegationSigned"),
        "port43": payload.get("port43"),
        "rdap_conformance": [str(c) for c in payload.get("rdapConformance", []) or []],
    }


def ip_fields(payload: dict) -> dict:
    entities = payload.get("entities") or []
    registrant = _entity(entities, "registrant") or _entity(entities, "administrative") or {}
    events = _events(payload)
    start, end = payload.get("startAddress"), payload.get("endAddress")
    prefix = None
    if start and end:
        try:
            nets = list(ipaddress.summarize_address_range(ipaddress.ip_address(start), ipaddress.ip_address(end)))
            prefix = ", ".join(str(n) for n in nets[:4]) + ("…" if len(nets) > 4 else "")
        except ValueError:
            prefix = None
    return {
        "handle": payload.get("handle"),
        "start_address": start,
        "end_address": end,
        "prefix": prefix,
        "cidr_from_registry": [f"{c.get('v4prefix') or c.get('v6prefix')}/{c.get('length')}"
                               for c in payload.get("cidr0_cidrs", []) or [] if isinstance(c, dict)],
        "network_name": payload.get("name"),
        "network_type": payload.get("type"),
        "country": payload.get("country"),
        "ip_version": payload.get("ipVersion"),
        "parent_handle": payload.get("parentHandle"),
        "registry": payload.get("port43") or None,
        "registry_status": [str(s) for s in payload.get("status", []) or []],
        "allocated": events.get("registered"),
        "last_changed": events.get("last_changed"),
        "events": events,
        "organisation": _vcard_value(registrant, "fn") if registrant else None,
        "organisation_handle": registrant.get("handle") if registrant else None,
        # Several RIRs put the originating AS in an extension; it is reported only when present.
        "asn_from_registry": payload.get("arin_originas0_originautnums") or payload.get("originAutnums") or None,
    }


# ------------------------------------------------------------------ lookup

def lookup(http, query: str, kind: str, *, bootstrap_cache: dict | None = None) -> RdapResult:
    """Resolve the authoritative RDAP server from the IANA registry, then ask it.

    `http` is a `SafeHttp`; `data.iana.org` must be in its allowlist. The authoritative server is reached with
    `any_public_host`, because its hostname comes from the registry rather than from a fixed list — the address
    checks and the redirect cap still apply to it and to every hop.
    """
    started = _now()
    limits = DOMAIN_LIMITATIONS if kind == "domain" else IP_LIMITATIONS
    try:
        if kind == "domain":
            payload = (bootstrap_cache or {}).get("domain") or http.get_json(BOOTSTRAP["domain"])
            if bootstrap_cache is not None:
                bootstrap_cache["domain"] = payload
            base = domain_service(payload, query)
            path = f"domain/{query.strip().rstrip('.').lower()}"
        else:
            family = "ipv6" if ipaddress.ip_address(query).version == 6 else "ipv4"
            payload = (bootstrap_cache or {}).get(family) or http.get_json(BOOTSTRAP[family])
            if bootstrap_cache is not None:
                bootstrap_cache[family] = payload
            base = ip_service(payload, query)
            path = f"ip/{query}"
    except Exception as exc:
        return RdapResult(query, kind, "lookup_failed", None, {}, [], f"bootstrap: {type(exc).__name__}: {str(exc)[:160]}",
                          started, limits)

    if not base:
        return RdapResult(query, kind, "no_authoritative_server", None, {}, [],
                          "The IANA bootstrap registry lists no RDAP service for this name or address block",
                          started, limits)

    url = base.rstrip("/") + "/" + path
    try:
        body = http.get_json(url, any_public_host=True, max_redirects=MAX_REDIRECTS)
    except Exception as exc:
        text = str(exc)
        status = "not_found" if "404" in text else "lookup_failed"
        return RdapResult(query, kind, status, url, {}, [], f"{type(exc).__name__}: {text[:160]}", started, limits)

    fields = domain_fields(body) if kind == "domain" else ip_fields(body)
    fields["module_version"] = RDAP_MODULE_VERSION
    return RdapResult(query, kind, "answered", url, fields, sorted(body.keys()), None, started, limits)
