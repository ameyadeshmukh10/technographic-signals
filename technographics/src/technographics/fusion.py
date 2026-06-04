"""Merge DNS and Web detections into a unified, deduplicated result set."""

from __future__ import annotations

from technographics.schema import Detection

# tier ordering for picking the strongest signal when both pipelines report one
_TIER_RANK = {None: 0, "paid": 1, "enterprise": 2}


def _stronger_tier(a: str | None, b: str | None) -> str | None:
    return a if _TIER_RANK[a] >= _TIER_RANK[b] else b


def fuse(
    dns_detections: list[Detection], web_detections: list[Detection]
) -> list[Detection]:
    by_id: dict[str, list[Detection]] = {}
    for det in (*dns_detections, *web_detections):
        by_id.setdefault(det.vendor_id, []).append(det)

    fused: list[Detection] = []
    for vendor_id, dets in by_id.items():
        if len(dets) == 1:
            fused.append(dets[0])
            continue

        # Detected in both pipelines: noisy-OR the confidences.
        confidence = 1.0
        for det in dets:
            confidence *= 1.0 - det.confidence
        confidence = 1.0 - confidence

        evidence: list[str] = []
        tier: str | None = None
        for det in dets:
            evidence.extend(det.evidence)
            tier = _stronger_tier(tier, det.tier_signal)

        first = dets[0]
        fused.append(
            Detection(
                vendor_id=vendor_id,
                vendor_name=first.vendor_name,
                category=first.category,
                source="fused",
                confidence=round(confidence, 4),
                evidence=evidence,
                tier_signal=tier,
            )
        )

    fused.sort(key=lambda d: d.confidence, reverse=True)
    return fused
