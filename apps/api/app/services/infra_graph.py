"""Turn an infrastructure observation into the entities and relationships it actually supports.

One rule runs through this module: the relationship must say what the record says, and no more.

The connector it replaces wrote every DNS answer into the graph as `RESOLVES_TO`. That is right for an address
record and wrong for everything else. A nameserver record does not mean the domain resolves to the nameserver; a
mail exchanger is not where the site lives; a CNAME is an alias, and a PTR name is chosen by whoever holds the
address block rather than by whoever used an address. Flattening all of them into one edge type would let a
reader draw a conclusion the record never carried, so each record type gets the edge it means and keeps its
original RR type alongside.

The second rule is about strength. A name read out of a certificate is a lead: somebody asked an authority to
certify it, which is not evidence that anything was ever served there. Those arrive as `candidate`, with the
ordinary explanations attached, and so do names that merely share a certificate — shared certificates are what
hosting platforms issue by default, and the specification is explicit that shared infrastructure never becomes a
finding of common control.

On the evidence level given to a provider's dated historical record: this system did not make that observation,
the provider did, so the relationship records the observer in `method_name` and in its attributes and carries a
limitation saying so. The level describes how direct the observation was, not who holds it, and a dated record
covering the period in question is the most directly relevant evidence a case can have — calling it stale
because it is old would understate exactly the evidence an investigator most needs.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Case, EvidenceLevel, Relationship
from app.parsers import indicators
from app.services.ingestion import add_relationship, get_or_create_entity

INFRA_GRAPH_VERSION = "1.0.0"

# Which edge each record type means, and how to read it. The UI and the report quote these rather than
# paraphrasing them, so that one wording is used everywhere.
RECORD_RELATIONSHIPS = {
    "A": ("RESOLVES_TO", "The name resolved to this IPv4 address at the observation time."),
    "AAAA": ("RESOLVES_TO", "The name resolved to this IPv6 address at the observation time."),
    "CNAME": ("ALIAS_OF", "The name is an alias for this other name; the alias target is where resolution continues."),
    "MX": ("MAIL_EXCHANGE", "This host is published as a mail exchanger for the name. It is not where the site is hosted."),
    "NS": ("USES_NAMESERVER", "This host is published as a nameserver for the name. A shared nameserver is common and indicates nothing about control."),
    "PTR": ("REVERSE_DNS", "The holder of the address block publishes this name for the address. It is their label, not proof of who used the address."),
    "TXT": (None, "A text record. It carries provider verification tokens and policy, and names no second entity."),
}

PTR_LIMITS = ["a_ptr_name_is_published_by_the_address_block_holder_not_by_whoever_used_the_address"]
NS_LIMITS = ["a_shared_nameserver_is_ordinary_and_indicates_nothing_about_common_control"]
MX_LIMITS = ["a_mail_exchanger_is_not_the_host_serving_the_site"]


def _domain(db: Session, case: Case, name: str, seen: datetime | None, attrs: dict | None = None):
    return get_or_create_entity(db, case.id, "domain", name.strip().rstrip(".").lower(), None, attrs, seen)


def _ip(db: Session, case: Case, value: str, seen: datetime | None):
    return get_or_create_entity(db, case.id, "ip", value, None,
                                {"classification": indicators.ip_classification(value),
                                 "family": "ipv6" if ":" in value else "ipv4"}, seen)


def _rel(db: Session, case: Case, src, dst, rel_type: str, level: EvidenceLevel, method: str,
         evidence_ids: list[str], **kw) -> Relationship:
    return add_relationship(db, case.id, src, dst, rel_type, level, method, evidence_ids, **kw)


# ----------------------------------------------------------------------------------------- DNS records

def _from_dns_record(db: Session, case: Case, f: dict, ev_ids: list[str], observed: datetime | None,
                     provider: str, limits: list[str]) -> list[Relationship]:
    record = str(f.get("record") or "").upper()
    if f.get("status") != "answered":
        # A domain with no MX record, a name that does not exist, a resolver that timed out: each is recorded as
        # evidence by the caller. None of them is a relationship, and inventing one would assert a mapping that
        # was never observed.
        return []
    rel_type, meaning = RECORD_RELATIONSHIPS.get(record, (None, ""))
    if rel_type is None:
        return []

    name = str(f.get("name") or "").rstrip(".").lower()
    if not name:
        return []
    out: list[Relationship] = []
    valid_to = f.get("valid_until")
    base = dict(record_type=record, meaning=meaning, ttl=f.get("ttl"), resolver=f.get("resolver"),
                provider=provider, graph_version=INFRA_GRAPH_VERSION)

    for value in f.get("values") or []:
        if record in {"A", "AAAA"}:
            ip = value.get("ip")
            if not ip:
                continue
            src, dst = _domain(db, case, name, observed), _ip(db, case, ip, observed)
            extra, extra_limits = {"address_family": value.get("family"), "address_classification": value.get("classification")}, []
        elif record == "CNAME":
            target = value.get("target")
            if not target:
                continue
            src, dst = _domain(db, case, name, observed), _domain(db, case, target, observed)
            extra, extra_limits = {}, []
        elif record == "MX":
            exchange = value.get("exchange")
            if not exchange:
                continue
            src, dst = _domain(db, case, name, observed), _domain(db, case, exchange, observed, {"role_seen": "mail_exchanger"})
            extra, extra_limits = {"preference": value.get("preference")}, MX_LIMITS
        elif record == "NS":
            ns = value.get("nameserver")
            if not ns:
                continue
            src, dst = _domain(db, case, name, observed), _domain(db, case, ns, observed, {"role_seen": "nameserver"})
            extra, extra_limits = {}, NS_LIMITS
        elif record == "PTR":
            hostname, ip = value.get("hostname"), value.get("ip")
            if not (hostname and ip):
                continue
            src, dst = _ip(db, case, ip, observed), _domain(db, case, hostname, observed)
            extra, extra_limits = {}, PTR_LIMITS
        else:
            continue
        out.append(_rel(db, case, src, dst, rel_type, EvidenceLevel.directly_observed, f"connector_dns_{record.lower()}",
                        ev_ids, observed_at=observed, valid_from=observed,
                        valid_to=_parse(valid_to),
                        limitations=limits + extra_limits,
                        attributes={**base, **extra, "raw": value.get("raw")}))
    return out


def _parse(value) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


# ----------------------------------------------------------------------------------------- registration

def _from_rdap(db: Session, case: Case, f: dict, ev_ids: list[str], observed: datetime | None,
               provider: str, limits: list[str]) -> list[Relationship]:
    name = str(f.get("domain") or "").rstrip(".").lower()
    if not name or f.get("status") != "answered":
        return []
    out: list[Relationship] = []
    dom = _domain(db, case, name, observed, {
        "registrar_name": f.get("registrar_name"), "registrar_iana_id": f.get("registrar_iana_id"),
        "registered": f.get("registered"), "expires": f.get("expires"), "last_changed": f.get("last_changed"),
        "registration_status": f.get("registry_status"), "redaction": f.get("redaction"),
    })
    registrar = f.get("registrar_name") or f.get("registrar_iana_id")
    if registrar:
        ent = get_or_create_entity(db, case.id, "registrar", str(registrar), None,
                                   {"iana_id": f.get("registrar_iana_id"), "handle": f.get("registrar_handle")}, observed)
        out.append(_rel(db, case, dom, ent, "REGISTERED_WITH", EvidenceLevel.directly_observed, "connector_rdap",
                        ev_ids, observed_at=observed, valid_from=_parse(f.get("registered")), limitations=limits,
                        attributes={"registrar_iana_id": f.get("registrar_iana_id"), "reseller": f.get("reseller"),
                                    "expires": f.get("expires"), "provider": provider,
                                    "meaning": "The registry names this registrar for the domain now. It is not evidence of who registered it originally.",
                                    "graph_version": INFRA_GRAPH_VERSION}))
    for ns in f.get("nameservers") or []:
        ent = _domain(db, case, ns, observed, {"role_seen": "nameserver"})
        out.append(_rel(db, case, dom, ent, "USES_NAMESERVER", EvidenceLevel.directly_observed, "connector_rdap_ns",
                        ev_ids, observed_at=observed, limitations=limits + NS_LIMITS,
                        attributes={"source": "rdap_delegation", "provider": provider,
                                    "graph_version": INFRA_GRAPH_VERSION}))
    return out


def _from_ip_allocation(db: Session, case: Case, f: dict, ev_ids: list[str], observed: datetime | None,
                        provider: str, limits: list[str]) -> list[Relationship]:
    value = str(f.get("ip") or "")
    if not value or f.get("status") != "answered":
        return []
    ip = _ip(db, case, value, observed)
    ip.attributes = {**(ip.attributes or {}), "network_name": f.get("network_name"), "network_type": f.get("network_type"),
                     "allocation_country": f.get("country"), "prefix": f.get("prefix"),
                     "allocated": f.get("allocated"), "network_holder": f.get("organisation")}
    out: list[Relationship] = []
    holder = f.get("organisation") or f.get("network_name")
    if holder:
        ent = get_or_create_entity(db, case.id, "network_holder", str(holder), None,
                                   {"handle": f.get("organisation_handle"), "country": f.get("country"),
                                    "prefix": f.get("prefix"), "network_type": f.get("network_type")}, observed)
        out.append(_rel(db, case, ip, ent, "ALLOCATED_TO", EvidenceLevel.directly_observed, "connector_ip_rdap",
                        ev_ids, observed_at=observed, valid_from=_parse(f.get("allocated")), limitations=limits,
                        attributes={"prefix": f.get("prefix"), "network_name": f.get("network_name"),
                                    "registry_status": f.get("registry_status"), "provider": provider,
                                    "meaning": "This organisation holds the address range. It is not the subscriber and not the person who used the address.",
                                    "graph_version": INFRA_GRAPH_VERSION}))
    asn = f.get("asn_from_registry")
    for number in (asn if isinstance(asn, list) else [asn] if asn else []):
        ent = get_or_create_entity(db, case.id, "asn", f"AS{number}", None, {"source": "rir_rdap"}, observed)
        out.append(_rel(db, case, ip, ent, "ANNOUNCED_BY", EvidenceLevel.directly_observed, "connector_ip_rdap_asn",
                        ev_ids, observed_at=observed, limitations=limits + [
                            "a_shared_autonomous_system_is_ordinary_and_indicates_nothing_about_common_control"],
                        attributes={"provider": provider, "graph_version": INFRA_GRAPH_VERSION}))
    return out


# ----------------------------------------------------------------------------------------- certificates

def _from_certificate(db: Session, case: Case, f: dict, ev_ids: list[str], observed: datetime | None,
                      provider: str, limits: list[str]) -> list[Relationship]:
    name = str(f.get("domain") or "").rstrip(".").lower()
    key = f.get("certificate_key")
    if not (name and key):
        return []
    cert = get_or_create_entity(db, case.id, "certificate", str(key), f.get("common_name") or str(key), {
        "issuer_name": f.get("issuer_name"), "common_name": f.get("common_name"),
        "not_before": f.get("not_before"), "not_after": f.get("not_after"),
        "serial_number": f.get("serial_number"), "san_count": f.get("san_count"),
        "validity_state": f.get("validity_state"), "log_entry_timestamp": f.get("log_entry_timestamp"),
    }, observed)
    dom = _domain(db, case, name, observed)
    return [_rel(db, case, dom, cert, "NAMED_IN_CERTIFICATE", EvidenceLevel.directly_observed,
                 "connector_certificate_transparency", ev_ids, observed_at=observed,
                 valid_from=_parse(f.get("not_before")), valid_to=_parse(f.get("not_after")),
                 limitations=limits, attributes={
                     "issuer_name": f.get("issuer_name"), "validity_state": f.get("validity_state"),
                     "log_entry_timestamp": f.get("log_entry_timestamp"), "provider": provider,
                     "meaning": "A certificate naming this domain was logged. Issuance is not evidence that a site was serving.",
                     "graph_version": INFRA_GRAPH_VERSION})]


def _from_subdomain_discovery(db: Session, case: Case, f: dict, ev_ids: list[str], observed: datetime | None,
                              provider: str, limits: list[str]) -> list[Relationship]:
    parent_name = str(f.get("domain") or "").rstrip(".").lower()
    if not parent_name:
        return []
    parent = _domain(db, case, parent_name, observed)
    out: list[Relationship] = []
    for row in f.get("names") or []:
        name = str(row.get("name") or "")
        if not name or row.get("is_parent_itself"):
            continue
        child = _domain(db, case, name.replace("*.", "wildcard."), observed, {
            "discovered_via": "certificate_subject_alternative_name", "is_wildcard": row.get("is_wildcard"),
            "first_log_entry": row.get("first_log_entry"), "resolution_checked": False})
        out.append(_rel(db, case, parent, child, "HAS_SUBDOMAIN", EvidenceLevel.candidate,
                        "connector_certificate_san", ev_ids, observed_at=observed, limitations=limits + [
                            "a_name_found_in_a_certificate_was_certified_not_observed_serving",
                            "this_name_has_not_been_resolved_by_this_system"],
                        attributes={"certificates": row.get("certificates"), "is_wildcard": row.get("is_wildcard"),
                                    "first_log_entry": row.get("first_log_entry"), "provider": provider,
                                    "meaning": "This name appeared in a certificate for the domain. It is a lead to check, not an observed service.",
                                    "graph_version": INFRA_GRAPH_VERSION}))
    return out


def _from_shared_certificate(db: Session, case: Case, f: dict, ev_ids: list[str], observed: datetime | None,
                             provider: str, limits: list[str]) -> list[Relationship]:
    parent_name = str(f.get("domain") or "").rstrip(".").lower()
    if not parent_name:
        return []
    parent = _domain(db, case, parent_name, observed)
    out: list[Relationship] = []
    for row in (f.get("names") or [])[:50]:
        name = str(row.get("name") or "")
        if not name:
            continue
        other = _domain(db, case, name.replace("*.", "wildcard."), observed)
        out.append(_rel(db, case, parent, other, "SHARES_CERTIFICATE", EvidenceLevel.candidate,
                        "connector_certificate_shared", ev_ids, observed_at=observed, direction="undirected",
                        limitations=limits + [
                            "a_shared_certificate_does_not_establish_common_ownership_or_control",
                            "platform_and_cdn_certificates_routinely_cover_many_unrelated_customers"],
                        attributes={"certificates": row.get("certificates"),
                                    "names_on_that_certificate": row.get("names_on_that_certificate"),
                                    "alternatives": row.get("alternatives"), "provider": provider,
                                    "meaning": "These names appear on the same certificate. That is a candidate link only.",
                                    "graph_version": INFRA_GRAPH_VERSION}))
    return out


# ----------------------------------------------------------------------------------------- historical

def _from_passive_dns(db: Session, case: Case, f: dict, ev_ids: list[str], observed: datetime | None,
                      provider: str, limits: list[str]) -> list[Relationship]:
    """Dated resolution observations from a provider, kept inside their own observation window.

    `valid_from` and `valid_to` are the provider's first and last sighting, so a reader comparing the window with
    the transaction time is comparing dated evidence with dated evidence. The observer is named, because this
    system did not see it.
    """
    out: list[Relationship] = []
    for row in f.get("records") or []:
        record = str(row.get("record") or "").upper()
        name, value = row.get("name"), row.get("value")
        if not (name and value) or record not in {"A", "AAAA", "CNAME"}:
            continue
        src = _domain(db, case, str(name), observed)
        dst = _ip(db, case, str(value), observed) if record in {"A", "AAAA"} else _domain(db, case, str(value), observed)
        rel_type = "RESOLVES_TO" if record in {"A", "AAAA"} else "ALIAS_OF"
        out.append(_rel(db, case, src, dst, rel_type, EvidenceLevel.directly_observed, f"provider_passive_dns_{record.lower()}",
                        ev_ids, observed_at=observed, valid_from=_parse(row.get("first_seen")),
                        valid_to=_parse(row.get("last_seen")), limitations=limits + [
                            "observed_by_the_provider_not_by_this_system",
                            "the_window_is_the_providers_sighting_range_not_a_guarantee_of_continuity"],
                        attributes={"record_type": record, "observed_by": provider,
                                    "first_seen": row.get("first_seen"), "last_seen": row.get("last_seen"),
                                    "observation_count": row.get("observation_count"), "historical": True,
                                    "meaning": "A provider observed this mapping between these dates. It is dated historical evidence, not a current lookup.",
                                    "graph_version": INFRA_GRAPH_VERSION}))
    return out


# ----------------------------------------------------------------------------------------- entry point

_HANDLERS = {
    "dns_record": _from_dns_record,
    "rdap": _from_rdap,
    "ip_allocation": _from_ip_allocation,
    "certificate": _from_certificate,
    "subdomain_discovery": _from_subdomain_discovery,
    "shared_certificate_names": _from_shared_certificate,
    "passive_dns": _from_passive_dns,
}


def record(db: Session, case: Case, obs_type: str, fields: dict, *, evidence_ids: list[str],
           observed_at: datetime | None, provider: str, limitations: list[str] | None = None) -> list[Relationship]:
    """Build whatever entities and relationships one observation supports, and nothing else.

    An observation type with no handler — a network classification, a threat-intelligence hit, a lookup error —
    is stored as evidence against the case by the caller and creates no relationship. That is deliberate: the
    classification of an address is a property of that address, not a link between two things.
    """
    handler = _HANDLERS.get(obs_type)
    if handler is None:
        return []
    return handler(db, case, fields or {}, list(evidence_ids), observed_at, provider, list(limitations or []))
