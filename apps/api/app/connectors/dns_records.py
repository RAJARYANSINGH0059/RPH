"""Current DNS record lookups across the record types an investigator actually needs.

The connector this replaces queried `A` and nothing else, while telling the investigator it covered A, AAAA and
CNAME. That is the kind of gap that makes a tool untrustworthy: the screen said DNS intelligence and the code
asked one question.

Two rules shape this module.

The first is that an absence of an answer is a finding with a name. A domain that exists but has no MX record
(`nodata`) is not the same as a domain that does not exist (`nxdomain`), and neither is the same as a resolver
that timed out. Collapsing the three into an empty list would let a reader conclude "no mail server" from what
was really a network failure, so each state is carried through and labelled.

The second is that nothing here is historical. A record read today describes today. The TTL bounds how long the
answer may be reused from the moment it was observed; it says nothing about what the name pointed at when the
victim's money moved. Every result carries that limitation with it.
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

DNS_MODULE_VERSION = "1.0.0"

# The record types the specification names, in the order an investigator reads them.
DOMAIN_RECORD_TYPES = ("A", "AAAA", "CNAME", "MX", "NS", "TXT")

# What a status means, for the UI and the report to quote rather than invent.
STATUS_MEANING = {
    "answered": "The resolver returned at least one record of this type.",
    "nodata": "The name exists, but it has no record of this type. This is an observation, not a missing lookup.",
    "nxdomain": "The resolver reports that this name does not exist at all.",
    "timeout": "The resolver did not answer in time. Nothing is known about this record type.",
    "no_nameservers": "No nameserver would answer for this name. Nothing is known about this record type.",
    "resolver_error": "The lookup failed for another reason, which is recorded. Nothing is known about this record type.",
    "not_queried": "This record type was not asked for.",
}

LIMITATIONS = [
    "current_lookup_not_historical",
    "dns_answer_describes_the_observation_time_only",
]


@dataclass
class RecordSet:
    """One record type asked of one name, with the answer or the reason there is none."""

    name: str
    record_type: str
    status: str
    values: list[dict] = field(default_factory=list)
    ttl: int | None = None
    resolver: str = ""
    error: str | None = None
    observed_at: datetime | None = None

    @property
    def answered(self) -> bool:
        return self.status == "answered"

    @property
    def valid_until(self) -> datetime | None:
        """The TTL bounds reuse of the answer from when it was observed. It is not a validity proof."""
        if self.observed_at is None or self.ttl is None or not self.answered:
            return None
        return self.observed_at + timedelta(seconds=int(self.ttl))

    def as_fields(self) -> dict:
        return {
            "name": self.name,
            "record": self.record_type,
            "status": self.status,
            "status_meaning": STATUS_MEANING.get(self.status, self.status),
            "values": self.values,
            "value_count": len(self.values),
            "ttl": self.ttl,
            "resolver": self.resolver,
            "error": self.error,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "module_version": DNS_MODULE_VERSION,
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _classify(ip: str) -> str:
    from app.parsers.indicators import ip_classification

    return ip_classification(ip)


def _values_for(record_type: str, rrset) -> list[dict]:
    """Turn a resolver answer into typed values, keeping the original text of each record.

    Each record type expresses a different relation, so each is read on its own terms rather than flattened into
    a list of strings: an MX record carries a preference, a TXT record carries several strings that must not be
    concatenated, and an address record carries an address whose range matters.
    """
    out: list[dict] = []
    for rr in rrset:
        text = rr.to_text()
        if record_type in {"A", "AAAA"}:
            ip = text.strip()
            out.append({"ip": ip, "classification": _classify(ip),
                        "family": "ipv6" if record_type == "AAAA" else "ipv4", "raw": text})
        elif record_type == "MX":
            out.append({"preference": getattr(rr, "preference", None),
                        "exchange": str(getattr(rr, "exchange", "")).rstrip(".").lower() or None, "raw": text})
        elif record_type == "NS":
            out.append({"nameserver": str(getattr(rr, "target", "")).rstrip(".").lower() or text.rstrip(".").lower(), "raw": text})
        elif record_type == "CNAME":
            out.append({"target": str(getattr(rr, "target", "")).rstrip(".").lower() or text.rstrip(".").lower(), "raw": text})
        elif record_type == "TXT":
            # A TXT record is a sequence of strings. Joining them would change the record, and some carry
            # provider verification tokens that a reader may need to match character for character.
            strings = [s.decode("utf-8", "replace") if isinstance(s, bytes) else str(s)
                       for s in getattr(rr, "strings", [])] or [text.strip('"')]
            out.append({"strings": strings, "joined": "".join(strings), "raw": text})
        elif record_type == "PTR":
            out.append({"hostname": str(getattr(rr, "target", "")).rstrip(".").lower() or text.rstrip(".").lower(), "raw": text})
        else:
            out.append({"raw": text})
    return out


def _resolver(timeout: float):
    import dns.resolver

    r = dns.resolver.Resolver()
    r.lifetime = timeout
    r.timeout = timeout
    return r


def _resolver_label(r) -> str:
    """Which resolver answered. An answer with no attributable resolver is not auditable."""
    servers = list(getattr(r, "nameservers", []) or [])
    return ", ".join(str(s) for s in servers[:3]) or "system"


def query(name: str, record_type: str, timeout: float = 6.0) -> RecordSet:
    """Ask one record type of one name, and name the reason when there is no answer."""
    import dns.resolver

    r = _resolver(timeout)
    label = _resolver_label(r)
    started = _now()
    try:
        ans = r.resolve(name, record_type, lifetime=timeout)
    except dns.resolver.NoAnswer:
        return RecordSet(name, record_type, "nodata", resolver=label, observed_at=started)
    except dns.resolver.NXDOMAIN:
        return RecordSet(name, record_type, "nxdomain", resolver=label, observed_at=started)
    except dns.resolver.NoNameservers as exc:
        return RecordSet(name, record_type, "no_nameservers", resolver=label, error=str(exc)[:200], observed_at=started)
    except dns.exception.Timeout as exc:
        return RecordSet(name, record_type, "timeout", resolver=label, error=str(exc)[:200], observed_at=started)
    except Exception as exc:  # a resolver can fail in ways dnspython does not model; record it rather than hide it
        return RecordSet(name, record_type, "resolver_error", resolver=label,
                         error=f"{type(exc).__name__}: {str(exc)[:160]}", observed_at=started)
    rrset = ans.rrset
    return RecordSet(name, record_type, "answered", _values_for(record_type, ans),
                     ttl=getattr(rrset, "ttl", None) if rrset is not None else None,
                     resolver=label, observed_at=started)


def query_domain(name: str, timeout: float = 6.0, record_types: tuple[str, ...] = DOMAIN_RECORD_TYPES) -> list[RecordSet]:
    """Every requested record type for one name, including the types that returned nothing."""
    clean = (name or "").strip().rstrip(".").lower()
    if not clean:
        return []
    return [query(clean, rt, timeout) for rt in record_types]


def reverse_name(ip: str) -> str | None:
    """The in-addr.arpa / ip6.arpa name for an address, for both families."""
    try:
        import dns.reversename

        return str(dns.reversename.from_address(ip))
    except Exception:
        return None


def query_ptr(ip: str, timeout: float = 6.0) -> RecordSet | None:
    """Reverse DNS for an address. A PTR name is chosen by whoever controls the address block, so it is a claim
    about the network's own labelling and not evidence of who used the address."""
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return None
    arpa = reverse_name(ip)
    if arpa is None:
        return None
    rs = query(arpa, "PTR", timeout)
    rs.values = [{**v, "ip": ip} for v in rs.values]
    return rs
