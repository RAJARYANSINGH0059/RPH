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
KNOWN_TYPES = {"dns", "hosting", "url", "rdap", "cdn", "note"}


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


_CORE_KEYS = {"type", "observed_at", "domain", "ip", "ttl", "provider", "asn", "source", "note", "url", "registrar", "created", "valid_from", "valid_to", "resolver"}


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
