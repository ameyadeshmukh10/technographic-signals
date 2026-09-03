"""Unit tests for the technographics adapter's bucket mapping + DetectionHit
construction. No network, no HubSpot config required."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))
sys.path.insert(0, str(_REPO / "technographics" / "src"))

from detectors.category_map import bucket_for, confidence_bucket  # noqa: E402


class TestConfidenceBucket:
    def test_high(self):
        assert confidence_bucket(1.0) == "high"
        assert confidence_bucket(0.85) == "high"

    def test_medium(self):
        assert confidence_bucket(0.84) == "medium"
        assert confidence_bucket(0.6) == "medium"

    def test_low(self):
        assert confidence_bucket(0.59) == "low"
        assert confidence_bucket(0.3) == "low"


class TestBucketFor:
    def test_crm_by_category(self):
        assert bucket_for("salesforce", "crm") == "crm"

    def test_marketing_automation_to_martech(self):
        assert bucket_for("marketo", "marketing_automation") == "martech"

    def test_analytics_default_to_martech(self):
        assert bucket_for("mixpanel", "analytics") == "martech"

    def test_ad_pixel_override_beats_analytics_category(self):
        # master files LinkedIn Insight under "analytics"; override -> ad_pixel
        assert bucket_for("linkedin_insight_tag", "analytics") == "ad_pixel"
        assert bucket_for("tiktok_pixel", "analytics") == "ad_pixel"
        assert bucket_for("google_tag_manager", "tag_managers") == "ad_pixel"

    def test_intent_override_beats_marketing_automation(self):
        # 6sense lives under "marketing_automation" upstream; we want salestech
        assert bucket_for("6sense", "marketing_automation") == "salestech"
        assert bucket_for("zoominfo", "analytics") == "salestech"
        assert bucket_for("apollo", "javascript_libraries") == "salestech"

    def test_ported_gap_vendors(self):
        assert bucket_for("google_ads", "advertising") == "ad_pixel"
        assert bucket_for("g2", "sales_engagement") == "salestech"
        assert bucket_for("factors_ai", "sales_engagement") == "salestech"

    def test_unknown_category_dropped(self):
        assert bucket_for("some_random_cms", "cms") is None
        assert bucket_for("nginx", "web_servers") is None

    def test_erp_bucket(self):
        assert bucket_for("oracle_ebs", "erp") == "erp"


class TestEnginePageMapping:
    """Exercise the FetchResult->PageData->DetectionHit path without network."""

    def test_detect_web_only(self):
        from detectors.engine import TechEngine

        class FR:
            url = "https://acme.example/"
            html = 'gtag("config","AW-123") <div id="intercom-frame"></div>'
            script_srcs = [
                "https://cdn.segment.com/analytics.js/v1/x/analytics.min.js",
                "https://snap.licdn.com/li.lms-analytics/insight.min.js",
            ]
            cookies = ["intercom-id-xyz"]
            error = None

        engine = TechEngine(enable_dns=False, enable_probes=False)
        hits = engine.detect(None, "https://acme.example/", FR())
        by_name = {h.name: h for h in hits}

        # Ported Google Ads (ad_pixel), master LinkedIn Insight (ad_pixel),
        # Segment (martech), Intercom (salestech via override)
        buckets = {h.name: h.category for h in hits}
        assert buckets.get("Google Ads") == "ad_pixel"
        assert buckets.get("Linkedin Insight Tag") == "ad_pixel"
        assert buckets.get("Twilio Segment") == "martech"
        assert buckets.get("Intercom") == "salestech"
        # confidence is a legacy string bucket
        assert all(h.confidence in ("high", "medium", "low") for h in hits)
        # evidence capped at 3
        assert all(len(h.evidence) <= 3 for h in hits)

    def test_probe_detections_fused_into_hits(self, monkeypatch):
        from detectors import engine as engine_mod
        from technographics.schema import Detection

        class FR:
            url = "https://acme.example/"
            html = "<html><body>marketing</body></html>"
            script_srcs = []
            cookies = []
            error = None

        probe_det = Detection(
            vendor_id="oracle_ebs",
            vendor_name="Oracle E-Business Suite",
            category="erp",
            source="probe",
            confidence=1.0,
            evidence=["probe https://erp.acme.example/OA_HTML/AppsLogin", "html /OA_HTML/cabo/ ~ /OA_HTML/cabo/"],
        )
        monkeypatch.setattr(engine_mod, "probe_subdomains", lambda *a, **kw: [probe_det])

        engine = engine_mod.TechEngine(enable_dns=False, enable_probes=True)
        hits = engine.detect("acme.example", "https://acme.example/", FR())
        ebs = [h for h in hits if h.name == "Oracle E-Business Suite"]
        assert len(ebs) == 1
        assert ebs[0].category == "erp"
        assert ebs[0].confidence == "high"
        assert ebs[0].evidence[0].startswith("probe https://erp.acme.example/")

    def test_erp_rendered_in_output_string(self):
        from src.detectors import DetectionHit
        from src.orchestrator import format_signals

        hits = [
            DetectionHit(name="HubSpot", category="crm", confidence="high", evidence=[]),
            DetectionHit(
                name="Oracle E-Business Suite", category="erp", confidence="high", evidence=[]
            ),
        ]
        assert format_signals(hits) == "CRM: HubSpot | ERP: Oracle E-Business Suite"
