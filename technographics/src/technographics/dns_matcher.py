"""DNS detection engine.

Given collected DNS records for a domain, test each vendor's
:class:`DNSSignature` and emit :class:`Detection` objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from technographics.schema import Detection, DNSSignature, Pattern, Vendor


@dataclass
class DNSRecords:
    """Records collected for one domain.

    ``cname`` maps a probed hostname (e.g. ``help.acme.com``) to its CNAME
    target. Apex-level records are flat lists.
    """

    domain: str
    a: list[str] = field(default_factory=list)
    mx: list[str] = field(default_factory=list)
    txt: list[str] = field(default_factory=list)
    ns: list[str] = field(default_factory=list)
    soa: list[str] = field(default_factory=list)
    cname: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    @property
    def cname_targets(self) -> list[str]:
        return list(self.cname.values())


# Confidence shaping shared with the web matcher.
def aggregate_confidence(strengths: list[float]) -> float:
    if not strengths:
        return 0.0
    base = max(strengths)
    boost = min(0.15, 0.05 * (len(strengths) - 1))
    return min(1.0, base + boost)


class DNSMatcher:
    def __init__(self, signatures: dict[str, DNSSignature], vendors: dict[str, Vendor]):
        self.signatures = signatures
        self.vendors = vendors

    def match(self, records: DNSRecords) -> list[Detection]:
        detections: list[Detection] = []
        for vendor_id, sig in self.signatures.items():
            detection = self._match_one(sig, records)
            if detection is not None:
                detections.append(detection)
        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections

    def _match_one(self, sig: DNSSignature, records: DNSRecords) -> Detection | None:
        evidence: list[str] = []
        matched_strengths: list[float] = []

        # (patterns, candidate-iterable, label) per record type
        for patterns, candidates, label in (
            (sig.cname_patterns, records.cname.items(), "CNAME"),
            (sig.txt_patterns, records.txt, "TXT"),
            (sig.mx_patterns, records.mx, "MX"),
            (sig.ns_patterns, records.ns, "NS"),
            (sig.a_patterns, records.a, "A"),
            (sig.soa_patterns, records.soa, "SOA"),
        ):
            self._test(patterns, candidates, label, evidence, matched_strengths)

        if not matched_strengths:
            return None

        tier_signal = self._tier(sig, records, evidence)
        vendor = self.vendors.get(sig.vendor_id)
        return Detection(
            vendor_id=sig.vendor_id,
            vendor_name=vendor.vendor_name if vendor else sig.vendor_id,
            category=vendor.category if vendor else "",
            source="dns",
            confidence=aggregate_confidence(matched_strengths),
            evidence=evidence,
            tier_signal=tier_signal,
        )

    @staticmethod
    def _test(
        patterns: list[Pattern],
        candidates,
        label: str,
        evidence: list[str],
        matched_strengths: list[float],
    ) -> None:
        for pattern in patterns:
            for candidate in candidates:
                if label == "CNAME":
                    host, target = candidate
                    if pattern.matches(target):
                        evidence.append(f"{label} {host} -> {target} ~ {pattern.value}")
                        matched_strengths.append(pattern.strength.value)
                else:
                    if pattern.matches(candidate):
                        evidence.append(f"{label} {candidate} ~ {pattern.value}")
                        matched_strengths.append(pattern.strength.value)

    @staticmethod
    def _tier(sig: DNSSignature, records: DNSRecords, evidence: list[str]) -> str | None:
        all_candidates = (
            records.cname_targets + records.txt + records.mx + records.ns + records.a + records.soa
        )
        if _any_match(sig.enterprise_indicators, all_candidates, "enterprise", evidence):
            return "enterprise"
        if _any_match(sig.paid_indicators, all_candidates, "paid", evidence):
            return "paid"
        return None


def _any_match(
    patterns: list[Pattern], candidates: list[str], tier: str, evidence: list[str]
) -> bool:
    hit = False
    for pattern in patterns:
        for candidate in candidates:
            if pattern.matches(candidate):
                evidence.append(f"[{tier}] {candidate} ~ {pattern.value} ({pattern.notes})")
                hit = True
    return hit
