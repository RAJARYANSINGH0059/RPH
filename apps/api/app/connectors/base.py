"""Connector framework: healthcheck / fetch / normalise with timeouts, allowlists, caching and graceful failure.

Status vocabulary (shown to the investigator):
  configured      - credentials/flags present, not yet exercised
  not_configured  - disabled or missing key
  unavailable     - configured but last healthcheck failed
  mock            - synthetic/mock adapter
  live            - an actual authenticated request succeeded in this process
"""
from __future__ import annotations

import ipaddress
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings


@dataclass
class ExternalObservation:
    obs_type: str  # dns|rdap|threat_intel
    provider: str
    fields: dict
    observed_at: datetime
    source_url: str | None = None
    attribution: str = ""
    limitations: list[str] = field(default_factory=list)


@dataclass
class ConnectorHealth:
    status: str
    detail: str
    checked_at: datetime


class Connector(Protocol):
    name: str
    provider: str
    allowed_hosts: set[str]

    def status(self) -> ConnectorHealth: ...
    def healthcheck(self) -> ConnectorHealth: ...
    def fetch(self, indicators: list[tuple[str, str]]) -> list[ExternalObservation]: ...


# ---------------------------------------------------------------- SSRF guard

_BLOCKED_NETS = [ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24",
    "192.0.2.0/24", "192.168.0.0/16", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
    "::1/128", "fc00::/7", "fe80::/10", "ff00::/8",
)]


def is_blocked_ip(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return any(a in n for n in _BLOCKED_NETS) or a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved


def assert_safe_url(url: str, allowed_hosts: set[str]) -> None:
    """Allowlisted hostname + scheme https + resolved IPs must be public. Raises ValueError otherwise."""
    p = urlparse(url)
    if p.scheme != "https":
        raise ValueError("Only https provider URLs are permitted")
    host = (p.hostname or "").lower()
    if host not in allowed_hosts:
        raise ValueError(f"Host {host} not in connector allowlist")
    assert_public_host(host)


def assert_public_host(host: str) -> None:
    """Every address the host resolves to must be public.

    Separated from the allowlist check because RDAP cannot use a fixed allowlist: the authoritative server for a
    TLD or an address block is whatever IANA's registry names, and that list changes without us. The host still
    has to resolve entirely to public addresses, so a registry entry (or a redirect) pointing at a private or
    cloud-metadata address is refused.
    """
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed for {host}: {exc}")
    if not infos:
        raise ValueError(f"No address for {host}")
    for info in infos:
        if is_blocked_ip(info[4][0]):
            raise ValueError("Provider host resolves to a blocked address range")


class SafeHttp:
    """Small wrapper: allowlist + timeouts + size/content-type limits + simple TTL cache."""

    def __init__(self, allowed_hosts: set[str], timeout: float | None = None, max_bytes: int = 2_000_000, cache_ttl: int = 600):
        self.allowed_hosts = allowed_hosts
        self.timeout = timeout or get_settings().connector_timeout_seconds
        self.max_bytes = max_bytes
        self.cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, dict]] = {}
        self._last_call = 0.0
        self.min_interval = 0.5  # rate limit: 2 req/s per connector

    _REDIRECTS = {301, 302, 303, 307, 308}

    def _throttle(self) -> None:
        wait = self.min_interval - (time.time() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()

    def _check(self, url: str, extra_hosts: set[str] | None, any_public_host: bool) -> None:
        """Validate one URL before it is requested, including each hop of a redirect chain."""
        if any_public_host:
            p = urlparse(url)
            if p.scheme != "https":
                raise ValueError("Only https provider URLs are permitted")
            assert_public_host((p.hostname or "").lower())
        else:
            assert_safe_url(url, self.allowed_hosts | (extra_hosts or set()))

    def request_raw(self, url: str, headers: dict | None = None, method: str = "GET", data: dict | None = None,
                    *, extra_hosts: set[str] | None = None, any_public_host: bool = False,
                    max_redirects: int = 0) -> httpx.Response:
        """One request, with every redirect hop re-validated rather than trusted.

        httpx is kept on `follow_redirects=False` so no hop escapes the address checks: a provider that redirects
        to a private address, to plain http, or around a chain without end is refused at the hop that does it.
        """
        seen = 0
        target = url
        while True:
            self._check(target, extra_hosts, any_public_host)
            self._throttle()
            with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
                resp = client.request(method, target, headers={"User-Agent": "ps05x-connector/0.1", **(headers or {})}, data=data)
            if resp.status_code in self._REDIRECTS and resp.headers.get("location"):
                if seen >= max_redirects:
                    raise ValueError(f"Redirect limit reached at {resp.status_code} (hops allowed: {max_redirects})")
                seen += 1
                target = str(httpx.URL(target).join(resp.headers["location"]))
                method, data = "GET", None   # a redirected POST is not replayed as a POST
                continue
            return resp

    def get_json(self, url: str, headers: dict | None = None, method: str = "GET", data: dict | None = None,
                 *, extra_hosts: set[str] | None = None, any_public_host: bool = False,
                 max_redirects: int = 0) -> dict:
        key = f"{method}:{url}:{sorted((data or {}).items())}"
        now = time.time()
        if key in self._cache and now - self._cache[key][0] < self.cache_ttl:
            return self._cache[key][1]
        resp = self.request_raw(url, headers, method, data, extra_hosts=extra_hosts,
                                any_public_host=any_public_host, max_redirects=max_redirects)
        ct = resp.headers.get("content-type", "")
        if "json" not in ct:
            raise ValueError(f"Unexpected content-type {ct}")
        if len(resp.content) > self.max_bytes:
            raise ValueError("Response too large")
        resp.raise_for_status()
        payload = resp.json()
        self._cache[key] = (time.time(), payload)
        return payload

    def get_text(self, url: str, headers: dict | None = None, *, extra_hosts: set[str] | None = None,
                 any_public_host: bool = False, max_redirects: int = 0) -> str:
        """For providers that publish a plain-text list rather than JSON."""
        resp = self.request_raw(url, headers, "GET", None, extra_hosts=extra_hosts,
                                any_public_host=any_public_host, max_redirects=max_redirects)
        if len(resp.content) > self.max_bytes:
            raise ValueError("Response too large")
        resp.raise_for_status()
        return resp.text


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
