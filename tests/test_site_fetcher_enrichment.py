"""Tests for the site_fetcher enrichment (headers / meta_tags / js_globals)
and that those channels flow through the technographics adapter."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "technographics" / "src"))

from src.site_fetcher import FetchResult, SiteFetcher, _extract_meta_tags  # noqa: E402


SAMPLE_HTML = """
<html><head>
  <meta name="generator" content="HubSpot">
  <meta property="og:title" content="Acme">
  <meta name="GENERATOR" content="dup-should-be-ignored">
  <meta charset="utf-8">
</head><body>hi</body></html>
"""


class TestExtractMetaTags:
    def test_parses_name_and_property(self):
        meta = _extract_meta_tags(SAMPLE_HTML)
        assert meta["generator"] == "HubSpot"
        assert meta["og:title"] == "Acme"

    def test_keys_lowercased_first_wins(self):
        meta = _extract_meta_tags(SAMPLE_HTML)
        assert meta["generator"] == "HubSpot"  # not the later dup

    def test_empty_html(self):
        assert _extract_meta_tags("") == {}


class TestStaticEnrichment:
    def test_static_request_captures_headers_and_meta(self):
        fetcher = SiteFetcher()
        resp = MagicMock()
        resp.url = "https://acme.example/"
        resp.status_code = 200
        resp.text = SAMPLE_HTML
        resp.cookies = []
        resp.headers = {"Server": "cloudflare", "X-Powered-By": "Express"}

        with patch.object(fetcher, "_get_session") as gs:
            gs.return_value.get.return_value = resp
            fr = fetcher._static_request("https://acme.example/")

        assert fr.headers == {"server": "cloudflare", "x-powered-by": "Express"}
        assert fr.meta_tags["generator"] == "HubSpot"
        assert fr.js_globals == []  # static can't evaluate window
        assert fr.rendered is False


class TestAdapterFlowsNewChannels:
    def test_js_global_only_detection(self):
        """A vendor with no script src — only a window global — is detected
        once js_globals flow through the adapter. microsoft_clarity's js
        global is 'clarity'."""
        from src.detectors.engine import TechEngine

        fr = FetchResult(
            url="https://acme.example/",
            status=200,
            html="<html></html>",
            script_srcs=[],
            cookies=[],
            js_globals=["clarity"],
        )
        engine = TechEngine(enable_dns=False)
        hits = {h.name: h for h in engine.detect(None, "https://acme.example/", fr)}
        assert "Microsoft Clarity" in hits
        assert hits["Microsoft Clarity"].category == "martech"

    def test_page_from_fetch_passes_all_channels(self):
        from src.detectors.engine import TechEngine

        fr = FetchResult(
            url="https://acme.example/",
            html="<html></html>",
            script_srcs=["https://x/y.js"],
            cookies=["sessionid"],
            headers={"server": "cloudflare"},
            meta_tags={"generator": "HubSpot"},
            js_globals=["Intercom"],
        )
        engine = TechEngine(enable_dns=False)
        page = engine._page_from_fetch("https://acme.example/", fr)
        assert page.js_globals == ["Intercom"]
        assert page.headers == {"server": "cloudflare"}
        assert page.meta_tags == {"generator": "HubSpot"}
        assert page.cookies == {"sessionid": ""}
