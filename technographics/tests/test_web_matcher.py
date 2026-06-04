from __future__ import annotations

import json
from pathlib import Path

import pytest

from technographics.loader import load_library
from technographics.web_matcher import PageData, WebMatcher

FIXTURE = Path(__file__).parent / "fixtures" / "sample_page_data.json"


@pytest.fixture(scope="module")
def matcher() -> WebMatcher:
    lib = load_library()
    return WebMatcher(lib.web_signatures, lib.vendors)


@pytest.fixture(scope="module")
def page() -> PageData:
    return PageData(**json.loads(FIXTURE.read_text()))


@pytest.fixture(scope="module")
def by_vendor(matcher, page) -> dict:
    return {d.vendor_id: d for d in matcher.match(page)}


def test_detects_intercom_and_segment(by_vendor):
    assert {"intercom", "segment"} <= set(by_vendor)


def test_intercom_high_confidence_with_many_signals(by_vendor):
    d = by_vendor["intercom"]
    assert d.source == "web"
    assert d.confidence == pytest.approx(1.0)
    # js global + script + cookie + html all contributed
    assert any("window.Intercom" in e for e in d.evidence)
    assert any("intercom-id-" in e for e in d.evidence)
    assert any("intercom-frame" in e for e in d.evidence)


def test_segment_detected_via_js_and_script(by_vendor):
    d = by_vendor["segment"]
    assert d.confidence == pytest.approx(1.0)
    assert d.category == "cdp"


def test_cloudflare_detected_via_server_header(by_vendor):
    assert "cloudflare" in by_vendor
    assert any("cloudflare" in e.lower() for e in by_vendor["cloudflare"].evidence)


def test_no_false_positive_hubspot(by_vendor):
    assert "hubspot" not in by_vendor


def test_js_globals_case_sensitive(matcher):
    # lowercase 'intercom' should NOT match the 'Intercom' global
    page = PageData(js_globals=["intercom"])
    assert "intercom" not in {d.vendor_id for d in matcher.match(page)}


def test_empty_page_no_detections(matcher):
    assert matcher.match(PageData()) == []


def test_results_sorted_descending(matcher, page):
    confs = [d.confidence for d in matcher.match(page)]
    assert confs == sorted(confs, reverse=True)
