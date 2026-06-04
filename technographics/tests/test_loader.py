from __future__ import annotations

import json

import pytest

from technographics.loader import load_library, load_selection

CURATED_VENDORS = {
    "salesforce", "hubspot", "pipedrive", "marketo", "pardot", "customer_io",
    "klaviyo", "segment", "rudderstack", "mparticle", "intercom", "zendesk",
    "gorgias", "front", "outreach", "salesloft", "apollo", "google_workspace",
    "microsoft_365", "google_analytics", "mixpanel", "amplitude", "heap",
    "fullstory", "snowflake", "databricks", "fivetran", "hightouch",
    "cloudflare", "akamai", "fastly",
    # ported gap signatures (marketing/sales config)
    "google_ads", "g2", "factors_ai", "reo", "aisdr",
}


def test_curated_vendors_present_and_marked():
    lib = load_library()
    assert CURATED_VENDORS <= set(lib.vendors)
    for vid in CURATED_VENDORS:
        assert lib.source(vid) == "curated", vid


def test_curated_only_mode():
    lib = load_library(include_master=False)
    assert set(lib.vendors) == CURATED_VENDORS
    assert lib.stats()["master"] == 0
    assert lib.stats()["curated"] == 36


def test_master_tier_loads():
    lib = load_library()
    assert len(lib.vendors) > 1000, "master tier should add thousands of vendors"
    # A well-known Wappalyzer-only entry:
    assert "wordpress" in lib.vendors
    assert lib.source("wordpress") == "wappalyzer"


def test_curated_overrides_master_atomically():
    """For shared vendor_ids, curated metadata wins as a whole."""
    lib = load_library()
    intercom = lib.vendors["intercom"]
    # Curated provides typical_buyer; master does not.
    assert intercom.typical_buyer
    # Curated category is our snake_case bucket.
    assert intercom.category == "customer_support"


def test_every_curated_vendor_has_a_known_category():
    lib = load_library()
    for vid in CURATED_VENDORS:
        cat = lib.vendors[vid].category
        assert cat in lib.categories, f"{vid} -> {cat}"


def test_dns_signatures_reference_known_vendors():
    lib = load_library()
    for vendor_id, sig in lib.dns_signatures.items():
        assert sig.vendor_id == vendor_id
        assert vendor_id in lib.vendors


def test_intercom_dns_patterns_parsed():
    lib = load_library()
    sig = lib.dns_signatures["intercom"]
    assert any("intercom.help" in p.value for p in sig.cname_patterns)
    assert sig.paid_indicators
    assert "help" in sig.subdomains_to_probe


def test_paid_and_enterprise_indicators_have_notes():
    """Curated indicators must explain WHY they signal paid/enterprise."""
    lib = load_library(include_master=False)
    for sig in lib.dns_signatures.values():
        for pat in (*sig.paid_indicators, *sig.enterprise_indicators):
            assert pat.notes.strip(), f"{sig.vendor_id} indicator missing notes"


def test_selection_filter_narrows_library():
    lib = load_library(selection={"intercom", "segment", "wordpress"})
    assert set(lib.vendors) == {"intercom", "segment", "wordpress"}
    assert set(lib.web_signatures) <= {"intercom", "segment", "wordpress"}
    assert set(lib.dns_signatures) <= {"intercom", "segment", "wordpress"}


def test_load_selection_reads_json(tmp_path):
    path = tmp_path / "selection.json"
    path.write_text(json.dumps({"selected": ["intercom", "hubspot"]}))
    assert load_selection(path) == {"intercom", "hubspot"}


def test_load_library_missing_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_library(tmp_path / "does-not-exist")


def test_stats_split_curated_and_master():
    stats = load_library().stats()
    assert stats["curated"] == 36
    assert stats["master"] >= 7000
    assert stats["total_vendors"] == stats["curated"] + stats["master"]
    assert stats["with_dns"] >= 31  # at least the curated DNS sigs
    assert stats["with_web"] >= 7000  # the master web tier
