"""Concrete adapters: RDAP (current registration), DNS (current resolution), URLhaus/ThreatFox (key-gated), MISP (interface)."""
from __future__ import annotations

from app.core.config import get_settings
from app.connectors import certs, dns_records, rdap_bootstrap
from app.connectors.base import ConnectorHealth, ExternalObservation, SafeHttp, is_blocked_ip, now_utc

# Reserved names exist so that examples and tests never reach a real service. The synthetic case factory uses
# them deliberately, so looking one up would be useless and would leak a fixture onto someone else's resolver.
RESERVED_SUFFIXES = (".test", ".example", ".invalid", ".localhost", ".local")


def is_reserved_name(value: str) -> bool:
    name = (value or "").strip().rstrip(".").lower()
    return name.endswith(RESERVED_SUFFIXES) or name in {"example.com", "example.net", "example.org"}


def is_lookupable_ip(value: str) -> bool:
    """Only public addresses are looked up. Documentation ranges carry synthetic fixtures and are left alone."""
    from app.parsers.indicators import ip_classification

    return ip_classification(value) == "public"


class _BaseConnector:
    name = "base"
    provider = ""
    allowed_hosts: set[str] = set()
    attribution = ""

    def __init__(self):
        self._health: ConnectorHealth | None = None
        self._live = False
        self.http = SafeHttp(self.allowed_hosts)

    def enabled(self) -> bool:
        return False

    def status(self) -> ConnectorHealth:
        if not self.enabled():
            return ConnectorHealth("not_configured", self.not_configured_hint(), now_utc())
        if self._live:
            return ConnectorHealth("live", "Authenticated/real request succeeded in this process", self._health.checked_at if self._health else now_utc())
        if self._health and self._health.status == "unavailable":
            return self._health
        return ConnectorHealth("configured", "Configured; no successful request yet", now_utc())

    def not_configured_hint(self) -> str:
        return "Disabled"

    def healthcheck(self) -> ConnectorHealth:
        if not self.enabled():
            return self.status()
        try:
            self._probe()
            self._live = True
            self._health = ConnectorHealth("live", "Probe succeeded", now_utc())
        except Exception as exc:
            self._health = ConnectorHealth("unavailable", f"{type(exc).__name__}: {str(exc)[:160]}", now_utc())
        return self._health

    def _probe(self) -> None:
        raise NotImplementedError

    def fetch(self, indicators: list[tuple[str, str]]) -> list[ExternalObservation]:
        if not self.enabled():
            return []
        out: list[ExternalObservation] = []
        for kind, value in indicators[:50]:
            try:
                out.extend(self._fetch_one(kind, value))
                self._live = True
            except Exception as exc:
                out.append(ExternalObservation("error", self.provider, {"indicator": value, "error": f"{type(exc).__name__}"}, now_utc(),
                                               attribution=self.attribution, limitations=["lookup_failed"]))
        return out

    def _fetch_one(self, kind: str, value: str) -> list[ExternalObservation]:
        return []


class RdapConnector(_BaseConnector):
    """Domain registration, read from the registry that is authoritative for the TLD."""

    name = "rdap"
    provider = "IANA RDAP bootstrap (RFC 7484), then the authoritative registry or registrar RDAP service"
    allowed_hosts = {rdap_bootstrap.BOOTSTRAP_HOST}
    attribution = ("RDAP registration data read from the server IANA names as authoritative. Current registration, "
                   "not historical ownership; registrant contact data is commonly withheld by the registry.")

    def __init__(self):
        super().__init__()
        self._bootstrap: dict = {}

    def enabled(self) -> bool:
        return get_settings().enable_rdap

    def not_configured_hint(self) -> str:
        return "Set ENABLE_RDAP=true to allow current registration lookups"

    def _probe(self) -> None:
        self.http.get_json(rdap_bootstrap.BOOTSTRAP["domain"])

    def _fetch_one(self, kind: str, value: str) -> list[ExternalObservation]:
        if kind != "domain" or is_reserved_name(value):
            return []
        res = rdap_bootstrap.lookup(self.http, value, "domain", bootstrap_cache=self._bootstrap)
        fields = {"domain": value, "status": res.status, "status_detail": res.error, **res.fields}
        limits = list(res.limitations)
        if not res.answered:
            limits.append("registration_fields_unknown_for_this_domain")
        return [ExternalObservation("rdap", self.provider, fields, res.observed_at or now_utc(),
                                    res.service_url, self.attribution, limits)]


class IpRdapConnector(_BaseConnector):
    """Address allocation from the regional internet registry that holds the block.

    This says who holds the network, which is not who used an address inside it. That distinction travels with
    the observation rather than being left to the reader to remember.
    """

    name = "ip_rdap"
    provider = "IANA RDAP bootstrap (RFC 7484), then the authoritative RIR RDAP service"
    allowed_hosts = {rdap_bootstrap.BOOTSTRAP_HOST}
    attribution = ("Address allocation from the responsible regional internet registry: the organisation holding "
                   "the network range, never the subscriber or the person using an address within it.")

    def __init__(self):
        super().__init__()
        self._bootstrap: dict = {}

    def enabled(self) -> bool:
        return get_settings().enable_rdap

    def not_configured_hint(self) -> str:
        return "Set ENABLE_RDAP=true to allow current address-allocation lookups"

    def _probe(self) -> None:
        self.http.get_json(rdap_bootstrap.BOOTSTRAP["ipv4"])

    def _fetch_one(self, kind: str, value: str) -> list[ExternalObservation]:
        if kind != "ip" or not is_lookupable_ip(value):
            return []
        res = rdap_bootstrap.lookup(self.http, value, "ip", bootstrap_cache=self._bootstrap)
        fields = {"ip": value, "status": res.status, "status_detail": res.error, **res.fields}
        limits = list(res.limitations)
        if not res.answered:
            limits.append("allocation_fields_unknown_for_this_address")
        return [ExternalObservation("ip_allocation", self.provider, fields, res.observed_at or now_utc(),
                                    res.service_url, self.attribution, limits)]


class DnsConnector(_BaseConnector):
    """Current DNS across every record type the specification names, and PTR for addresses."""

    name = "dns"
    provider = "System resolver (dnspython)"
    allowed_hosts: set[str] = set()
    attribution = ("Current answers from the configured resolver for A, AAAA, CNAME, MX, NS and TXT, and PTR for "
                   "addresses. This is live resolution, not passive or historical DNS.")

    def enabled(self) -> bool:
        return get_settings().enable_dns

    def not_configured_hint(self) -> str:
        return "Set ENABLE_DNS=true to allow current DNS lookups"

    def _probe(self) -> None:
        rs = dns_records.query("example.com", "A", get_settings().connector_timeout_seconds)
        if rs.status in {"timeout", "no_nameservers", "resolver_error"}:
            raise RuntimeError(f"resolver unavailable: {rs.status} {rs.error or chr(32)}".strip())

    def _fetch_one(self, kind: str, value: str) -> list[ExternalObservation]:
        timeout = get_settings().connector_timeout_seconds
        if kind == "domain":
            if is_reserved_name(value):
                return []
            sets = dns_records.query_domain(value, timeout)
        elif kind == "ip":
            if not is_lookupable_ip(value):
                return []
            ptr = dns_records.query_ptr(value, timeout)
            sets = [ptr] if ptr else []
        else:
            return []
        out: list[ExternalObservation] = []
        for rs in sets:
            # A record type that returned nothing is still reported. "This domain has no MX record" is an
            # observation; silence would read as a lookup nobody performed.
            out.append(ExternalObservation("dns_record", self.provider, rs.as_fields(),
                                           rs.observed_at or now_utc(), None, self.attribution,
                                           list(dns_records.LIMITATIONS)))
        return out


class CertificateTransparencyConnector(_BaseConnector):
    """Passive certificate search, and the sibling names certificates reveal."""

    name = "certificate_transparency"
    provider = "crt.sh certificate transparency search (Sectigo)"
    allowed_hosts = {certs.CT_HOST}
    attribution = ("Public certificate transparency log search. A log entry records that a certificate was issued; "
                   "it does not establish that a site was serving, nor that names sharing a certificate share an "
                   "operator.")

    def enabled(self) -> bool:
        return get_settings().enable_ct

    def not_configured_hint(self) -> str:
        return ("Set ENABLE_CT=true to allow passive certificate-transparency search "
                "(public source; fair-use limits apply)")

    def _probe(self) -> None:
        self.http.get_json(certs.search_url("example.com", include_subdomains=False))

    def _fetch_one(self, kind: str, value: str) -> list[ExternalObservation]:
        if kind != "domain" or is_reserved_name(value):
            return []
        payload = self.http.get_json(certs.search_url(value))
        found = certs.parse_entries(payload if isinstance(payload, list) else [], value)
        url = certs.search_url(value)
        out = [ExternalObservation("certificate", self.provider, {"domain": value, **c.as_fields()},
                                   now_utc(), url, self.attribution, list(certs.LIMITATIONS)) for c in found]
        names = certs.discovered_names(found, value)
        if names:
            out.append(ExternalObservation(
                "subdomain_discovery", self.provider,
                {"domain": value, "names": names, "name_count": len(names),
                 "method": "certificate_subject_alternative_names"},
                now_utc(), url, self.attribution,
                list(certs.LIMITATIONS) + ["a_discovered_name_is_a_lead_not_an_observed_service"]))
        related = certs.related_names(found, value)
        if related:
            out.append(ExternalObservation(
                "shared_certificate_names", self.provider,
                {"domain": value, "names": related, "name_count": len(related)},
                now_utc(), url, self.attribution,
                list(certs.LIMITATIONS) + ["shared_certificate_is_candidate_evidence_only"]))
        if not out:
            out.append(ExternalObservation(
                "certificate", self.provider,
                {"domain": value, "status": "no_entries_found",
                 "status_meaning": ("This search returned no certificate for the name. That is this source's "
                                    "coverage, not proof that none exists.")},
                now_utc(), url, self.attribution, list(certs.LIMITATIONS)))
        return out


class PassiveDnsConnector(_BaseConnector):
    """Historical domain-to-address observations, which need a licensed provider.

    The adapter, its request shape and its normalised result exist so a provider can be configured without
    further code. Without one it reports not_configured, and dated historical observations still enter a case
    through the technical-observations JSON path, which is how a case gets history today.
    """

    name = "passive_dns"
    provider = "Passive DNS provider (operator-supplied)"
    attribution = "Historical resolution observations from a licensed passive-DNS provider."

    @property
    def allowed_hosts(self) -> set[str]:  # type: ignore[override]
        from urllib.parse import urlparse

        u = get_settings().passive_dns_url
        host = urlparse(u).hostname if u else None
        return {host.lower()} if host else set()

    def __init__(self):
        self._health = None
        self._live = False
        self.http = SafeHttp(self.allowed_hosts)

    def enabled(self) -> bool:
        s = get_settings()
        return bool(s.passive_dns_url and s.passive_dns_key)

    def not_configured_hint(self) -> str:
        return ("Set PASSIVE_DNS_URL and PASSIVE_DNS_KEY to enable dated historical resolution. Until then, the "
                "only historical observations are those supplied as evidence; nothing is reconstructed from a "
                "current lookup.")

    def _probe(self) -> None:
        s = get_settings()
        self.http.get_json(s.passive_dns_url, headers={"Authorization": f"Bearer {s.passive_dns_key}"})

    def _fetch_one(self, kind: str, value: str) -> list[ExternalObservation]:
        if kind not in {"domain", "ip"} or is_reserved_name(value):
            return []
        s = get_settings()
        data = self.http.get_json(f"{s.passive_dns_url.rstrip('/')}/{value}",
                                  headers={"Authorization": f"Bearer {s.passive_dns_key}"})
        records = data.get("records") if isinstance(data, dict) else None
        rows = []
        for r in (records or [])[:200]:
            if not isinstance(r, dict):
                continue
            rows.append({"name": r.get("rrname") or r.get("name"),
                         "value": r.get("rdata") or r.get("value"),
                         "record": r.get("rrtype") or r.get("type"),
                         "first_seen": r.get("time_first") or r.get("first_seen"),
                         "last_seen": r.get("time_last") or r.get("last_seen"),
                         "observation_count": r.get("count")})
        return [ExternalObservation(
            "passive_dns", self.provider,
            {"indicator": value, "records": rows, "record_count": len(rows)},
            now_utc(), None, self.attribution,
            ["provider_coverage_is_partial_and_an_absence_is_not_evidence_of_absence",
             "first_and_last_seen_are_the_providers_observation_window_not_a_validity_proof"])]


class NetworkClassificationConnector(_BaseConnector):
    """Whether an address appears on the Tor Project's published exit-node list.

    A listing describes the network address, not a person: an exit node carries other people's traffic by
    design. A negative result means only that this list did not contain the address when it was read.
    """

    name = "network_classification"
    provider = "Tor Project bulk exit list"
    allowed_hosts = {"check.torproject.org"}
    attribution = ("The Tor Project's published list of exit-node addresses. Membership describes the network "
                   "address, never the identity or the conduct of whoever used it.")
    LIST_URL = "https://check.torproject.org/torbulkexitlist"

    def __init__(self):
        super().__init__()
        self._addresses: set[str] | None = None
        self._loaded_at = None

    def enabled(self) -> bool:
        return get_settings().enable_tor_exit_list

    def not_configured_hint(self) -> str:
        return ("Set ENABLE_TOR_EXIT_LIST=true to check addresses against the Tor Project's published exit list. "
                "No VPN or proxy provider is configured, so those classifications are unavailable.")

    def _load(self) -> set[str]:
        text = self.http.get_text(self.LIST_URL)
        addrs = {line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")}
        self._addresses, self._loaded_at = addrs, now_utc()
        return addrs

    def _probe(self) -> None:
        if not self._load():
            raise RuntimeError("exit list was empty")

    def _fetch_one(self, kind: str, value: str) -> list[ExternalObservation]:
        if kind != "ip" or not is_lookupable_ip(value):
            return []
        addrs = self._addresses if self._addresses is not None else self._load()
        listed = value in addrs
        return [ExternalObservation(
            "network_classification", self.provider,
            {"ip": value, "tor_exit_node": listed,
             "classification": "listed_tor_exit_node" if listed else "not_on_this_list",
             "list_read_at": (self._loaded_at or now_utc()).isoformat(),
             "list_size": len(addrs), "vpn_or_proxy": "no_provider_configured"},
            now_utc(), self.LIST_URL, self.attribution,
            ["an_exit_node_carries_other_peoples_traffic_so_a_listing_identifies_no_one",
             "not_on_this_list_means_only_that_this_list_did_not_contain_it_when_read",
             "no_vpn_or_proxy_provider_is_configured"])]


class UrlhausConnector(_BaseConnector):
    name = "urlhaus"
    provider = "abuse.ch URLhaus"
    allowed_hosts = {"urlhaus-api.abuse.ch"}
    attribution = "abuse.ch URLhaus community API; fair-use terms apply; commercial use may require enhanced access."

    def enabled(self) -> bool:
        return bool(get_settings().urlhaus_auth_key)

    def not_configured_hint(self) -> str:
        return "Set URLHAUS_AUTH_KEY to enable"

    def _probe(self) -> None:
        self.http.get_json("https://urlhaus-api.abuse.ch/v1/host/", headers={"Auth-Key": get_settings().urlhaus_auth_key},
                           method="POST", data={"host": "example.com"})

    def _fetch_one(self, kind: str, value: str) -> list[ExternalObservation]:
        if kind not in {"domain", "ip"} or value.endswith(".test"):
            return []
        data = self.http.get_json("https://urlhaus-api.abuse.ch/v1/host/", headers={"Auth-Key": get_settings().urlhaus_auth_key},
                                  method="POST", data={"host": value})
        return [ExternalObservation("threat_intel", self.provider, {"host": value, "query_status": data.get("query_status"),
                                                                    "url_count": data.get("url_count"), "firstseen": data.get("firstseen")},
                                    now_utc(), None, self.attribution, ["community_feed_coverage_is_partial"])]


class ThreatfoxConnector(_BaseConnector):
    name = "threatfox"
    provider = "abuse.ch ThreatFox"
    allowed_hosts = {"threatfox-api.abuse.ch"}
    attribution = "abuse.ch ThreatFox community API; IOCs older than ~6 months are expired from the API."

    def enabled(self) -> bool:
        return bool(get_settings().threatfox_auth_key)

    def not_configured_hint(self) -> str:
        return "Set THREATFOX_AUTH_KEY to enable"

    def _probe(self) -> None:
        self.http.get_json("https://threatfox-api.abuse.ch/api/v1/", headers={"Auth-Key": get_settings().threatfox_auth_key},
                           method="POST", data={"query": "search_ioc", "search_term": "example.com"})

    def _fetch_one(self, kind: str, value: str) -> list[ExternalObservation]:
        if kind not in {"domain", "ip"} or value.endswith(".test"):
            return []
        data = self.http.get_json("https://threatfox-api.abuse.ch/api/v1/", headers={"Auth-Key": get_settings().threatfox_auth_key},
                                  method="POST", data={"query": "search_ioc", "search_term": value})
        return [ExternalObservation("threat_intel", self.provider, {"indicator": value, "query_status": data.get("query_status"),
                                                                    "matches": len(data.get("data") or []) if isinstance(data.get("data"), list) else 0},
                                    now_utc(), None, self.attribution, ["ioc_expiry_6_months", "cloud_ips_change_tenants"])]


class MispConnector(_BaseConnector):
    name = "misp"
    provider = "MISP (operator instance)"
    attribution = "Operator-controlled MISP instance via Automation API."

    @property
    def allowed_hosts(self) -> set[str]:  # type: ignore[override]
        from urllib.parse import urlparse
        u = get_settings().misp_url
        return {urlparse(u).hostname.lower()} if u and urlparse(u).hostname else set()

    def __init__(self):
        self._health = None
        self._live = False
        self.http = SafeHttp(self.allowed_hosts)

    def enabled(self) -> bool:
        s = get_settings()
        return bool(s.misp_url and s.misp_key)

    def not_configured_hint(self) -> str:
        return "Set MISP_URL and MISP_KEY to enable (interface implemented; no instance configured)"

    def _probe(self) -> None:
        s = get_settings()
        self.http.get_json(f"{s.misp_url.rstrip('/')}/servers/getVersion", headers={"Authorization": s.misp_key, "Accept": "application/json"})

    def _fetch_one(self, kind: str, value: str) -> list[ExternalObservation]:
        s = get_settings()
        data = self.http.get_json(f"{s.misp_url.rstrip('/')}/attributes/restSearch", method="POST",
                                  headers={"Authorization": s.misp_key, "Accept": "application/json", "Content-Type": "application/json"},
                                  data={"value": value, "returnFormat": "json"})
        attrs = (data.get("response") or {}).get("Attribute") or []
        return [ExternalObservation("threat_intel", self.provider, {"indicator": value, "matches": len(attrs)}, now_utc(), None, self.attribution, [])]


class SyntheticMockConnector(_BaseConnector):
    """Mock adapter used only for synthetic cases; never contacts a network."""
    name = "synthetic_mock"
    provider = "Synthetic fixture (no network)"
    attribution = "Synthetic data generated by the case factory."

    def enabled(self) -> bool:
        return True

    def status(self) -> ConnectorHealth:
        return ConnectorHealth("mock", "Offline synthetic adapter; observations come from generated technical_observations.json", now_utc())

    def healthcheck(self) -> ConnectorHealth:
        return self.status()


REGISTRY: dict[str, _BaseConnector] = {}


def get_registry() -> dict[str, _BaseConnector]:
    if not REGISTRY:
        for cls in (RdapConnector, IpRdapConnector, DnsConnector, CertificateTransparencyConnector,
                    PassiveDnsConnector, NetworkClassificationConnector,
                    UrlhausConnector, ThreatfoxConnector, MispConnector, SyntheticMockConnector):
            inst = cls()
            REGISTRY[inst.name] = inst
    return REGISTRY
