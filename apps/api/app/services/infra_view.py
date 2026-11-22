"""Assemble what the case actually knows about its digital infrastructure, per domain and per address.

The existing infrastructure screens read the case graph and filter it by node type, which shows the entities but
loses the record behind them: a reader sees that a domain resolves somewhere without seeing which record type
said so, when it was read, what its TTL was, or that the MX lookup returned nothing at all.

This service reads the stored evidence instead of recomputing anything, so the page and the report quote the same
observations the graph was built from. Three things it is careful about:

A record type that returned no answer is reported, not omitted. "This domain publishes no MX record" is a finding
an investigator can use; an empty list is indistinguishable from a lookup nobody ran.

Current and historical observations stay in separate collections. Nothing here promotes a lookup made today into
evidence about the period when the money moved, and a case with no historical provider configured says so rather
than showing today's answer under a historical heading.

Coverage is stated per domain and per address: which record types were asked, which were answered, whether
registration was read, whether a certificate search ran, and which providers were not configured at all. An
absence of evidence is reported as an absence, never as a negative finding.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors import dns_records
from app.connectors.adapters import get_registry
from app.models import Case, Entity, EvidenceItem, Relationship
from app.parsers import indicators

INFRA_VIEW_VERSION = "1.0.0"

CURRENT_ONLY_NOTE = ("Every current lookup describes the moment it was made. A mapping read today is not evidence "
                     "of what a name pointed at when the money moved; only a dated historical observation can "
                     "support that, and this case shows historical observations separately.")


def _iso(v) -> str | None:
    return v.isoformat() if isinstance(v, datetime) else (v if isinstance(v, str) else None)


def _connector_states() -> dict:
    out = {}
    for name, c in get_registry().items():
        h = c.status()
        out[name] = {"status": h.status, "provider": c.provider, "detail": h.detail, "checked_at": _iso(h.checked_at)}
    return out


def _observations(db: Session, case: Case) -> list[EvidenceItem]:
    return list(db.execute(
        select(EvidenceItem).where(EvidenceItem.case_id == case.id, EvidenceItem.source_type.in_(["connector", "technical_observation"]))
    ).scalars())


def report(db: Session, case: Case) -> dict:
    """One structured answer for the infrastructure workspace, built only from what the case holds."""
    entities = list(db.execute(select(Entity).where(Entity.case_id == case.id)).scalars())
    by_id = {e.id: e for e in entities}
    rels = list(db.execute(select(Relationship).where(Relationship.case_id == case.id)).scalars())
    items = _observations(db, case)

    domains: dict[str, dict] = {}
    addresses: dict[str, dict] = {}
    certificates: list[dict] = []
    discovered: list[dict] = []
    historical: list[dict] = []
    shared_certificate: list[dict] = []
    classifications: list[dict] = []
    failures: list[dict] = []

    def domain_row(name: str) -> dict:
        return domains.setdefault(name, {
            "domain": name, "records": {}, "record_types_asked": [], "record_types_answered": [],
            "registration": None, "certificates": [], "discovered_names": [], "nameservers": [],
            "mail_exchangers": [], "addresses": [], "aliases": [], "historical_observations": 0,
        })

    def address_row(value: str) -> dict:
        return addresses.setdefault(value, {
            "ip": value, "family": "ipv6" if ":" in value else "ipv4",
            "classification": indicators.ip_classification(value),
            "allocation": None, "reverse_dns": None, "network_classification": None, "hosting": None,
            "domains": [],
        })

    for ev in items:
        payload = ev.normalised_value if isinstance(ev.normalised_value, dict) else {}
        # A supplied observation records both the type the file declared and the shape it was read as. The shape
        # is what decides where it belongs here, because that is what the graph was built from.
        kind = str(payload.get("graph_type") or payload.get("type") or "")
        observed = _iso(ev.observed_at)
        provider = (ev.source_locator or {}).get("provider") if isinstance(ev.source_locator, dict) else None
        base = {"evidence_item_id": ev.id, "observed_at": observed, "provider": provider,
                "source_url": (ev.source_locator or {}).get("url") if isinstance(ev.source_locator, dict) else None,
                "limitations": list(ev.quality_flags or [])}

        # Observations a case already holds use the earlier shapes: a `dns` observation that is a domain-to-address
        # mapping with no record type named, a `hosting` observation, and an `rdap` observation with two fields.
        # Reading only the new shapes would leave this page blank for every case recorded before them, which would
        # look like an absence of evidence rather than an absence of support in this view.
        if kind == "dns" and payload.get("domain") and payload.get("ip") and not payload.get("record"):
            name, value = str(payload["domain"]).lower(), str(payload["ip"])
            record = "AAAA" if ":" in value else "A"
            d = domain_row(name)
            row = {**base, "record": record, "status": "answered",
                   "status_meaning": dns_records.STATUS_MEANING["answered"],
                   "values": [{"ip": value, "classification": indicators.ip_classification(value),
                               "family": "ipv6" if ":" in value else "ipv4", "raw": value}],
                   "value_count": 1, "ttl": payload.get("ttl"),
                   "resolver": payload.get("resolver") or payload.get("source"),
                   "valid_until": _iso(ev.event_time_end), "error": None,
                   "shape": "supplied_mapping_without_a_named_record_type"}
            d["records"].setdefault(record, []).append(row)
            for key, coll in (("record_types_asked", d["record_types_asked"]), ("record_types_answered", d["record_types_answered"])):
                if record not in coll:
                    coll.append(record)
            d["addresses"].append(value)
            address_row(value)["domains"].append(name)
            continue

        if kind in {"hosting", "cdn"} and payload.get("ip"):
            value = str(payload["ip"])
            a = address_row(value)
            a["hosting"] = {**base, "provider": payload.get("provider"), "asn": payload.get("asn"),
                            "is_cdn": kind == "cdn",
                            "meaning": "The provider hosting the address, as supplied. Hosting is not control."}
            if payload.get("domain"):
                domain_row(str(payload["domain"]).lower())["addresses"].append(value)
                a["domains"].append(str(payload["domain"]).lower())
            continue

        if kind == "rdap" and payload.get("domain") and not payload.get("status"):
            name = str(payload["domain"]).lower()
            domain_row(name)["registration"] = {**base, "status": "answered",
                                                "registrar_name": payload.get("registrar"),
                                                "registered": payload.get("created"),
                                                "shape": "supplied_registration_observation",
                                                "redaction": "not stated by this observation"}
            continue

        if kind == "dns_record":
            name = str(payload.get("name") or "")
            record = str(payload.get("record") or "").upper()
            if not (name and record):
                continue
            target = address_row(name) if record == "PTR" and payload.get("values") else None
            row = {**base, "record": record, "status": payload.get("status"),
                   "status_meaning": payload.get("status_meaning"), "values": payload.get("values") or [],
                   "value_count": payload.get("value_count"), "ttl": payload.get("ttl"),
                   "resolver": payload.get("resolver"), "valid_until": payload.get("valid_until"),
                   "error": payload.get("error")}
            if record == "PTR":
                # A PTR lookup is asked of the reverse name but is about the address, so it is filed there.
                for v in payload.get("values") or []:
                    if v.get("ip"):
                        address_row(v["ip"])["reverse_dns"] = {**row, "hostname": v.get("hostname")}
                if not (payload.get("values") or []):
                    failures.append({**row, "name": name, "about": "reverse_dns"})
                continue
            d = domain_row(name)
            d["records"].setdefault(record, []).append(row)
            if record not in d["record_types_asked"]:
                d["record_types_asked"].append(record)
            if payload.get("status") == "answered":
                if record not in d["record_types_answered"]:
                    d["record_types_answered"].append(record)
                for v in payload.get("values") or []:
                    if record in {"A", "AAAA"} and v.get("ip"):
                        d["addresses"].append(v["ip"])
                        address_row(v["ip"])["domains"].append(name)
                    elif record == "NS" and v.get("nameserver"):
                        d["nameservers"].append(v["nameserver"])
                    elif record == "MX" and v.get("exchange"):
                        d["mail_exchangers"].append(v["exchange"])
                    elif record == "CNAME" and v.get("target"):
                        d["aliases"].append(v["target"])
            elif payload.get("status") in {"timeout", "no_nameservers", "resolver_error"}:
                failures.append({**row, "name": name, "about": "dns"})

        elif kind == "rdap":
            name = str(payload.get("domain") or "")
            if not name:
                continue
            d = domain_row(name)
            d["registration"] = {**base, **{k: payload.get(k) for k in (
                "status", "status_detail", "registry_status", "registered", "expires", "last_changed",
                "registrar_name", "registrar_iana_id", "reseller", "nameservers", "redaction",
                "registrant_disclosed", "registrant_name", "secure_dns", "handle", "events")}}

        elif kind == "ip_allocation":
            value = str(payload.get("ip") or "")
            if not value:
                continue
            address_row(value)["allocation"] = {**base, **{k: payload.get(k) for k in (
                "status", "status_detail", "registry_status", "prefix", "network_name", "network_type",
                "country", "organisation", "organisation_handle", "allocated", "last_changed",
                "asn_from_registry", "start_address", "end_address", "ip_version", "registry")}}

        elif kind == "certificate":
            row = {**base, **payload}
            certificates.append(row)
            name = str(payload.get("domain") or "")
            if name and payload.get("certificate_key"):
                domain_row(name)["certificates"].append(payload.get("certificate_key"))

        elif kind == "subdomain_discovery":
            name = str(payload.get("domain") or "")
            names = payload.get("names") or []
            discovered.append({**base, "domain": name, "names": names, "name_count": len(names),
                               "method": payload.get("method")})
            if name:
                domain_row(name)["discovered_names"] = [n.get("name") for n in names if isinstance(n, dict)]

        elif kind == "shared_certificate_names":
            shared_certificate.append({**base, "domain": payload.get("domain"),
                                       "names": payload.get("names") or [],
                                       "name_count": payload.get("name_count")})

        elif kind == "passive_dns":
            rows = payload.get("records") or []
            historical.append({**base, "indicator": payload.get("indicator"), "records": rows,
                               "record_count": len(rows)})
            name = str(payload.get("indicator") or "")
            if name in domains:
                domains[name]["historical_observations"] += len(rows)

        elif kind == "network_classification":
            value = str(payload.get("ip") or "")
            row = {**base, **{k: payload.get(k) for k in ("classification", "tor_exit_node", "list_read_at",
                                                          "list_size", "vpn_or_proxy")}}
            classifications.append({**row, "ip": value})
            if value:
                address_row(value)["network_classification"] = row

        elif kind == "error":
            failures.append({**base, "about": "connector", "name": payload.get("indicator"),
                             "error": payload.get("error")})

    # Dated observations supplied as evidence rather than fetched: this is how a case gets history while no
    # passive-DNS provider is configured, so they are counted as historical and never as current.
    supplied_historical = [h for h in historical if (h.get("provider") or "").lower().startswith("supplied")]

    for d in domains.values():
        for key in ("addresses", "nameservers", "mail_exchangers", "aliases"):
            d[key] = sorted(dict.fromkeys(d[key]))
        d["certificates"] = sorted(dict.fromkeys(d["certificates"]))
        missing = [rt for rt in dns_records.DOMAIN_RECORD_TYPES if rt not in d["record_types_asked"]]
        d["record_types_not_asked"] = missing
        d["coverage"] = ("complete" if not missing and d["registration"] else
                         "partial" if d["record_types_asked"] or d["registration"] else "none")
    for a in addresses.values():
        a["domains"] = sorted(dict.fromkeys(a["domains"]))

    # Relationship counts by type, so the page can show what the graph gained without re-deriving it.
    rel_counts: dict[str, int] = defaultdict(int)
    for r in rels:
        if r.relationship_type in {"RESOLVES_TO", "ALIAS_OF", "MAIL_EXCHANGE", "USES_NAMESERVER", "REVERSE_DNS",
                                   "ALLOCATED_TO", "ANNOUNCED_BY", "REGISTERED_WITH", "NAMED_IN_CERTIFICATE",
                                   "HAS_SUBDOMAIN", "SHARES_CERTIFICATE", "HOSTED_ON", "SHARED_INFRASTRUCTURE"}:
            rel_counts[r.relationship_type] += 1

    states = _connector_states()
    not_configured = sorted(n for n, s in states.items() if s["status"] == "not_configured")

    return {
        "version": INFRA_VIEW_VERSION,
        "case_id": case.id,
        "domains": sorted(domains.values(), key=lambda d: d["domain"]),
        "addresses": sorted(addresses.values(), key=lambda a: (a["family"], a["ip"])),
        "certificates": certificates,
        "discovered_names": discovered,
        "shared_certificate_names": shared_certificate,
        "network_classifications": classifications,
        "historical_observations": historical,
        "lookup_failures": failures,
        "relationship_counts": dict(sorted(rel_counts.items())),
        "entity_counts": {t: sum(1 for e in entities if e.entity_type == t)
                          for t in sorted({e.entity_type for e in entities})},
        "connectors": states,
        "record_types": list(dns_records.DOMAIN_RECORD_TYPES),
        "record_status_meanings": dns_records.STATUS_MEANING,
        "coverage_summary": {
            "domains": len(domains),
            "domains_with_full_record_set": sum(1 for d in domains.values() if not d["record_types_not_asked"]),
            "domains_with_registration": sum(1 for d in domains.values() if d["registration"]),
            "addresses": len(addresses),
            "addresses_with_allocation": sum(1 for a in addresses.values() if a["allocation"]),
            "addresses_with_reverse_dns": sum(1 for a in addresses.values() if a["reverse_dns"]),
            "certificates": len(certificates),
            "addresses_with_hosting": sum(1 for a in addresses.values() if a["hosting"]),
            "historical_observation_sources": len(historical),
            "historical_observations_supplied_as_evidence": len(supplied_historical),
            "providers_not_configured": not_configured,
        },
        "limitations": [
            CURRENT_ONLY_NOTE,
            "A record type that returned no answer is reported with the reason. An absence of evidence is not a negative finding.",
            "Shared addresses, nameservers, autonomous systems, registrars and certificates are candidate links only; none of them establishes common ownership or control.",
            "A PTR name is published by whoever holds the address block, so it describes their labelling and not who used the address.",
            "Address allocation names the organisation holding a range, never the subscriber and never a person's location.",
            "A name found in a certificate was certified, not observed serving, and has not been resolved by this system.",
        ],
        "next": ("Where a record is missing or a provider is not configured, the evidence-request workflow drafts "
                 "a narrow request for the specific record and time window that would resolve it."),
    }
