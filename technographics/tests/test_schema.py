from __future__ import annotations

import pytest

from technographics.schema import (
    DomPattern,
    MatchType,
    Pattern,
    SignalStrength,
    dom_pattern_from_dict,
    pattern_from_dict,
    pattern_to_dict,
    vendor_from_dict,
    web_signature_from_dict,
)


def make(value: str, mt: MatchType) -> Pattern:
    return Pattern(value=value, match_type=mt, strength=SignalStrength.STRONG)


class TestExact:
    def test_match(self):
        assert make("Intercom", MatchType.EXACT).matches("intercom")

    def test_no_match(self):
        assert not make("Intercom", MatchType.EXACT).matches("intercomSettings")

    def test_case_insensitive(self):
        assert make("HUBSPOT", MatchType.EXACT).matches("hubspot")

    def test_strips_dots(self):
        assert make("intercom.com", MatchType.EXACT).matches(".intercom.com.")


class TestContains:
    def test_match(self):
        assert make("intercom.help", MatchType.CONTAINS).matches(
            "custom.intercom.help.example.com"
        )

    def test_no_match(self):
        assert not make("zendesk", MatchType.CONTAINS).matches("intercom.help")


class TestSuffix:
    def test_match(self):
        assert make("hs-sites.com", MatchType.SUFFIX).matches("123.hs-sites.com")

    def test_no_match(self):
        assert not make("hs-sites.com", MatchType.SUFFIX).matches(
            "hs-sites.com.evil.com"
        )

    def test_trailing_dot_normalized(self):
        assert make("mktoweb.com", MatchType.SUFFIX).matches("foo.mktoweb.com.")


class TestPrefix:
    def test_match(self):
        assert make("intercom-id-", MatchType.PREFIX).matches("intercom-id-abc123")

    def test_no_match(self):
        assert not make("intercom-id-", MatchType.PREFIX).matches("x-intercom-id-1")


class TestRegex:
    def test_match(self):
        assert make(r"widget\.intercom\.io", MatchType.REGEX).matches(
            "https://widget.intercom.io/widget/abc"
        )

    def test_case_insensitive(self):
        assert make(r"INTERCOM", MatchType.REGEX).matches("widget.intercom.io")

    def test_no_match(self):
        assert not make(r"^segment\.com$", MatchType.REGEX).matches(
            "cdn.segment.com"
        )

    def test_invalid_regex_returns_false(self):
        assert not make(r"[unclosed", MatchType.REGEX).matches("anything")


class TestEdgeCases:
    def test_empty_candidate(self):
        assert not make("intercom", MatchType.CONTAINS).matches("")

    def test_none_candidate(self):
        assert not make("intercom", MatchType.CONTAINS).matches(None)  # type: ignore[arg-type]

    def test_empty_value_contains_matches_anything(self):
        assert make("", MatchType.CONTAINS).matches("anything")


class TestSignalStrength:
    @pytest.mark.parametrize(
        "value,expected",
        [
            (1.0, SignalStrength.DEFINITIVE),
            (0.95, SignalStrength.DEFINITIVE),
            (0.85, SignalStrength.STRONG),
            (0.8, SignalStrength.STRONG),
            (0.6, SignalStrength.MODERATE),
            (0.5, SignalStrength.MODERATE),
            (0.3, SignalStrength.WEAK),
            (0.1, SignalStrength.WEAK),
        ],
    )
    def test_from_value_snaps(self, value, expected):
        assert SignalStrength.from_value(value) is expected


class TestDomPattern:
    def test_basic_selector_only(self):
        d = dom_pattern_from_dict({"selector": ".my-widget"})
        assert d.selector == ".my-widget"
        assert d.exists is True
        assert d.attributes == {}
        assert d.text is None

    def test_with_attributes_and_text(self):
        d = dom_pattern_from_dict({
            "selector": "#root",
            "attributes": {
                "data-app": {"value": "intercom", "match_type": "exact", "strength": 0.85},
            },
            "text": {"value": "Powered by Intercom", "match_type": "contains", "strength": 0.6},
        })
        assert "data-app" in d.attributes
        assert d.attributes["data-app"].matches("intercom")
        assert d.text is not None
        assert d.text.matches("we love powered by intercom")


class TestExtendedVendor:
    def test_loads_wappalyzer_fields(self):
        v = vendor_from_dict({
            "vendor_id": "intercom",
            "vendor_name": "Intercom",
            "category": "customer_support",
            "source": "wappalyzer",
            "upstream_name": "Intercom",
            "wappalyzer_cats": [52, 17],
            "implies": ["jquery"],
            "cpe": "cpe:/a:intercom:intercom",
            "saas": True,
            "oss": False,
            "pricing": ["mid", "recurring"],
            "description": "Live chat.",
            "icon": "Intercom.svg",
        })
        assert v.source == "wappalyzer"
        assert v.wappalyzer_cats == [52, 17]
        assert v.implies == ["jquery"]
        assert v.saas is True
        assert v.oss is False
        assert v.pricing == ["mid", "recurring"]
        assert v.cpe.startswith("cpe:")
        assert v.icon == "Intercom.svg"

    def test_defaults_when_curated_only(self):
        v = vendor_from_dict({
            "vendor_id": "hubspot",
            "vendor_name": "HubSpot",
            "category": "crm",
        })
        assert v.source == "curated"
        assert v.wappalyzer_cats == []
        assert v.saas is False


class TestExtendedWebSignature:
    def test_loads_superset_fields(self):
        sig = web_signature_from_dict({
            "vendor_id": "x",
            "inline_script_patterns": [{"value": "window\\.foo", "match_type": "regex", "strength": 1.0}],
            "text_patterns": [{"value": "powered by", "match_type": "contains", "strength": 0.6}],
            "dom_patterns": [{"selector": "#root"}],
            "probe_paths": {"/license.txt": [{"value": "GPL", "match_type": "contains", "strength": 0.6}]},
        })
        assert sig.inline_script_patterns
        assert sig.text_patterns[0].matches("Powered by Acme")
        assert sig.dom_patterns[0].selector == "#root"
        assert "/license.txt" in sig.probe_paths


class TestRoundTrip:
    def test_pattern_dict_round_trip(self):
        original = {
            "value": "widget.intercom.io",
            "match_type": "regex",
            "strength": 0.85,
            "notes": "main widget",
        }
        pat = pattern_from_dict(original)
        assert pat.match_type is MatchType.REGEX
        assert pat.strength is SignalStrength.STRONG
        dumped = pattern_to_dict(pat)
        assert dumped["value"] == original["value"]
        assert dumped["match_type"] == "regex"
        assert dumped["notes"] == "main widget"
