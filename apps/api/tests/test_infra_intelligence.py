"""Domain, DNS, address, certificate and historical infrastructure intelligence.

These tests pin the things that make infrastructure evidence safe to act on, which is mostly about refusing to
say more than the record says:

- every requested record type is reported, including the ones that returned nothing, and each no-answer
  condition keeps its own name rather than collapsing into an empty list;
- a record becomes the relationship it actually means, so a nameserver does not arrive as a resolution and a
  mail exchanger does not arrive as a host;
- shared addresses, nameservers, autonomous systems, registrars and certificates stay candidate links and never
  become a finding of common ownership;
- a name found in a certificate is a lead, not an observed service;
- a current lookup never becomes historical evidence, and a dated observation keeps its own window;
- the address checks hold for hosts that come from the IANA registry and for every redirect hop;
- reserved and documentation ranges, which is where the synthetic fixtures live, are never looked up at all.
"""
from __future__ import annotations

import ipaddress
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.connectors import certs, dns_records, rdap_bootstrap
from app.connectors.adapters import get_registry, is_lookupable_ip, is_reserved_name
from app.connectors.base import SafeHttp, assert_public_host, assert_safe_url
from app.parsers import indicators, technical_json


# ------------------------------------------------------------------------------- fake resolver

class _RR:
    def __init__(self, text, **kw):
        self._text = text
        for k, v in kw.items():
            setattr(self, k, v)

    def to_text(self):
        return self._text


class _RRSet(list):
    def __init__(self, items, ttl):
        super().__init__(items)
        self.ttl = ttl


class _Answer:
    def __init__(self, items, ttl=300):
        self.rrset = _RRSet(items, ttl)

    def __iter__(self):
        return iter(self.rrset)


class _FakeResolver:
    """Stands in for the system resolver so the record logic is tested without touching a network."""

    nameservers = ["192.0.2.53"]

    def __init__(self, behaviour):
        self.behaviour = behaviour

    def resolve(self, name, rtype, lifetime=None):
        result = self.behaviour(name, rtype)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.fixture
def resolver(monkeypatch):
    def install(behaviour):
        monkeypatch.setattr(dns_records, "_resolver", lambda timeout: _FakeResolver(behaviour))
    return install


# ------------------------------------------------------------------------------- DNS record types

def test_every_record_type_is_read_on_its_own_terms(resolver):
    """An MX record carries a preference and a TXT record carries several strings. Flattening either into a list
    of addresses would change what the record says."""
    answers = {
        "A": _Answer([_RR("203.0.113.9")], 120),
        "AAAA": _Answer([_RR("2001:db8::9")], 120),
        "CNAME": _Answer([_RR("target.example.", target="target.example.")], 60),
        "MX": _Answer([_RR("10 mail.example.", preference=10, exchange="mail.example.")], 3600),
        "NS": _Answer([_RR("ns1.example.", target="ns1.example.")], 86400),
        "TXT": _Answer([_RR('"v=spf1 -all" "extra"', strings=[b"v=spf1 -all", b"extra"])], 300),
    }
    resolver(lambda name, rtype: answers[rtype])
    sets = {rs.record_type: rs for rs in dns_records.query_domain("pay.example")}
    assert set(sets) == set(dns_records.DOMAIN_RECORD_TYPES)
    assert sets["A"].values[0]["ip"] == "203.0.113.9" and sets["A"].values[0]["family"] == "ipv4"
    assert sets["AAAA"].values[0]["family"] == "ipv6"
    assert sets["CNAME"].values[0]["target"] == "target.example"
    assert sets["MX"].values[0] == {"preference": 10, "exchange": "mail.example", "raw": "10 mail.example."}
    assert sets["NS"].values[0]["nameserver"] == "ns1.example"
    assert sets["TXT"].values[0]["strings"] == ["v=spf1 -all", "extra"], "multiple TXT strings must not be joined away"


def test_each_reason_for_no_answer_keeps_its_own_name(resolver):
    """`no MX record` and `the resolver timed out` must never look the same to a reader."""
    import dns.exception
    import dns.resolver

    cases = {
        "MX": dns.resolver.NoAnswer(),
        "NS": dns.resolver.NXDOMAIN(),
        "TXT": dns.exception.Timeout(),
        "CNAME": dns.resolver.NoNameservers(),
        "AAAA": RuntimeError("resolver exploded"),
        "A": _Answer([_RR("203.0.113.9")], 60),
    }
    resolver(lambda name, rtype: cases[rtype])
    got = {rs.record_type: rs.status for rs in dns_records.query_domain("pay.example")}
    assert got == {"A": "answered", "AAAA": "resolver_error", "CNAME": "no_nameservers",
                   "MX": "nodata", "NS": "nxdomain", "TXT": "timeout"}
    for rs in dns_records.query_domain("pay.example"):
        assert dns_records.STATUS_MEANING[rs.status], "every status must carry a meaning the UI can quote"
        assert not rs.answered or rs.values


def test_a_ttl_bounds_reuse_from_the_observation_and_is_not_a_validity_proof(resolver):
    resolver(lambda name, rtype: _Answer([_RR("203.0.113.9")], 900))
    rs = dns_records.query("pay.example", "A")
    assert rs.valid_until is not None
    assert rs.valid_until - rs.observed_at == timedelta(seconds=900)
    assert "current_lookup_not_historical" in dns_records.LIMITATIONS


def test_a_record_that_did_not_answer_has_no_validity_window(resolver):
    import dns.resolver

    resolver(lambda name, rtype: dns.resolver.NoAnswer())
    assert dns_records.query("pay.example", "MX").valid_until is None


def test_reverse_lookup_works_for_both_address_families(resolver):
    resolver(lambda name, rtype: _Answer([_RR("host.example.", target="host.example.")], 300))
    v4 = dns_records.query_ptr("203.0.113.9")
    v6 = dns_records.query_ptr("2001:db8::9")
    assert v4 and v4.record_type == "PTR" and v4.values[0]["ip"] == "203.0.113.9"
    assert v6 and v6.values[0]["hostname"] == "host.example"
    assert dns_records.reverse_name("203.0.113.9").endswith("in-addr.arpa.")
    assert dns_records.reverse_name("2001:db8::9").endswith("ip6.arpa.")
    assert dns_records.query_ptr("not-an-address") is None


# ------------------------------------------------------------------------------- RDAP bootstrap

BOOTSTRAP_DNS = {"services": [[["com", "net"], ["https://rdap.verisign.example/com/v1/"]],
                              [["co.uk"], ["https://rdap.nominet.example/"]],
                              [["uk"], ["https://rdap.uk.example/"]]]}
BOOTSTRAP_V4 = {"services": [[["203.0.0.0/8"], ["https://rdap.apnic.example/"]],
                             [["203.0.113.0/24"], ["https://rdap.specific.example/"]]]}


def test_the_authoritative_server_is_chosen_by_the_longest_matching_suffix():
    assert rdap_bootstrap.domain_service(BOOTSTRAP_DNS, "shop.example.com").startswith("https://rdap.verisign")
    assert rdap_bootstrap.domain_service(BOOTSTRAP_DNS, "a.b.co.uk").startswith("https://rdap.nominet")
    assert rdap_bootstrap.domain_service(BOOTSTRAP_DNS, "thing.uk").startswith("https://rdap.uk")
    assert rdap_bootstrap.domain_service(BOOTSTRAP_DNS, "thing.invalidtld") is None


def test_the_registry_for_an_address_is_the_most_specific_block_that_contains_it():
    assert rdap_bootstrap.ip_service(BOOTSTRAP_V4, "203.0.113.9") == "https://rdap.specific.example/"
    assert rdap_bootstrap.ip_service(BOOTSTRAP_V4, "203.4.5.6") == "https://rdap.apnic.example/"
    assert rdap_bootstrap.ip_service(BOOTSTRAP_V4, "198.51.100.1") is None
    assert rdap_bootstrap.ip_service(BOOTSTRAP_V4, "not-an-address") is None


DOMAIN_RESPONSE = {
    "ldhName": "PAY-REFUND.EXAMPLE",
    "handle": "D123-EXAMPLE",
    "status": ["client transfer prohibited"],
    "events": [{"eventAction": "registration", "eventDate": "2026-04-01T10:00:00Z"},
               {"eventAction": "expiration", "eventDate": "2027-04-01T10:00:00Z"},
               {"eventAction": "last changed", "eventDate": "2026-04-20T10:00:00Z"}],
    "nameservers": [{"ldhName": "NS1.HOSTING.EXAMPLE."}, {"ldhName": "ns2.hosting.example"}],
    "entities": [{"roles": ["registrar"], "handle": "REG-99",
                  "publicIds": [{"type": "IANA Registrar ID", "identifier": "1234"}],
                  "vcardArray": ["vcard", [["version", {}, "text", "4.0"], ["fn", {}, "text", "Example Registrar Ltd"]]]},
                 {"roles": ["registrant"], "vcardArray": ["vcard", [["version", {}, "text", "4.0"]]]}],
    "secureDNS": {"delegationSigned": False},
}


def test_registration_expiry_and_registrar_identity_are_extracted_when_present():
    f = rdap_bootstrap.domain_fields(DOMAIN_RESPONSE)
    assert f["domain"] == "pay-refund.example"
    assert f["registered"] == "2026-04-01T10:00:00Z"
    assert f["expires"] == "2027-04-01T10:00:00Z", "expiry is the field the old connector never extracted"
    assert f["last_changed"] == "2026-04-20T10:00:00Z"
    assert f["registrar_name"] == "Example Registrar Ltd"
    assert f["registrar_iana_id"] == "1234"
    assert f["nameservers"] == ["ns1.hosting.example", "ns2.hosting.example"]


def test_a_withheld_registrant_is_reported_as_withheld_and_never_filled_in():
    f = rdap_bootstrap.domain_fields(DOMAIN_RESPONSE)
    assert f["registrant_disclosed"] is False
    assert f["registrant_name"] is None
    assert "withheld" in f["redaction"]
    assert f["reseller"] is None, "a reseller is reported only where the registry supplies one"


def test_a_field_the_registry_does_not_supply_stays_absent():
    f = rdap_bootstrap.domain_fields({"ldhName": "bare.example"})
    assert f["registrar_name"] is None and f["expires"] is None and f["registered"] is None
    assert f["nameservers"] == []


def test_address_allocation_describes_the_network_holder():
    f = rdap_bootstrap.ip_fields({
        "handle": "NET-203-0-113-0-1", "startAddress": "203.0.113.0", "endAddress": "203.0.113.255",
        "name": "EXAMPLE-HOSTING", "type": "ALLOCATION", "country": "IN", "ipVersion": "v4",
        "events": [{"eventAction": "registration", "eventDate": "2020-01-01T00:00:00Z"}],
        "entities": [{"roles": ["registrant"], "handle": "ORG-EX",
                      "vcardArray": ["vcard", [["version", {}, "text", "4.0"], ["fn", {}, "text", "Example Hosting Pvt Ltd"]]]}],
    })
    assert f["prefix"] == "203.0.113.0/24"
    assert f["organisation"] == "Example Hosting Pvt Ltd"
    assert f["network_name"] == "EXAMPLE-HOSTING"
    assert f["allocated"] == "2020-01-01T00:00:00Z"
    assert "not_the_person_using_an_address" in " ".join(rdap_bootstrap.IP_LIMITATIONS)


# ------------------------------------------------------------------------------- outbound safety

def test_a_registry_named_host_still_has_to_resolve_to_a_public_address():
    """The bootstrap registry replaces the fixed allowlist, not the address checks."""
    with pytest.raises(ValueError):
        assert_public_host("localhost")
    with pytest.raises(ValueError):
        assert_safe_url("https://evil.example/rdap", {"data.iana.org"})
    with pytest.raises(ValueError):
        assert_safe_url("http://data.iana.org/rdap/dns.json", {"data.iana.org"})


def test_a_redirect_towards_a_private_address_is_refused_at_that_hop(monkeypatch):
    import httpx

    http = SafeHttp({"start.example"})
    http.min_interval = 0

    class _Resp:
        status_code = 302
        headers = {"location": "https://127.0.0.1/secrets"}
        content = b""

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def request(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    monkeypatch.setattr("app.connectors.base.assert_public_host", lambda host: None if host == "start.example" else (_ for _ in ()).throw(ValueError("blocked")))
    with pytest.raises(ValueError):
        http.request_raw("https://start.example/x", any_public_host=True, max_redirects=2)


def test_a_redirect_chain_is_capped(monkeypatch):
    import httpx

    http = SafeHttp(set())
    http.min_interval = 0
    hops = {"n": 0}

    class _Resp:
        status_code = 302
        content = b""

        @property
        def headers(self):
            hops["n"] += 1
            return {"location": f"https://host{hops['n']}.example/next"}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def request(self, *a, **k):
            return _Resp()

    monkeypatch.setattr(httpx, "Client", _Client)
    monkeypatch.setattr("app.connectors.base.assert_public_host", lambda host: None)
    with pytest.raises(ValueError, match="Redirect limit"):
        http.request_raw("https://host0.example/x", any_public_host=True, max_redirects=2)


# ------------------------------------------------------------------------------- certificates

CT_PAYLOAD = [
    {"id": 111, "issuer_name": "C=US, O=Test CA", "common_name": "pay-refund.example",
     "name_value": "pay-refund.example\nwww.pay-refund.example\n*.cdn.pay-refund.example",
     "not_before": "2026-04-01T00:00:00", "not_after": "2026-07-01T00:00:00",
     "serial_number": "0abc", "entry_timestamp": "2026-04-01T06:00:00"},
    {"id": 222, "issuer_name": "C=US, O=Platform CA", "common_name": "shared-platform.example",
     "name_value": "shared-platform.example\npay-refund.example\nunrelated-shop.example",
     "not_before": "2026-01-01T00:00:00", "not_after": "2026-02-01T00:00:00",
     "serial_number": "0def", "entry_timestamp": "2026-01-01T06:00:00"},
]


def test_certificate_entries_keep_their_own_names_and_identifiers():
    found = certs.parse_entries(CT_PAYLOAD, "pay-refund.example")
    assert len(found) == 2
    first = found[0]
    assert first.key == "crtsh:111"
    assert "www.pay-refund.example" in first.san_names
    assert first.as_fields()["fingerprint"] is None, "this source supplies no fingerprint, so none is invented"
    assert "does not supply a SHA-256 fingerprint" in first.as_fields()["fingerprint_note"]


def test_expiry_is_read_from_the_certificates_own_window():
    found = certs.parse_entries(CT_PAYLOAD, "pay-refund.example")
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    assert found[0].validity_state(now) == "within_validity_window"
    assert found[1].validity_state(now) == "expired"
    assert certs.Certificate(None, None, None, []).validity_state(now) == "validity_not_supplied"


def test_a_name_from_a_certificate_is_a_lead_and_a_wildcard_stays_a_wildcard():
    found = certs.parse_entries(CT_PAYLOAD, "pay-refund.example")
    names = certs.discovered_names(found, "pay-refund.example")
    by_name = {n["name"]: n for n in names}
    assert "www.pay-refund.example" in by_name
    assert by_name["*.cdn.pay-refund.example"]["is_wildcard"] is True, "a wildcard must not be expanded into names nobody saw"
    assert all(n["status"] == "discovered_name_not_confirmed_active" for n in names)
    assert "unrelated-shop.example" not in by_name, "a name outside the domain is not one of its subdomains"


def test_names_sharing_a_certificate_are_candidates_with_the_ordinary_explanation():
    found = certs.parse_entries(CT_PAYLOAD, "pay-refund.example")
    related = certs.related_names(found, "pay-refund.example")
    names = {r["name"] for r in related}
    assert {"shared-platform.example", "unrelated-shop.example"} <= names
    for r in related:
        assert r["evidence_level"] == "candidate"
        assert any("CDN" in a or "platform" in a for a in r["alternatives"])
    assert "shared_operator" in " ".join(certs.LIMITATIONS).replace("-", "_")


# ------------------------------------------------------------------------------- addresses

def test_both_address_families_are_extracted_from_free_text():
    text = ("Victim paid via http://pay-refund.example from 2001:db8::dead:beef, "
            "the portal logged [2001:db8:1234::1]:8443 and 203.0.113.9 at 09:30 on 2026-05-01. Ratio 1:2:3.")
    ips = {i.value for i in indicators.extract_indicators(text) if i.kind == "ip"}
    assert "203.0.113.9" in ips
    assert "2001:db8::dead:beef" in ips
    assert "2001:db8:1234::1" in ips, "an address in brackets with a port must still be recognised"
    assert not any(v in ips for v in ("09:30", "1:2:3")), "a time or a ratio is not an address"


def test_the_narrower_address_category_wins():
    """A link-local address is also private, so testing private first made the narrower label unreachable."""
    assert indicators.ip_classification("fe80::1") == "link_local"
    assert indicators.ip_classification("169.254.1.1") == "link_local"
    assert indicators.ip_classification("127.0.0.1") == "loopback"
    assert indicators.ip_classification("::1") == "loopback"
    assert indicators.ip_classification("10.0.0.1") == "private"
    assert indicators.ip_classification("224.0.0.1") == "multicast"
    assert indicators.ip_classification("169.254.169.254") == "metadata"


def test_documentation_ranges_of_both_families_are_recognised_and_never_looked_up():
    assert indicators.ip_classification("203.0.113.9") == "documentation"
    assert indicators.ip_classification("2001:db8::1") == "documentation"
    assert not is_lookupable_ip("203.0.113.9") and not is_lookupable_ip("2001:db8::1")
    assert is_lookupable_ip("8.8.8.8") and is_lookupable_ip("2606:4700::1111")


def test_reserved_names_are_never_looked_up():
    """The synthetic case factory uses these deliberately; a lookup would leak a fixture onto a real resolver."""
    for name in ("victim-bank.test", "pay-refund.example", "thing.invalid", "host.localhost", "example.com"):
        assert is_reserved_name(name), name
    assert not is_reserved_name("pay-refund.co")


# ------------------------------------------------------------------------------- connector states

def test_no_provider_claims_to_be_live_without_a_successful_request():
    states = {name: c.status().status for name, c in get_registry().items()}
    assert states["synthetic_mock"] == "mock"
    for name, status in states.items():
        if name != "synthetic_mock":
            assert status in {"not_configured", "configured", "unavailable"}, f"{name} reports {status}"
            assert status != "live"


def test_every_connector_the_specification_names_is_present():
    names = set(get_registry())
    assert {"rdap", "ip_rdap", "dns", "certificate_transparency", "passive_dns",
            "network_classification"} <= names


def test_an_unconfigured_provider_says_what_configuring_it_would_take():
    reg = get_registry()
    for name in ("passive_dns", "certificate_transparency", "network_classification", "ip_rdap"):
        hint = reg[name].status().detail
        assert hint and len(hint) > 20, f"{name} gives no hint"
    assert "PASSIVE_DNS_URL" in reg["passive_dns"].status().detail
    assert "nothing is\n" not in reg["passive_dns"].status().detail  # hint is one readable line
    assert "no VPN or proxy provider is configured" in reg["network_classification"].status().detail.lower() or \
           "vpn or proxy" in reg["network_classification"].status().detail.lower()


# ------------------------------------------------------------------------------- the graph mapping

@pytest.fixture(scope="module")
def infra_case(client, analyst):
    r = client.post("/api/cases", json={"title": "Infrastructure intelligence",
                                        "summary": "Supplied domain, DNS, address, certificate and dated historical observations."},
                    headers=analyst)
    assert r.status_code == 201, r.text[:300]
    return r.json()["id"]


OBSERVATIONS = {"observations": [
    {"type": "dns", "domain": "pay-refund.example", "ip": "203.0.113.9", "ttl": 300,
     "observed_at": "2026-05-02T10:00:00Z", "source": "current lookup", "resolver": "198.51.100.53"},
    {"type": "dns", "domain": "pay-refund.example", "record": "MX", "value": "mail.hosting.example",
     "observed_at": "2026-05-02T10:00:00Z", "source": "current lookup"},
    {"type": "dns", "domain": "pay-refund.example", "record": "NS", "value": "ns1.hosting.example",
     "observed_at": "2026-05-02T10:00:00Z", "source": "current lookup"},
    {"type": "dns", "domain": "pay-refund.example", "record": "CNAME", "value": "edge.cdn.example",
     "observed_at": "2026-05-02T10:00:00Z", "source": "current lookup"},
    {"type": "dns", "domain": "pay-refund.example", "record": "TXT", "value": "v=spf1 -all",
     "observed_at": "2026-05-02T10:00:00Z", "source": "current lookup"},
    {"type": "ptr", "ip": "203.0.113.9", "hostname": "host9.hosting.example",
     "observed_at": "2026-05-02T10:00:00Z", "source": "current lookup"},
    {"type": "asn", "ip": "203.0.113.9", "asn": "AS64500", "organisation": "Example Hosting Pvt Ltd",
     "prefix": "203.0.113.0/24", "country": "IN", "observed_at": "2026-05-02T10:00:00Z"},
    {"type": "certificate", "domain": "pay-refund.example", "certificate_key": "sha256:aa11",
     "issuer": "Test CA", "not_before": "2026-04-01T00:00:00Z", "not_after": "2026-07-01T00:00:00Z",
     "san_names": ["pay-refund.example", "login.pay-refund.example"], "observed_at": "2026-05-02T10:00:00Z"},
    {"type": "subdomain", "parent": "pay-refund.example", "names": ["login.pay-refund.example"],
     "source": "supplied", "observed_at": "2026-05-02T10:00:00Z"},
    {"type": "historical_dns", "domain": "pay-refund.example", "ip": "198.51.100.7",
     "first_seen": "2026-04-28T00:00:00Z", "last_seen": "2026-05-05T00:00:00Z",
     "source": "supplied dated record", "observed_at": "2026-05-10T00:00:00Z"},
]}


@pytest.fixture(scope="module")
def uploaded(client, analyst, infra_case):
    body = json.dumps(OBSERVATIONS).encode()
    r = client.post(f"/api/cases/{infra_case}/upload",
                    files={"files": ("technical_observations.json", body, "application/json")}, headers=analyst)
    assert r.status_code in (200, 201), r.text[:400]
    return r.json()


def _rels(client, analyst, case_id):
    g = client.get(f"/api/cases/{case_id}/graph", headers=analyst).json()
    return g["edges"], {n["id"]: n for n in g["nodes"]}


def test_each_record_type_becomes_the_relationship_it_actually_means(client, analyst, infra_case, uploaded):
    edges, _ = _rels(client, analyst, infra_case)
    kinds = {e["type"] for e in edges}
    assert "RESOLVES_TO" in kinds, "an address record is a resolution"
    assert "MAIL_EXCHANGE" in kinds, "a mail exchanger must not arrive as a resolution"
    assert "USES_NAMESERVER" in kinds, "a nameserver must not arrive as a resolution"
    assert "ALIAS_OF" in kinds, "a CNAME is an alias"
    assert "REVERSE_DNS" in kinds, "a PTR name belongs to the address, not the domain"
    assert "ALLOCATED_TO" in kinds and "ANNOUNCED_BY" in kinds
    assert "NAMED_IN_CERTIFICATE" in kinds
    assert "HAS_SUBDOMAIN" in kinds


def test_a_text_record_names_no_second_entity(client, analyst, infra_case, uploaded):
    """A TXT record is evidence about the domain. Turning it into an edge would invent a relationship."""
    edges, nodes = _rels(client, analyst, infra_case)
    assert not any("spf1" in str(n.get("label", "")) for n in nodes.values())
    assert dns_records.LIMITATIONS, "limitations are attached to every DNS observation"


def test_a_discovered_name_is_a_candidate_not_an_observation(client, analyst, infra_case, uploaded):
    edges, _ = _rels(client, analyst, infra_case)
    subs = [e for e in edges if e["type"] == "HAS_SUBDOMAIN"]
    assert subs
    for e in subs:
        assert e["evidence_level"] == "candidate", "a certified name is a lead, not an observed service"


def test_shared_infrastructure_never_becomes_a_common_operator_finding(client, analyst, infra_case, uploaded):
    edges, _ = _rels(client, analyst, infra_case)
    assert not [e for e in edges if e["type"] in {"COMMON_OPERATOR", "COMMON_OWNER"}]


def test_a_dated_historical_observation_keeps_its_own_window(client, analyst, infra_case, uploaded):
    """The whole point of supplying history: its window must be the provider's dates, not today."""
    body = client.get(f"/api/cases/{infra_case}/infrastructure", headers=analyst).json()
    hist = body["historical_observations"]
    assert hist, "a supplied dated record must appear as historical"
    rows = [r for h in hist for r in h["records"]]
    assert any(r["first_seen"] == "2026-04-28T00:00:00Z" and r["last_seen"] == "2026-05-05T00:00:00Z" for r in rows)
    assert body["coverage_summary"]["historical_observation_sources"] >= 1


def test_a_current_lookup_is_never_presented_as_historical(client, analyst, infra_case, uploaded):
    body = client.get(f"/api/cases/{infra_case}/infrastructure", headers=analyst).json()
    joined = " ".join(body["limitations"]).lower()
    assert "not evidence of what a name pointed at when the money moved" in joined
    for d in body["domains"]:
        for record, rows in d["records"].items():
            for row in rows:
                assert row.get("valid_until") is None or row["observed_at"] is not None


# ------------------------------------------------------------------------------- the infrastructure view

def test_the_view_reports_which_record_types_were_asked_and_which_were_not(client, analyst, infra_case, uploaded):
    body = client.get(f"/api/cases/{infra_case}/infrastructure", headers=analyst).json()
    d = next(d for d in body["domains"] if d["domain"] == "pay-refund.example")
    assert set(d["record_types_answered"]) >= {"MX", "NS", "CNAME", "TXT"}
    assert "AAAA" in d["record_types_not_asked"], "a record type nobody asked for must not read as absent"
    assert d["coverage"] in {"partial", "complete", "none"}
    assert d["mail_exchangers"] == ["mail.hosting.example"]
    assert d["nameservers"] == ["ns1.hosting.example"]


def test_the_view_files_reverse_dns_and_allocation_against_the_address(client, analyst, infra_case, uploaded):
    body = client.get(f"/api/cases/{infra_case}/infrastructure", headers=analyst).json()
    a = next(a for a in body["addresses"] if a["ip"] == "203.0.113.9")
    assert a["reverse_dns"]["hostname"] == "host9.hosting.example"
    assert a["allocation"]["organisation"] == "Example Hosting Pvt Ltd"
    assert a["classification"] == "documentation"
    assert a["family"] == "ipv4"


def test_the_view_names_the_providers_that_are_not_configured(client, analyst, infra_case, uploaded):
    body = client.get(f"/api/cases/{infra_case}/infrastructure", headers=analyst).json()
    not_configured = body["coverage_summary"]["providers_not_configured"]
    assert "passive_dns" in not_configured
    assert body["connectors"]["passive_dns"]["status"] == "not_configured"
    assert not any(c["status"] == "live" for c in body["connectors"].values())


def test_the_view_states_what_shared_infrastructure_does_not_establish(client, analyst, infra_case, uploaded):
    body = client.get(f"/api/cases/{infra_case}/infrastructure", headers=analyst).json()
    joined = " ".join(body["limitations"]).lower()
    assert "candidate links only" in joined and "common ownership" in joined
    assert "ptr name is published by whoever holds the address block" in joined
    assert "never the subscriber and never a person" in joined


def test_another_members_case_cannot_be_read_through_this_route(client, supervisor, infra_case):
    assert client.get(f"/api/cases/{infra_case}/infrastructure", headers=supervisor).status_code == 404


def test_a_case_with_no_infrastructure_evidence_reports_nothing_rather_than_guessing(client, analyst):
    case = client.post("/api/cases", json={"title": "Empty infrastructure", "summary": "No observations supplied."},
                       headers=analyst).json()["id"]
    body = client.get(f"/api/cases/{case}/infrastructure", headers=analyst).json()
    assert body["domains"] == [] and body["addresses"] == []
    assert body["coverage_summary"]["domains"] == 0
    assert body["limitations"], "an empty case still states what the evidence cannot show"

# ------------------------------------------------------------------------------- the connector field merge

class _FakeHttp:
    """Answers the bootstrap registry and then the authoritative server, without a network."""

    def __init__(self, bootstrap, body):
        self.bootstrap = bootstrap
        self.body = body
        self.urls = []

    def get_json(self, url, headers=None, method="GET", data=None, **kw):
        self.urls.append(url)
        if url.startswith(rdap_bootstrap.BOOTSTRAP["domain"]) or "/rdap/dns.json" in url:
            return self.bootstrap
        if "/rdap/ipv4.json" in url or "/rdap/ipv6.json" in url:
            return self.bootstrap
        return self.body


def test_a_successful_lookup_still_reads_as_answered_after_the_fields_are_merged(monkeypatch):
    """The registry's own status array must not overwrite the word that says the lookup succeeded.

    Both live under `status` in RDAP: a domain carries `clientTransferProhibited` and friends, and the connector
    also records whether the lookup itself answered. Merging them under one key let the array win, so a
    successful lookup would have produced no registrar relationship at all.
    """
    from app.connectors.adapters import RdapConnector

    c = RdapConnector()
    monkeypatch.setattr(c, "enabled", lambda: True)
    c.http = _FakeHttp(BOOTSTRAP_DNS, DOMAIN_RESPONSE)

    obs = c._fetch_one("domain", "shop.example.com")
    assert len(obs) == 1
    f = obs[0].fields
    assert f["status"] == "answered", "the lookup status must survive the merge"
    assert f["registry_status"] == ["client transfer prohibited"], "the registry array keeps its own name"
    assert f["registrar_iana_id"] == "1234" and f["expires"] == "2027-04-01T10:00:00Z"
    assert any("rdap.verisign.example" in u for u in c.http.urls), "the authoritative server must be asked directly"


def test_an_address_lookup_merges_the_same_way(monkeypatch):
    from app.connectors.adapters import IpRdapConnector

    c = IpRdapConnector()
    monkeypatch.setattr(c, "enabled", lambda: True)
    # 203.0.113.0/24 is a documentation range and is never looked up, so this bootstrap covers a public block.
    c.http = _FakeHttp({"services": [[["8.0.0.0/8"], ["https://rdap.arin.example/"]]]}, {
        "handle": "NET-1", "startAddress": "203.0.113.0", "endAddress": "203.0.113.255",
        "name": "EXAMPLE-HOSTING", "status": ["active"], "country": "IN",
        "entities": [{"roles": ["registrant"], "vcardArray": ["vcard", [["fn", {}, "text", "Example Hosting"]]]}],
    })
    obs = c._fetch_one("ip", "8.8.8.8")
    assert len(obs) == 1
    f = obs[0].fields
    assert f["status"] == "answered"
    assert f["registry_status"] == ["active"]
    assert f["organisation"] == "Example Hosting"


def test_a_lookup_that_fails_says_so_and_builds_nothing(monkeypatch):
    from app.connectors.adapters import RdapConnector
    from app.services import infra_graph

    class _Broken(_FakeHttp):
        def get_json(self, url, headers=None, method="GET", data=None, **kw):
            if "/rdap/dns.json" in url:
                return self.bootstrap
            raise RuntimeError("404 not found")

    c = RdapConnector()
    monkeypatch.setattr(c, "enabled", lambda: True)
    c.http = _Broken(BOOTSTRAP_DNS, {})
    f = c._fetch_one("domain", "shop.example.com")[0].fields
    assert f["status"] in {"not_found", "lookup_failed"}
    assert "registration_fields_unknown_for_this_domain" in c._fetch_one("domain", "shop.example.com")[0].limitations
    assert infra_graph._from_rdap(None, None, f, [], None, "p", []) == [], "a failed lookup must create no relationship"
