from __future__ import annotations

import pytest

from technographics.fusion import fuse
from technographics.schema import Detection


def det(vendor_id, source, conf, tier=None, evidence=None):
    return Detection(
        vendor_id=vendor_id,
        vendor_name=vendor_id.title(),
        category="cdp",
        source=source,
        confidence=conf,
        evidence=evidence or [f"{source}-evidence"],
        tier_signal=tier,
    )


def test_vendor_in_both_uses_noisy_or():
    dns = [det("intercom", "dns", 0.9)]
    web = [det("intercom", "web", 0.8)]
    [result] = fuse(dns, web)
    assert result.source == "fused"
    # 1 - (1-0.9)*(1-0.8) = 0.98
    assert result.confidence == pytest.approx(0.98)
    assert set(result.evidence) == {"dns-evidence", "web-evidence"}


def test_single_pipeline_passthrough():
    out = fuse([det("hubspot", "dns", 0.6)], [])
    assert len(out) == 1
    assert out[0].source == "dns"
    assert out[0].confidence == 0.6


def test_tier_signal_prefers_enterprise():
    dns = [det("salesforce", "dns", 0.5, tier="enterprise")]
    web = [det("salesforce", "web", 0.5, tier="paid")]
    [result] = fuse(dns, web)
    assert result.tier_signal == "enterprise"


def test_sorted_descending():
    dns = [det("a", "dns", 0.3), det("b", "dns", 0.9)]
    web = [det("a", "web", 0.3)]
    out = fuse(dns, web)
    assert [d.vendor_id for d in out] == ["b", "a"]
    assert [d.confidence for d in out] == sorted([d.confidence for d in out], reverse=True)
