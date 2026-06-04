from __future__ import annotations

import json
from pathlib import Path

import pytest

from technographics.dns_matcher import DNSMatcher, DNSRecords, aggregate_confidence
from technographics.loader import load_library

FIXTURE = Path(__file__).parent / "fixtures" / "sample_dns_records.json"


@pytest.fixture(scope="module")
def matcher() -> DNSMatcher:
    lib = load_library()
    return DNSMatcher(lib.dns_signatures, lib.vendors)


@pytest.fixture(scope="module")
def records() -> DNSRecords:
    data = json.loads(FIXTURE.read_text())
    return DNSRecords(**data)


@pytest.fixture(scope="module")
def by_vendor(matcher, records) -> dict:
    return {d.vendor_id: d for d in matcher.match(records)}


def test_detects_expected_vendors(by_vendor):
    assert {"intercom", "hubspot", "microsoft_365", "cloudflare"} <= set(by_vendor)


def test_soa_field_triggers_master_tier(by_vendor):
    """The fixture's SOA points at ns1.dreamhost.com. The master-tier
    DreamHost signature is SOA-only, so this confirms the new SOA arm in
    DNSMatcher._match_one is wired up AND that the loader is exposing master
    DNS signatures alongside curated ones."""
    assert "dreamhost" in by_vendor, "DreamHost SOA pattern did not match"
    d = by_vendor["dreamhost"]
    assert any("SOA" in e for e in d.evidence)


def test_no_false_positive_google_workspace(by_vendor):
    # Outlook SPF must not trip the Google Workspace signature.
    assert "google_workspace" not in by_vendor


def test_intercom_confidence_and_tier(by_vendor):
    d = by_vendor["intercom"]
    assert d.source == "dns"
    assert d.confidence == pytest.approx(1.0)
    assert d.tier_signal == "paid"
    assert any("intercom.help" in e for e in d.evidence)


def test_hubspot_confidence_and_tier(by_vendor):
    d = by_vendor["hubspot"]
    # two STRONG (0.85) matches -> 0.85 + 0.05 boost
    assert d.confidence == pytest.approx(0.90)
    assert d.tier_signal == "paid"


def test_microsoft_365_definitive(by_vendor):
    d = by_vendor["microsoft_365"]
    assert d.confidence == pytest.approx(1.0)
    assert d.category == "email_productivity"


def test_cloudflare_from_ns(by_vendor):
    d = by_vendor["cloudflare"]
    assert d.confidence == pytest.approx(1.0)
    assert any("ns.cloudflare.com" in e for e in d.evidence)


def test_results_sorted_descending(matcher, records):
    confs = [d.confidence for d in matcher.match(records)]
    assert confs == sorted(confs, reverse=True)


def test_empty_records_no_detections(matcher):
    assert matcher.match(DNSRecords(domain="nothing.example")) == []


class TestConfidenceFormula:
    def test_single(self):
        assert aggregate_confidence([0.85]) == pytest.approx(0.85)

    def test_boost_caps_at_015(self):
        assert aggregate_confidence([0.6] * 10) == pytest.approx(0.75)

    def test_never_exceeds_one(self):
        assert aggregate_confidence([1.0, 0.85, 0.85]) == 1.0

    def test_empty(self):
        assert aggregate_confidence([]) == 0.0
