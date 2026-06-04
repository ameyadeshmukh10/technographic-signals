"""Typed signature schema for the dual-pipeline technographic detector.

A single vendor is described by shared metadata (:class:`Vendor`) plus up to two
independent signature documents: a :class:`DNSSignature` and a
:class:`WebSignature`. Both signature types are built out of :class:`Pattern`
objects, which carry a value, a match strategy, and a confidence weight.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache


class MatchType(Enum):
    EXACT = "exact"
    CONTAINS = "contains"
    SUFFIX = "suffix"
    PREFIX = "prefix"
    REGEX = "regex"


class SignalStrength(Enum):
    DEFINITIVE = 1.0
    STRONG = 0.85
    MODERATE = 0.6
    WEAK = 0.3

    @classmethod
    def from_value(cls, value: float) -> "SignalStrength":
        """Snap an arbitrary float to the nearest defined strength bucket."""
        return min(cls, key=lambda member: abs(member.value - value))


@lru_cache(maxsize=2048)
def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def _normalize(text: str) -> str:
    """Lower-case and strip leading/trailing dots and whitespace.

    DNS records and host fragments routinely carry trailing dots (the FQDN
    root) and inconsistent casing; normalizing both sides keeps comparisons
    stable.
    """
    return text.strip().strip(".").lower()


@dataclass
class Pattern:
    value: str
    match_type: MatchType
    strength: SignalStrength
    notes: str = ""

    def matches(self, candidate: str) -> bool:
        if candidate is None:
            return False
        # REGEX matches against the raw (only case-folded) candidate so that
        # anchors and dots in the expression behave as the author wrote them.
        if self.match_type is MatchType.REGEX:
            try:
                return _compile(self.value).search(candidate) is not None
            except re.error:
                return False

        cand = _normalize(candidate)
        val = _normalize(self.value)
        if self.match_type is MatchType.EXACT:
            return cand == val
        if self.match_type is MatchType.CONTAINS:
            return val in cand
        if self.match_type is MatchType.SUFFIX:
            return cand.endswith(val)
        if self.match_type is MatchType.PREFIX:
            return cand.startswith(val)
        return False


@dataclass
class Vendor:
    vendor_id: str
    vendor_name: str
    vendor_url: str
    category: str
    subcategory: str = ""
    typical_buyer: list[str] = field(default_factory=list)
    company_stage: list[str] = field(default_factory=list)
    price_tier: str = ""  # "smb" | "mid_market" | "enterprise"
    typically_replaces: list[str] = field(default_factory=list)
    typically_replaced_by: list[str] = field(default_factory=list)

    # --- Upstream Wappalyzer fields (populated by the master importer) ---
    source: str = "curated"  # "curated" | "wappalyzer"
    upstream_name: str = ""  # original Wappalyzer technology name
    wappalyzer_cats: list[int] = field(default_factory=list)
    implies: list[str] = field(default_factory=list)
    excludes: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    requires_category: list[int] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    cpe: str = ""
    description: str = ""
    icon: str = ""
    saas: bool = False
    oss: bool = False
    pricing: list[str] = field(default_factory=list)


@dataclass
class DNSSignature:
    vendor_id: str
    cname_patterns: list[Pattern] = field(default_factory=list)
    txt_patterns: list[Pattern] = field(default_factory=list)
    mx_patterns: list[Pattern] = field(default_factory=list)
    ns_patterns: list[Pattern] = field(default_factory=list)
    a_patterns: list[Pattern] = field(default_factory=list)
    soa_patterns: list[Pattern] = field(default_factory=list)
    subdomains_to_probe: list[str] = field(default_factory=list)
    paid_indicators: list[Pattern] = field(default_factory=list)
    enterprise_indicators: list[Pattern] = field(default_factory=list)
    last_verified: str | None = None
    verified_domains: list[str] = field(default_factory=list)


@dataclass
class DomPattern:
    """Wappalyzer-style DOM selector match.

    A hit means: the selector matches at least one node, AND (if specified)
    each ``attributes`` / ``properties`` / ``text`` sub-pattern matches the
    corresponding value on that node. The DOM matcher itself isn't built yet
    — this dataclass exists so the master importer can capture the
    fingerprint losslessly for a future pass.
    """

    selector: str
    exists: bool = True
    attributes: dict[str, Pattern] = field(default_factory=dict)
    properties: dict[str, Pattern] = field(default_factory=dict)
    text: Pattern | None = None
    strength: SignalStrength = SignalStrength.STRONG
    notes: str = ""


@dataclass
class WebSignature:
    vendor_id: str
    js_globals: list[Pattern] = field(default_factory=list)
    script_src_patterns: list[Pattern] = field(default_factory=list)
    cookie_patterns: list[Pattern] = field(default_factory=list)
    header_patterns: dict[str, list[Pattern]] = field(default_factory=dict)
    html_patterns: list[Pattern] = field(default_factory=list)
    meta_patterns: dict[str, list[Pattern]] = field(default_factory=dict)
    url_patterns: list[Pattern] = field(default_factory=list)
    paid_indicators: list[Pattern] = field(default_factory=list)

    # --- Captured by importer; not yet consumed by the web matcher ---
    dom_patterns: list[DomPattern] = field(default_factory=list)
    inline_script_patterns: list[Pattern] = field(default_factory=list)
    text_patterns: list[Pattern] = field(default_factory=list)
    css_patterns: list[Pattern] = field(default_factory=list)
    xhr_patterns: list[Pattern] = field(default_factory=list)
    robots_patterns: list[Pattern] = field(default_factory=list)
    cert_issuer_patterns: list[Pattern] = field(default_factory=list)
    probe_paths: dict[str, list[Pattern]] = field(default_factory=dict)

    last_verified: str | None = None
    verified_domains: list[str] = field(default_factory=list)


@dataclass
class Detection:
    vendor_id: str
    vendor_name: str
    category: str
    source: str  # "dns" | "web" | "fused"
    confidence: float  # 0.0 - 1.0
    evidence: list[str] = field(default_factory=list)
    tier_signal: str | None = None  # "paid" | "enterprise" | None


# ---------------------------------------------------------------------------
# (De)serialization helpers
# ---------------------------------------------------------------------------

def pattern_from_dict(data: dict) -> Pattern:
    return Pattern(
        value=data["value"],
        match_type=MatchType(data["match_type"]),
        strength=SignalStrength.from_value(float(data["strength"])),
        notes=data.get("notes", ""),
    )


def pattern_to_dict(pattern: Pattern) -> dict:
    return {
        "value": pattern.value,
        "match_type": pattern.match_type.value,
        "strength": pattern.strength.value,
        "notes": pattern.notes,
    }


def _patterns(items: list | None) -> list[Pattern]:
    return [pattern_from_dict(item) for item in (items or [])]


def _pattern_map(data: dict | None) -> dict[str, list[Pattern]]:
    return {key: _patterns(value) for key, value in (data or {}).items()}


def vendor_from_dict(data: dict) -> Vendor:
    return Vendor(
        vendor_id=data["vendor_id"],
        vendor_name=data["vendor_name"],
        vendor_url=data.get("vendor_url", ""),
        category=data["category"],
        subcategory=data.get("subcategory", ""),
        typical_buyer=list(data.get("typical_buyer", [])),
        company_stage=list(data.get("company_stage", [])),
        price_tier=data.get("price_tier", ""),
        typically_replaces=list(data.get("typically_replaces", [])),
        typically_replaced_by=list(data.get("typically_replaced_by", [])),
        source=data.get("source", "curated"),
        upstream_name=data.get("upstream_name", ""),
        wappalyzer_cats=list(data.get("wappalyzer_cats", [])),
        implies=list(data.get("implies", [])),
        excludes=list(data.get("excludes", [])),
        requires=list(data.get("requires", [])),
        requires_category=list(data.get("requires_category", [])),
        aliases=list(data.get("aliases", [])),
        cpe=data.get("cpe", ""),
        description=data.get("description", ""),
        icon=data.get("icon", ""),
        saas=bool(data.get("saas", False)),
        oss=bool(data.get("oss", False)),
        pricing=list(data.get("pricing", [])),
    )


def dns_signature_from_dict(data: dict) -> DNSSignature:
    return DNSSignature(
        vendor_id=data["vendor_id"],
        cname_patterns=_patterns(data.get("cname_patterns")),
        txt_patterns=_patterns(data.get("txt_patterns")),
        mx_patterns=_patterns(data.get("mx_patterns")),
        ns_patterns=_patterns(data.get("ns_patterns")),
        a_patterns=_patterns(data.get("a_patterns")),
        soa_patterns=_patterns(data.get("soa_patterns")),
        subdomains_to_probe=list(data.get("subdomains_to_probe", [])),
        paid_indicators=_patterns(data.get("paid_indicators")),
        enterprise_indicators=_patterns(data.get("enterprise_indicators")),
        last_verified=data.get("last_verified"),
        verified_domains=list(data.get("verified_domains", [])),
    )


def dom_pattern_from_dict(data: dict) -> DomPattern:
    text = data.get("text")
    return DomPattern(
        selector=data["selector"],
        exists=bool(data.get("exists", True)),
        attributes={k: pattern_from_dict(v) for k, v in (data.get("attributes") or {}).items()},
        properties={k: pattern_from_dict(v) for k, v in (data.get("properties") or {}).items()},
        text=pattern_from_dict(text) if text else None,
        strength=SignalStrength.from_value(float(data.get("strength", 0.85))),
        notes=data.get("notes", ""),
    )


def web_signature_from_dict(data: dict) -> WebSignature:
    return WebSignature(
        vendor_id=data["vendor_id"],
        js_globals=_patterns(data.get("js_globals")),
        script_src_patterns=_patterns(data.get("script_src_patterns")),
        cookie_patterns=_patterns(data.get("cookie_patterns")),
        header_patterns=_pattern_map(data.get("header_patterns")),
        html_patterns=_patterns(data.get("html_patterns")),
        meta_patterns=_pattern_map(data.get("meta_patterns")),
        url_patterns=_patterns(data.get("url_patterns")),
        paid_indicators=_patterns(data.get("paid_indicators")),
        dom_patterns=[dom_pattern_from_dict(d) for d in (data.get("dom_patterns") or [])],
        inline_script_patterns=_patterns(data.get("inline_script_patterns")),
        text_patterns=_patterns(data.get("text_patterns")),
        css_patterns=_patterns(data.get("css_patterns")),
        xhr_patterns=_patterns(data.get("xhr_patterns")),
        robots_patterns=_patterns(data.get("robots_patterns")),
        cert_issuer_patterns=_patterns(data.get("cert_issuer_patterns")),
        probe_paths=_pattern_map(data.get("probe_paths")),
        last_verified=data.get("last_verified"),
        verified_domains=list(data.get("verified_domains", [])),
    )
