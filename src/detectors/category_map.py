"""Map technographics detections onto the 4 output buckets.

The technographics library categorizes vendors with its own taxonomy
(curated 11-bucket + the full 108-category Wappalyzer set). The HubSpot
output string only has five buckets: ``crm``, ``ad_pixel``, ``martech``,
``salestech``, ``erp`` (see ``_CATEGORY_DISPLAY`` in ``orchestrator.py``).

Master frequently files ad pixels under "Analytics"/"Advertising" and
intent tools under "Analytics"/"Marketing automation", so a pure
category→bucket map is not enough. We resolve a bucket per detection as:

    VENDOR_BUCKET_OVERRIDE[vendor_id]  if present
    else CATEGORY_TO_BUCKET[category]  if present
    else None  (detection dropped from the output string)
"""

from __future__ import annotations

# technographics vendor.category (snake_case) -> output bucket
CATEGORY_TO_BUCKET: dict[str, str] = {
    # CRM
    "crm": "crm",
    # Martech: MAP / CDP / analytics / A-B / email / forms
    "marketing_automation": "martech",
    "cdp": "martech",
    "customer_data_platform": "martech",
    "analytics": "martech",
    "product_analytics": "martech",
    "a_b_testing": "martech",
    "ab_testing": "martech",
    "email": "martech",
    "email_productivity": "martech",
    "form_builders": "martech",
    "surveys": "martech",
    "tag_managers": "ad_pixel",  # GTM-style tags sit with ad pixels
    # Ad pixels
    "advertising": "ad_pixel",
    "retargeting": "ad_pixel",
    # Salestech: chat / scheduling / intent
    "live_chat": "salestech",
    "customer_support": "salestech",
    "appointment_scheduling": "salestech",
    "sales_engagement": "salestech",
    # ERP suites (detected via the subdomain probe step, not the marketing site)
    "erp": "erp",
}

# vendor_id -> bucket. Wins over CATEGORY_TO_BUCKET. Used where master's
# category misfiles a vendor relative to how a GTM team thinks about it.
VENDOR_BUCKET_OVERRIDE: dict[str, str] = {
    # --- ad pixels master files under Analytics/Advertising ---
    "facebook_pixel": "ad_pixel",
    "google_ads": "ad_pixel",
    "google_ads_conversion_tracking": "ad_pixel",
    "google_tag_manager": "ad_pixel",
    "linkedin_insight_tag": "ad_pixel",
    "linkedin_ads": "ad_pixel",
    "tiktok_pixel": "ad_pixel",
    "twitter_ads": "ad_pixel",
    "reddit_ads": "ad_pixel",
    "pinterest_conversion_tag": "ad_pixel",
    "microsoft_advertising": "ad_pixel",
    "snap_pixel": "ad_pixel",
    "quora_pixel": "ad_pixel",
    # --- sales/intent tools master files under Analytics/Marketing automation ---
    "6sense": "salestech",
    "demandbase": "salestech",
    "zoominfo": "salestech",
    "leadfeeder": "salestech",
    "clearbit_reveal": "salestech",
    "albacross": "salestech",
    "warmly": "salestech",
    "koala": "salestech",
    "gong": "salestech",
    "salesloft": "salestech",
    "apollo": "salestech",
    "outreach": "salestech",
    "qualified": "salestech",
    "drift": "salestech",
    "intercom": "salestech",
    "chili_piper": "salestech",
    "calendly": "salestech",
    "g2": "salestech",
    "factors_ai": "salestech",
    "reo": "salestech",
    "aisdr": "salestech",
}


def bucket_for(vendor_id: str, category: str) -> str | None:
    """Resolve the output bucket for a detection, or None to drop it."""
    if vendor_id in VENDOR_BUCKET_OVERRIDE:
        return VENDOR_BUCKET_OVERRIDE[vendor_id]
    return CATEGORY_TO_BUCKET.get(category)


def confidence_bucket(confidence: float) -> str:
    """Map a 0..1 technographics confidence onto high/medium/low.

    Thresholds mirror the existing low-confidence filter semantics in
    orchestrator.py (`filter_low_confidence` keeps high/medium).
    """
    if confidence >= 0.85:
        return "high"
    if confidence >= 0.6:
        return "medium"
    return "low"
