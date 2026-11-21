"""Concrete adapters: RDAP (current registration), DNS (current resolution), URLhaus/ThreatFox (key-gated), MISP (interface)."""
from __future__ import annotations

from app.core.config import get_settings
from app.connectors.base import ConnectorHealth, ExternalObservation, SafeHttp, is_blocked_ip, now_utc


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
    name = "rdap"
    provider = "rdap.org (ICANN RDAP bootstrap redirector)"
    allowed_hosts = {"rdap.org"}
    attribution = "RDAP registration data; personal data may be redacted. Current registration, not historical ownership."

    def enabled(self) -> bool:
        return get_settings().enable_rdap

    def not_configured_hint(self) -> str:
        return "Set ENABLE_RDAP=true to allow current registration lookups"

    def _probe(self) -> None:
        self.http.get_json("https://rdap.org/domain/example.com")

    def _fetch_one(self, kind: str, value: str) -> list[ExternalObservation]:
        if kind != "domain" or value.endswith(".test") or value.endswith(".example") or value.endswith(".invalid"):
            return []
        # rdap.org redirects (3xx) to the authoritative server; we follow one hop manually only to rdap.org-known hosts.
        try:
            data = self.http.get_json(f"https://rdap.org/domain/{value}")
        except Exception:
            # redirect responses are not JSON; treat as unavailable for this domain
            return [ExternalObservation("rdap", self.provider, {"domain": value, "note": "redirect_not_followed"}, now_utc(),
                                        attribution=self.attribution, limitations=["authoritative_server_not_in_allowlist"])]
        events = {e.get("eventAction"): e.get("eventDate") for e in data.get("events", []) if isinstance(e, dict)}
        registrar = None
        for ent in data.get("entities", []):
            if "registrar" in (ent.get("roles") or []):
                registrar = ent.get("handle") or ent.get("publicIds", [{}])[0].get("identifier")
        return [ExternalObservation("rdap", self.provider, {"domain": value, "registrar": registrar, "created": events.get("registration"),
                                                           "status": data.get("status")}, now_utc(), f"https://rdap.org/domain/{value}",
                                    self.attribution, ["rdap_is_current_registration_not_historical_ownership"])]


class DnsConnector(_BaseConnector):
    name = "dns"
    provider = "System resolver (dnspython)"
    allowed_hosts: set[str] = set()
    attribution = "Current A/AAAA/CNAME answers from the configured resolver. Not passive/historical DNS."

    def enabled(self) -> bool:
        return get_settings().enable_dns

    def not_configured_hint(self) -> str:
        return "Set ENABLE_DNS=true to allow current DNS lookups"

    def _probe(self) -> None:
        import dns.resolver
        dns.resolver.resolve("example.com", "A", lifetime=get_settings().connector_timeout_seconds)

    def _fetch_one(self, kind: str, value: str) -> list[ExternalObservation]:
        if kind != "domain" or value.endswith(".test"):
            return []
        import dns.resolver
        out = []
        ans = dns.resolver.resolve(value, "A", lifetime=get_settings().connector_timeout_seconds)
        for rr in ans:
            ip = rr.to_text()
            out.append(ExternalObservation("dns", self.provider, {"domain": value, "ip": ip, "ttl": ans.rrset.ttl, "record": "A",
                                                                 "resolver": "system", "blocked_range": is_blocked_ip(ip)},
                                           now_utc(), None, self.attribution, ["current_lookup_not_historical", "dns_mapping_valid_only_at_observation_time"]))
        return out


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
        for cls in (RdapConnector, DnsConnector, UrlhausConnector, ThreatfoxConnector, MispConnector, SyntheticMockConnector):
            inst = cls()
            REGISTRY[inst.name] = inst
    return REGISTRY
