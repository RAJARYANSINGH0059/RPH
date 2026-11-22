"""Schema-aware import of technical observation JSON/CSV (DNS, hosting, URL observations).

Accepted top-level shapes:
  {"observations": [ {...}, ... ]}   or   [ {...}, ... ]
Each observation: {"type": "dns"|"hosting"|"url"|"rdap", "observed_at": iso, "domain": ..., "ip": ..., "ttl": ..., "provider": ..., "asn": ..., "source": ..., "note": ...}
Unknown keys are preserved in `extra`. Nothing is invented for missing fields.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

PARSER_NAME = "technical_observations_json"
# The types a case may supply as evidence. The first six were already accepted; the rest were added so that a
# case can carry certificate, reverse-DNS, allocation, discovered-name and dated historical evidence without any
# provider being configured. That matters because historical passive DNS needs a licensed provider: supplying
# dated observations as evidence is how an investigation gets history today, and the alternative would be to
# leave the only honest source of historical data with nowhere to enter the system.
KNOWN_TYPES = {"dns", "hosting", "url", "rdap", "cdn", "note",
               "certificate", "ptr", "asn", "passive_dns", "historical_dns", "subdomain"}


@dataclass
class Observation:
    json_path: str
    obs_type: str
    fields: dict
    extra: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class TechnicalResult:
    observations: list[Observation]
    warnings: list[str] = field(default_factory=list)
    raw_count: int = 0


_CORE_KEYS = {"type", "observed_at", "domain", "ip", "ttl", "provider", "asn", "source", "note", "url", "registrar",
              "created", "valid_from", "valid_to", "resolver",
              # record-level and infrastructure fields
              "record", "value", "hostname", "certificate_key", "fingerprint", "issuer", "issuer_name",
              "common_name", "not_before", "not_after", "serial", "serial_number", "san_names", "names",
              "subdomain", "parent", "first_seen", "last_seen", "records", "organisation", "organization",
              "prefix", "country", "network_name", "expires", "last_changed", "nameservers", "status"}


def parse_technical_json_bytes(data: bytes, max_items: int = 20000) -> TechnicalResult:
    warnings: list[str] = []
    try:
        obj = json.loads(data.decode("utf-8-sig"))
    except Exception as exc:
        return TechnicalResult([], [f"json_invalid:{type(exc).__name__}"], 0)
    if isinstance(obj, dict):
        items = obj.get("observations")
        base = "$.observations"
        if items is None:
            items = [obj]
            base = "$"
            warnings.append("single_object_treated_as_one_observation")
    elif isinstance(obj, list):
        items, base = obj, "$"
    else:
        return TechnicalResult([], ["json_root_not_object_or_array"], 0)
    out: list[Observation] = []
    for i, it in enumerate(items[:max_items]):
        if not isinstance(it, dict):
            warnings.append(f"item_{i}_not_object")
            continue
        w: list[str] = []
        t = str(it.get("type", "")).lower() or "unknown"
        if t not in KNOWN_TYPES:
            w.append("unknown_observation_type")
        if "observed_at" not in it:
            w.append("missing_observed_at")
        fields = {k: it[k] for k in it if k in _CORE_KEYS}
        extra = {k: it[k] for k in it if k not in _CORE_KEYS}
        out.append(Observation(f"{base}[{i}]", t, fields, extra, w))
    if len(items) > max_items:
        warnings.append("item_limit_reached")
    return TechnicalResult(out, warnings, len(items))


# ------------------------------------------------------------------------------------ graph mapping

# Supplied observations that map onto the same typed relationships the connectors produce. Reusing that mapping
# means a dated record supplied as evidence and the same record read from a provider become the same kind of
# edge, with the same limitations, rather than two parallel code paths that drift apart.
GRAPH_TYPES = {"certificate", "ptr", "asn", "passive_dns", "historical_dns", "subdomain"}

_SUPPLIED_RECORD_TYPES = {"A", "AAAA", "CNAME", "MX", "NS", "TXT", "PTR"}


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def to_graph_observation(obs: "Observation") -> tuple[str, dict] | None:
    """Reshape one supplied observation into the (type, fields) pair the infrastructure graph understands.

    Returns None when the observation carries nothing a relationship could be built from, which is reported as a
    warning by the caller rather than silently dropped.
    """
    f = {**obs.fields, **obs.extra}
    t = obs.obs_type

    if t == "certificate":
        domain = f.get("domain") or f.get("common_name")
        key = f.get("certificate_key") or f.get("fingerprint") or f.get("serial_number") or f.get("serial")
        if not (domain and key):
            return None
        names = [str(n).strip().lower() for n in _as_list(f.get("san_names") or f.get("names")) if n]
        return "certificate", {
            "domain": str(domain).lower(), "certificate_key": str(key),
            "common_name": (str(f.get("common_name")).lower() if f.get("common_name") else None),
            "issuer_name": f.get("issuer_name") or f.get("issuer"),
            "not_before": f.get("not_before"), "not_after": f.get("not_after"),
            "serial_number": f.get("serial_number") or f.get("serial"),
            "san_count": len(names), "san_names": names,
            "validity_state": "validity_as_supplied", "log_entry_timestamp": f.get("observed_at"),
        }

    if t == "ptr":
        ip, hostname = f.get("ip"), f.get("hostname") or f.get("value")
        if not (ip and hostname):
            return None
        return "dns_record", {
            "name": str(ip), "record": "PTR", "status": "answered",
            "values": [{"ip": str(ip), "hostname": str(hostname).rstrip(".").lower(), "raw": str(hostname)}],
            "value_count": 1, "ttl": f.get("ttl"), "resolver": f.get("resolver") or f.get("source"),
            "valid_until": f.get("valid_to"),
        }

    if t == "asn":
        ip = f.get("ip")
        if not ip:
            return None
        return "ip_allocation", {
            "ip": str(ip), "status": "answered",
            "organisation": f.get("organisation") or f.get("organization") or f.get("provider"),
            "network_name": f.get("network_name"), "prefix": f.get("prefix"), "country": f.get("country"),
            "allocated": f.get("first_seen") or f.get("valid_from"),
            "asn_from_registry": [str(f["asn"]).lstrip("ASas")] if f.get("asn") else None,
        }

    if t in {"passive_dns", "historical_dns"}:
        rows = []
        for r in _as_list(f.get("records")):
            if isinstance(r, dict):
                rows.append({"name": r.get("name") or r.get("rrname") or f.get("domain"),
                             "value": r.get("value") or r.get("rdata") or r.get("ip"),
                             "record": (r.get("record") or r.get("rrtype") or "A"),
                             "first_seen": r.get("first_seen") or r.get("time_first"),
                             "last_seen": r.get("last_seen") or r.get("time_last"),
                             "observation_count": r.get("count") or r.get("observation_count")})
        if not rows and f.get("domain") and (f.get("ip") or f.get("value")):
            rows.append({"name": f.get("domain"), "value": f.get("ip") or f.get("value"),
                         "record": f.get("record") or "A",
                         "first_seen": f.get("first_seen") or f.get("valid_from"),
                         "last_seen": f.get("last_seen") or f.get("valid_to"),
                         "observation_count": None})
        if not rows:
            return None
        return "passive_dns", {"indicator": f.get("domain") or f.get("ip"), "records": rows,
                               "record_count": len(rows)}

    if t == "subdomain":
        parent = f.get("parent") or f.get("domain")
        children = [str(n).strip().lower() for n in
                    (_as_list(f.get("names")) or _as_list(f.get("subdomain"))) if n]
        if not (parent and children):
            return None
        parent = str(parent).lower()
        return "subdomain_discovery", {
            "domain": parent, "method": f.get("source") or "supplied_observation",
            "names": [{"name": c, "parent_domain": parent, "is_wildcard": c.startswith("*."),
                       "is_parent_itself": c == parent, "discovery_source": "supplied_observation",
                       "certificates": _as_list(f.get("certificate_key") or f.get("fingerprint")),
                       "first_log_entry": f.get("first_seen") or f.get("observed_at"),
                       "status": "discovered_name_not_confirmed_active"} for c in children],
        }

    return None


def supplied_record_set(obs: "Observation") -> tuple[str, dict] | None:
    """A supplied `dns` observation that names a record type becomes that record type, not an address record.

    The existing path reads a `dns` observation as a domain-to-address mapping, which is right for an A record
    and wrong for the other five. Where the observation says which record type it is, it is read as that type.
    """
    f = {**obs.fields, **obs.extra}
    if obs.obs_type != "dns":
        return None
    record = str(f.get("record") or "").upper()
    if record not in _SUPPLIED_RECORD_TYPES or record in {"A"}:
        return None            # A records keep the existing behaviour, so no case changes shape under this
    domain = f.get("domain")
    value = f.get("value") or f.get("ip") or f.get("hostname")
    if not (domain and value):
        return None
    value = str(value).rstrip(".").lower()
    if record == "AAAA":
        payload = {"ip": value, "family": "ipv6", "classification": None, "raw": value}
    elif record == "CNAME":
        payload = {"target": value, "raw": value}
    elif record == "MX":
        payload = {"exchange": value, "preference": f.get("preference"), "raw": value}
    elif record == "NS":
        payload = {"nameserver": value, "raw": value}
    elif record == "TXT":
        payload = {"strings": [str(value)], "joined": str(value), "raw": str(value)}
    else:
        payload = {"hostname": value, "ip": f.get("ip"), "raw": value}
    return "dns_record", {"name": str(domain).lower(), "record": record, "status": "answered",
                          "values": [payload], "value_count": 1, "ttl": f.get("ttl"),
                          "resolver": f.get("resolver") or f.get("source"), "valid_until": f.get("valid_to")}
