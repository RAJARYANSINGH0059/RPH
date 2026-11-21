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
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed for {host}: {exc}")
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

    def get_json(self, url: str, headers: dict | None = None, method: str = "GET", data: dict | None = None) -> dict:
        key = f"{method}:{url}:{sorted((data or {}).items())}"
        now = time.time()
        if key in self._cache and now - self._cache[key][0] < self.cache_ttl:
            return self._cache[key][1]
        assert_safe_url(url, self.allowed_hosts)
        wait = self.min_interval - (now - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.time()
        with httpx.Client(timeout=self.timeout, follow_redirects=False) as client:
            resp = client.request(method, url, headers={"User-Agent": "ps05x-connector/0.1", **(headers or {})}, data=data)
        ct = resp.headers.get("content-type", "")
        if "json" not in ct:
            raise ValueError(f"Unexpected content-type {ct}")
        if len(resp.content) > self.max_bytes:
            raise ValueError("Response too large")
        resp.raise_for_status()
        payload = resp.json()
        self._cache[key] = (time.time(), payload)
        return payload


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
