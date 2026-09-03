"""Tests for the probe-then-fetch step and the curated oracle_ebs signature.

No network: fetches are stubbed via the prober's ``fetcher`` injection point.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Importable without an editable install, e.g. when pytest runs from the repo
# root (mirrors tests/test_engine_mapping.py in the parent project).
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from technographics.loader import load_library
from technographics.schema import (
    DNSSignature,
    MatchType,
    Pattern,
    SignalStrength,
    Vendor,
    WebSignature,
)
from technographics.subdomain_prober import probe_specs, probe_subdomains
from technographics.web_matcher import PageData, WebMatcher

EBS_LOGIN_URL = "https://erp.acme.com/OA_HTML/AppsLogin"

EBS_LOGIN_HTML = """
<html><head>
<script src="/OA_HTML/cabo/jsLibs/Common2_2_24.js"></script>
</head><body>
<form action="/OA_HTML/OA.jsp?page=/oracle/apps/fnd/sso/login/webui/MainLoginPG">
<img src="/OA_MEDIA/FNDSSCORP.gif">
<a href="/OA_HTML/AppsLocalLogin.jsp">login</a>
</form>
</body></html>
"""

EBS_PAGE = PageData(
    final_url=EBS_LOGIN_URL,
    html=EBS_LOGIN_HTML,
    script_srcs=["/OA_HTML/cabo/jsLibs/Common2_2_24.js"],
    headers={"server": "Oracle-HTTP-Server", "x-oracle-dms-ecid": "005abc"},
    cookies={"oracle.uix": ""},
)

# An SPA catch-all: echoes a 200 for any path, so final_url matches the
# constructed probe URL, but the body carries no EBS artifacts.
SPA_PAGE = PageData(
    final_url=EBS_LOGIN_URL,
    html="<html><body><div id='root'></div></body></html>",
    headers={"server": "vercel"},
)


def _fake_fetcher(pages: dict[str, PageData], calls: list[str] | None = None):
    async def fetch(url: str) -> PageData | None:
        if calls is not None:
            calls.append(url)
        return pages.get(url)

    return fetch


@pytest.fixture(scope="module")
def library():
    return load_library()


def _sigs(library):
    return library.dns_signatures, library.web_signatures, library.vendors


class TestProbeSpecs:
    def test_oracle_ebs_opted_in(self, library):
        specs = probe_specs(library.dns_signatures, library.web_signatures)
        assert "oracle_ebs" in specs
        subdomains, paths = specs["oracle_ebs"]
        assert "erp" in subdomains and "isupplier" in subdomains
        assert "/OA_HTML/AppsLogin" in paths

    def test_oracle_fusion_opted_in(self, library):
        specs = probe_specs(library.dns_signatures, library.web_signatures)
        assert "oracle_fusion_cloud_erp" in specs
        subdomains, paths = specs["oracle_fusion_cloud_erp"]
        assert "erp" in subdomains
        assert "/" in paths

    def test_vendors_without_probe_paths_excluded(self, library):
        specs = probe_specs(library.dns_signatures, library.web_signatures)
        assert "customer_io" not in specs  # has subdomains_to_probe, no probe_paths


class TestProbeSubdomains:
    def test_detects_ebs_on_probed_subdomain(self, library):
        dns_sigs, web_sigs, vendors = _sigs(library)
        dets = probe_subdomains(
            "acme.com", dns_sigs, web_sigs, vendors,
            fetcher=_fake_fetcher({EBS_LOGIN_URL: EBS_PAGE}),
        )
        assert [d.vendor_id for d in dets] == ["oracle_ebs"]
        det = dets[0]
        assert det.source == "probe"
        assert det.confidence >= 0.85
        assert det.category == "erp"
        assert det.evidence[0] == f"probe {EBS_LOGIN_URL}"
        assert any("/OA_HTML/cabo/" in e for e in det.evidence)

    def test_url_only_match_rejected(self, library):
        # A catch-all server 200s the probe path we constructed ourselves;
        # the URL pattern fires but nothing in the response corroborates.
        dns_sigs, web_sigs, vendors = _sigs(library)
        dets = probe_subdomains(
            "acme.com", dns_sigs, web_sigs, vendors,
            fetcher=_fake_fetcher({EBS_LOGIN_URL: SPA_PAGE}),
        )
        assert dets == []

    def test_dead_hosts_yield_nothing(self, library):
        dns_sigs, web_sigs, vendors = _sigs(library)
        dets = probe_subdomains(
            "acme.com", dns_sigs, web_sigs, vendors, fetcher=_fake_fetcher({})
        )
        assert dets == []

    def test_scheme_and_www_stripped_from_domain(self, library):
        dns_sigs, web_sigs, vendors = _sigs(library)
        dets = probe_subdomains(
            "https://www.acme.com/", dns_sigs, web_sigs, vendors,
            fetcher=_fake_fetcher({EBS_LOGIN_URL: EBS_PAGE}),
        )
        assert [d.vendor_id for d in dets] == ["oracle_ebs"]

    def test_one_detection_per_vendor_across_hosts(self, library):
        dns_sigs, web_sigs, vendors = _sigs(library)
        second = "https://ebs.acme.com/OA_HTML/AppsLogin"
        dets = probe_subdomains(
            "acme.com", dns_sigs, web_sigs, vendors,
            fetcher=_fake_fetcher({EBS_LOGIN_URL: EBS_PAGE, second: EBS_PAGE}),
        )
        assert len(dets) == 1

    def test_max_probes_cap(self, library):
        dns_sigs, web_sigs, vendors = _sigs(library)
        calls: list[str] = []
        probe_subdomains(
            "acme.com", dns_sigs, web_sigs, vendors,
            max_probes_per_vendor=2,
            fetcher=_fake_fetcher({}, calls),
        )
        # the cap applies per probe-enabled vendor
        n_vendors = len(probe_specs(dns_sigs, web_sigs))
        assert len(calls) == 2 * n_vendors


class TestRedirectTrust:
    """URL-pattern evidence counts when the server redirected the probe off
    the probed site — the destination was the server's choice, not ours."""

    FUSION_URL = "https://fa-xyz-saasfaprod1.fa.ocs.oraclecloud.com/fscmUI/faces/AtkHomePageWelcome"

    def test_external_redirect_detected_as_fusion(self, library):
        # erp.acme.com/ bounces to an Oracle Fusion pod (the bk.rw shape);
        # no body/header evidence needed, the redirect target is definitive.
        dns_sigs, web_sigs, vendors = _sigs(library)
        page = PageData(final_url=self.FUSION_URL, html="<html></html>")
        dets = probe_subdomains(
            "acme.com", dns_sigs, web_sigs, vendors,
            fetcher=_fake_fetcher({"https://erp.acme.com/": page}),
        )
        assert [d.vendor_id for d in dets] == ["oracle_fusion_cloud_erp"]
        assert dets[0].confidence >= 0.85
        assert dets[0].category == "erp"

    def test_redirect_to_www_apex_not_trusted(self, library):
        # Wildcard DNS funnels every subdomain to www with the path intact;
        # the SPA there 200s anything. The URL match alone must not count.
        dns_sigs, web_sigs, vendors = _sigs(library)
        page = PageData(
            final_url="https://www.acme.com/OA_HTML/AppsLogin",
            html="<html><div id='root'></div></html>",
        )
        dets = probe_subdomains(
            "acme.com", dns_sigs, web_sigs, vendors,
            fetcher=_fake_fetcher({EBS_LOGIN_URL: page}),
        )
        assert dets == []


class TestPeopleSoftAndJdEdwards:
    def test_peoplesoft_signon_detected(self, library):
        dns_sigs, web_sigs, vendors = _sigs(library)
        url = "https://careers.acme.com/"
        # A bare PeopleSoft host redirects "/" to the PIA signon and sets PS cookies.
        page = PageData(
            final_url="https://careers.acme.com/psp/hrprd/?cmd=login",
            html="<html><head><link href='/cs/hrprd/cache/ptStyle_x.css'></head>"
                 "<body>/psp/hrprd/ EMPLOYEE</body></html>",
            cookies={"PS_TOKEN": "", "PS_LASTSITE": ""},
        )
        dets = probe_subdomains(
            "acme.com", dns_sigs, web_sigs, vendors,
            fetcher=_fake_fetcher({url: page}),
        )
        assert [d.vendor_id for d in dets] == ["peoplesoft"]
        assert dets[0].confidence >= 0.85
        assert dets[0].category == "erp"

    def test_jd_edwards_login_detected(self, library):
        dns_sigs, web_sigs, vendors = _sigs(library)
        url = "https://jde.acme.com/jde/E1Menu.maf"
        page = PageData(
            final_url=url,
            html="<html><body class='jdeLoginTitle'>com.jdedwards E1Menu.maf</body></html>",
        )
        dets = probe_subdomains(
            "acme.com", dns_sigs, web_sigs, vendors,
            fetcher=_fake_fetcher({url: page}),
        )
        assert [d.vendor_id for d in dets] == ["jd_edwards"]
        assert dets[0].confidence == pytest.approx(1.0)

    def test_peoplesoft_and_ebs_not_confused(self, library):
        # An EBS AppsLogin response must not trip the PeopleSoft signature.
        dns_sigs, web_sigs, vendors = _sigs(library)
        dets = probe_subdomains(
            "acme.com", dns_sigs, web_sigs, vendors,
            fetcher=_fake_fetcher({EBS_LOGIN_URL: EBS_PAGE}),
        )
        assert [d.vendor_id for d in dets] == ["oracle_ebs"]


class TestProbeSpecDrivenByCustomSignatures:
    """The mechanism is generic: any vendor with both fields gets probed."""

    def _custom(self):
        vendors = {
            "acmeportal": Vendor(
                vendor_id="acmeportal", vendor_name="Acme Portal",
                vendor_url="", category="erp",
            )
        }
        dns_sigs = {
            "acmeportal": DNSSignature(
                vendor_id="acmeportal", subdomains_to_probe=["portal"]
            )
        }
        web_sigs = {
            "acmeportal": WebSignature(
                vendor_id="acmeportal",
                probe_paths={
                    "/login": [
                        Pattern("acme-portal-build", MatchType.CONTAINS, SignalStrength.DEFINITIVE)
                    ]
                },
            )
        }
        return dns_sigs, web_sigs, vendors

    def test_probe_path_patterns_matched_as_html(self):
        dns_sigs, web_sigs, vendors = self._custom()
        url = "https://portal.acme.com/login"
        page = PageData(final_url=url, html="<html><!-- acme-portal-build 1.2 --></html>")
        dets = probe_subdomains(
            "acme.com", dns_sigs, web_sigs, vendors,
            fetcher=_fake_fetcher({url: page}),
        )
        assert [d.vendor_id for d in dets] == ["acmeportal"]
        assert dets[0].confidence == pytest.approx(1.0)


class TestOracleEbsWebSignature:
    """The curated signature also works through the plain web matcher, e.g.
    when detect-one is pointed straight at an EBS host."""

    def test_full_page_high_confidence(self, library):
        matcher = WebMatcher(library.web_signatures, library.vendors)
        by_vendor = {d.vendor_id: d for d in matcher.match(EBS_PAGE)}
        assert "oracle_ebs" in by_vendor
        assert by_vendor["oracle_ebs"].confidence == pytest.approx(1.0)

    def test_marketing_page_not_matched(self, library):
        matcher = WebMatcher(library.web_signatures, library.vendors)
        page = PageData(
            final_url="https://www.acme.com/",
            html="<html><body>Buy our stuff</body></html>",
            headers={"server": "cloudflare"},
        )
        by_vendor = {d.vendor_id: d for d in matcher.match(page)}
        assert "oracle_ebs" not in by_vendor
