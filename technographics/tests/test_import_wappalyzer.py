"""Unit tests for scripts/import_wappalyzer.py.

No live HTTP: every test feeds a small inline upstream fixture into the
converter functions.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

_SPEC = importlib.util.spec_from_file_location("import_wappalyzer", REPO / "scripts" / "import_wappalyzer.py")
importer = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(importer)  # type: ignore[union-attr]

slugs = importlib.import_module("_slugs")


# ---------------------------------------------------------------------------
# slug + override map
# ---------------------------------------------------------------------------

class TestSlugify:
    @pytest.mark.parametrize("name,expected", [
        ("HubSpot", "hubspot"),
        ("Microsoft 365", "microsoft_365"),     # via override
        ("Customer.io", "customer_io"),         # via override
        ("Google Analytics", "google_analytics"),  # via override
        ("Apollo.io", "apollo"),                # via override (collides w/ "Apollo")
        ("FullStory", "fullstory"),
        ("RudderStack", "rudderstack"),
        ("My Cool Thing!!", "my_cool_thing"),
        ("   spaces   ", "spaces"),
        ("3.14 PI", "3_14_pi"),
        ("", "unknown"),
    ])
    def test_vendor_id_for(self, name, expected):
        assert slugs.vendor_id_for(name) == expected


class TestUniqueAssignment:
    def test_distinct_names_unique_ids(self):
        out = slugs.assign_unique(["Intercom", "HubSpot", "Segment"])
        assert len(set(out.values())) == 3

    def test_collisions_get_hash_suffix(self):
        # "Foo Bar" and "Foo.Bar" both slugify to "foo_bar"
        out = slugs.assign_unique(["Foo Bar", "Foo.Bar"])
        ids = sorted(out.values())
        # First wins the bare slug; second gets a __<hash> suffix
        assert ids[0] == "foo_bar"
        assert ids[1].startswith("foo_bar__")
        assert len(set(ids)) == 2

    def test_deterministic(self):
        a = slugs.assign_unique(["Foo Bar", "Foo.Bar", "Baz"])
        b = slugs.assign_unique(["Baz", "Foo.Bar", "Foo Bar"])
        assert a == b


# ---------------------------------------------------------------------------
# convert_web: field mapping
# ---------------------------------------------------------------------------

UPSTREAM_FIXTURE = {
    "js": {"Intercom": "", "intercomSettings": ""},
    "scriptSrc": ["widget\\.intercom\\.io", "js\\.intercomcdn\\.com\\;confidence:50"],
    "scripts": ["window\\.Intercom\\.q\\.push"],
    "cookies": {"intercom-id-": "", "intercom-session-": ""},
    "headers": {"X-Powered-By": "intercom\\;confidence:80"},
    "html": ["<div id=\"intercom-frame\""],
    "text": ["Powered by Intercom"],
    "css": ["intercom-launcher"],
    "xhr": ["api\\.intercom\\.io"],
    "robots": ["intercom"],
    "meta": {"generator": "Intercom"},
    "url": ["intercom\\.com"],
    "certIssuer": "Intercom",
    "dom": {
        "#intercom-container": {
            "exists": "",
            "attributes": {"data-app": "intercom"},
        }
    },
    "probe": {"/widget.js": "INTERCOM"},
}


@pytest.fixture
def converted():
    return importer.convert_web("Intercom", UPSTREAM_FIXTURE, "test-src")


class TestConvertWeb:
    def test_js_globals_become_exact_patterns(self, converted):
        names = {p["value"] for p in converted["js_globals"]}
        assert names == {"Intercom", "intercomSettings"}
        assert all(p["match_type"] == "exact" for p in converted["js_globals"])

    def test_script_src_strips_confidence_modifier(self, converted):
        srcs = {p["value"]: p["strength"] for p in converted["script_src_patterns"]}
        assert "widget\\.intercom\\.io" in srcs
        assert "js\\.intercomcdn\\.com" in srcs
        # confidence:50 → strength 0.5
        assert srcs["js\\.intercomcdn\\.com"] == 0.5

    def test_inline_scripts_captured(self, converted):
        assert any("window" in p["value"] for p in converted["inline_script_patterns"])

    def test_cookies_become_prefix_patterns(self, converted):
        prefixes = {p["value"] for p in converted["cookie_patterns"]}
        assert prefixes == {"intercom-id-", "intercom-session-"}
        assert all(p["match_type"] == "prefix" for p in converted["cookie_patterns"])

    def test_headers_lowercased_and_keyed(self, converted):
        assert "x-powered-by" in converted["header_patterns"]
        pat = converted["header_patterns"]["x-powered-by"][0]
        assert pat["value"] == "intercom"
        assert pat["strength"] == 0.8

    def test_text_css_xhr_robots_certissuer_all_present(self, converted):
        assert converted["text_patterns"]
        assert converted["css_patterns"]
        assert converted["xhr_patterns"]
        assert converted["robots_patterns"]
        assert converted["cert_issuer_patterns"]

    def test_dom_dict_form_captured(self, converted):
        dom = converted["dom_patterns"]
        assert len(dom) == 1
        assert dom[0]["selector"] == "#intercom-container"
        assert "data-app" in dom[0]["attributes"]

    def test_probe_paths_captured(self, converted):
        probe = converted["probe_paths"]
        assert "/widget.js" in probe
        assert probe["/widget.js"][0]["value"] == "INTERCOM"

    def test_handles_missing_fields_gracefully(self):
        out = importer.convert_web("Empty", {}, "test-src")
        # All buckets present but empty (or sparse)
        assert out["js_globals"] == []
        assert out["dom_patterns"] == []
        assert out["probe_paths"] == {}


# ---------------------------------------------------------------------------
# convert_dns: DNS field mapping
# ---------------------------------------------------------------------------

class TestConvertDns:
    def test_soa_maps_to_soa_patterns(self):
        out = importer.convert_dns("DreamHost", {"dns": {"SOA": ["ns\\d+\\.dreamhost\\.com"]}}, "test-src")
        assert out["soa_patterns"]
        assert out["soa_patterns"][0]["value"] == "ns\\d+\\.dreamhost\\.com"

    def test_mx_and_txt_mapped(self):
        out = importer.convert_dns("X", {"dns": {"MX": [".*\\.protection\\.outlook\\.com"], "TXT": ["MS=ms"]}}, "src")
        assert out["mx_patterns"]
        assert out["txt_patterns"]

    def test_no_dns_field_returns_empty(self):
        out = importer.convert_dns("X", {}, "src")
        assert all(v == [] for v in out.values())


# ---------------------------------------------------------------------------
# normalization for deterministic output
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_normalize_web_sorts_patterns(self):
        doc = {
            "vendor_id": "x",
            "js_globals": [
                {"value": "B", "match_type": "exact", "strength": 1.0, "notes": ""},
                {"value": "A", "match_type": "exact", "strength": 1.0, "notes": ""},
            ],
        }
        out = importer._normalize_web_doc(doc)
        assert [p["value"] for p in out["js_globals"]] == ["A", "B"]
