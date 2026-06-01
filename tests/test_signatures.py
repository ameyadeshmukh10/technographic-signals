"""Detector tests against saved HTML fixtures.

Each test runs all four category detectors against one fixture and
asserts both that the expected vendors *are* detected and that nothing
else slips through. The minimal fixture has its own dedicated false-
positive test.
"""

from __future__ import annotations

from src.detectors import ad_pixels, crm, martech, salestech


def _names(hits) -> set[str]:
    return {h.name for h in hits}


def test_hubspot_fixture(make_fetch_result):
    fr = make_fetch_result("site_hubspot_meta_li.html")
    crm_hits = crm.detect(fr)
    ad_hits = ad_pixels.detect(fr)
    mt_hits = martech.detect(fr)
    st_hits = salestech.detect(fr)

    assert _names(crm_hits) == {"HubSpot"}, f"CRM mismatch: {_names(crm_hits)}"
    assert _names(ad_hits) == {
        "Meta Pixel",
        "LinkedIn Insight Tag",
        "Google Tag Manager",
    }, f"ad_pixel mismatch: {_names(ad_hits)}"
    assert mt_hits == [], f"unexpected martech: {[h.name for h in mt_hits]}"
    assert st_hits == [], f"unexpected salestech: {[h.name for h in st_hits]}"


def test_salesforce_fixture(make_fetch_result):
    fr = make_fetch_result("site_salesforce_pardot_marketo.html")
    crm_hits = crm.detect(fr)
    ad_hits = ad_pixels.detect(fr)
    mt_hits = martech.detect(fr)
    st_hits = salestech.detect(fr)

    assert _names(crm_hits) == {"Salesforce / Pardot", "Marketo"}, (
        f"CRM mismatch: {_names(crm_hits)}"
    )
    assert ad_hits == [], f"unexpected ad_pixel: {[h.name for h in ad_hits]}"
    assert _names(mt_hits) == {"Drift"}, f"martech mismatch: {_names(mt_hits)}"
    assert _names(st_hits) == {"Drift"}, f"salestech mismatch: {_names(st_hits)}"


def test_segment_fixture(make_fetch_result):
    fr = make_fetch_result("site_segment_mixpanel_intercom.html")
    crm_hits = crm.detect(fr)
    ad_hits = ad_pixels.detect(fr)
    mt_hits = martech.detect(fr)
    st_hits = salestech.detect(fr)

    assert crm_hits == [], f"unexpected CRM: {[h.name for h in crm_hits]}"
    assert ad_hits == [], f"unexpected ad_pixel: {[h.name for h in ad_hits]}"
    assert _names(mt_hits) == {"Segment", "Mixpanel", "Intercom"}, (
        f"martech mismatch: {_names(mt_hits)}"
    )
    assert _names(st_hits) == {"Intercom", "Calendly"}, (
        f"salestech mismatch: {_names(st_hits)}"
    )


def test_minimal_fixture(make_fetch_result):
    fr = make_fetch_result("site_minimal.html")
    assert crm.detect(fr) == []
    assert ad_pixels.detect(fr) == []
    assert martech.detect(fr) == []
    assert salestech.detect(fr) == []


def test_no_false_positives_on_minimal(make_fetch_result):
    fr = make_fetch_result("site_minimal.html")
    all_hits = (
        crm.detect(fr)
        + ad_pixels.detect(fr)
        + martech.detect(fr)
        + salestech.detect(fr)
    )
    assert all_hits == [], f"false positives: {[h.name for h in all_hits]}"
