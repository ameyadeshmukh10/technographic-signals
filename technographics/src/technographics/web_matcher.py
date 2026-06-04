"""JS/Web detection engine.

Given :class:`PageData` captured from a rendered page, test each vendor's
:class:`WebSignature` and emit :class:`Detection` objects. Shares the
confidence formula with the DNS matcher.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from technographics.dns_matcher import aggregate_confidence
from technographics.schema import Detection, Pattern, Vendor, WebSignature


@dataclass
class PageData:
    final_url: str = ""
    js_globals: list[str] = field(default_factory=list)
    script_srcs: list[str] = field(default_factory=list)
    cookies: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)  # lowercased keys
    html: str = ""
    meta_tags: dict[str, str] = field(default_factory=dict)
    error: str | None = None


class WebMatcher:
    def __init__(self, signatures: dict[str, WebSignature], vendors: dict[str, Vendor]):
        self.signatures = signatures
        self.vendors = vendors

    def match(self, page: PageData) -> list[Detection]:
        detections: list[Detection] = []
        for sig in self.signatures.values():
            detection = self._match_one(sig, page)
            if detection is not None:
                detections.append(detection)
        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections

    def _match_one(self, sig: WebSignature, page: PageData) -> Detection | None:
        evidence: list[str] = []
        strengths: list[float] = []

        # js_globals: exact, case-sensitive membership in the captured key list.
        global_set = set(page.js_globals)
        for pat in sig.js_globals:
            if pat.value in global_set:
                evidence.append(f"window.{pat.value}")
                strengths.append(pat.strength.value)

        _scan(sig.script_src_patterns, page.script_srcs, "script", evidence, strengths)
        _scan_keys(sig.cookie_patterns, page.cookies, "cookie", evidence, strengths)
        _scan_map(sig.header_patterns, page.headers, "header", evidence, strengths)
        if page.html:
            _scan(sig.html_patterns, [page.html], "html", evidence, strengths, show_value=True)
        _scan_map(sig.meta_patterns, page.meta_tags, "meta", evidence, strengths)
        if page.final_url:
            _scan(sig.url_patterns, [page.final_url], "url", evidence, strengths)

        if not strengths:
            return None

        tier_signal = None
        for pat in sig.paid_indicators:
            if _matches_any(pat, page):
                evidence.append(f"[paid] {pat.value} ({pat.notes})")
                tier_signal = "paid"

        vendor = self.vendors.get(sig.vendor_id)
        return Detection(
            vendor_id=sig.vendor_id,
            vendor_name=vendor.vendor_name if vendor else sig.vendor_id,
            category=vendor.category if vendor else "",
            source="web",
            confidence=aggregate_confidence(strengths),
            evidence=evidence,
            tier_signal=tier_signal,
        )


def _scan(
    patterns: list[Pattern],
    candidates: list[str],
    label: str,
    evidence: list[str],
    strengths: list[float],
    show_value: bool = False,
) -> None:
    for pat in patterns:
        for cand in candidates:
            if pat.matches(cand):
                shown = pat.value if show_value else cand
                evidence.append(f"{label} {shown} ~ {pat.value}")
                strengths.append(pat.strength.value)
                break  # one hit per pattern is enough


def _scan_keys(
    patterns: list[Pattern],
    mapping: dict[str, str],
    label: str,
    evidence: list[str],
    strengths: list[float],
) -> None:
    keys = list(mapping)
    for pat in patterns:
        for key in keys:
            if pat.matches(key):
                evidence.append(f"{label} {key} ~ {pat.value}")
                strengths.append(pat.strength.value)
                break


def _scan_map(
    pattern_map: dict[str, list[Pattern]],
    mapping: dict[str, str],
    label: str,
    evidence: list[str],
    strengths: list[float],
) -> None:
    for name, patterns in pattern_map.items():
        value = mapping.get(name.lower())
        if value is None:
            continue
        for pat in patterns:
            if pat.matches(value):
                evidence.append(f"{label} {name}: {value} ~ {pat.value}")
                strengths.append(pat.strength.value)


def _matches_any(pat: Pattern, page: PageData) -> bool:
    candidates = (
        list(page.js_globals)
        + page.script_srcs
        + list(page.cookies)
        + list(page.headers.values())
        + list(page.meta_tags.values())
        + ([page.html] if page.html else [])
        + ([page.final_url] if page.final_url else [])
    )
    return any(pat.matches(c) for c in candidates)
