"""Signature library: the patterns we look for in a page's HTML/JS to
identify which go-to-market technologies a company uses.

The library is intentionally signature-based (no third-party enrichment API).
Each `Signature` describes a single technology and the fingerprints we expect
to see when it is installed: script source URLs, raw-HTML/DOM patterns,
inline JS calls, and (when JS is rendered) cookie names.

A `confidence` level is attached to every signature so the orchestrator can
decide how to combine evidence:

- high   : a unique fingerprint that essentially never collides
           (e.g., `js.hs-scripts.com` only ships with HubSpot).
- medium : a probable signal that could collide with adjacent products
           or that many sites carry without it being a meaningful signal
           on its own (e.g., GA4, GTM).
- low    : a weak signal — only worth reporting when combined with other
           evidence in the same page.

All regex patterns are intended to be matched case-insensitively. The
matcher applies `re.IGNORECASE`; do NOT embed `(?i)` flags inside the
pattern strings themselves.

If a technology legitimately spans multiple categories (Drift, Intercom,
HubSpot Forms vs. HubSpot CRM), each category gets its own `Signature`
entry so the orchestrator can bucket findings cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Category = Literal["crm", "ad_pixel", "martech", "salestech"]
Confidence = Literal["high", "medium", "low"]


@dataclass
class Signature:
    """A single technology fingerprint.

    Attributes:
        name: Canonical display name written exactly as it should appear
            in the `technographic_signals` HubSpot property.
        category: Which bucket this technology falls into.
        patterns: Regex patterns matched against the raw response body
            (catches inline JS calls like `fbq('init'`, `Munchkin.init`,
            global variable names, etc.). Case-insensitive at match time.
        script_src_patterns: Regex patterns matched against the `src`
            attribute of `<script>` tags.
        dom_patterns: Regex patterns matched against the raw HTML
            (use these for `<meta>` tags, `<form action="...">`, iframe
            src URLs, container ID strings, and similar markup-level
            fingerprints).
        cookie_patterns: Regex patterns matched against cookie names.
            Only useful when JS rendering is enabled (Playwright path),
            because most tracking cookies are not set on the initial
            HTML response.
        confidence: How much weight a single hit on this signature carries.
    """

    name: str
    category: Category
    confidence: Confidence
    patterns: list[str] = field(default_factory=list)
    script_src_patterns: list[str] = field(default_factory=list)
    dom_patterns: list[str] = field(default_factory=list)
    cookie_patterns: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CRM
# ---------------------------------------------------------------------------
# CRMs ship loader scripts from very specific subdomains and (for HubSpot)
# set tracking cookies with stable names. These are some of the most reliable
# fingerprints on a page — when present, they essentially never collide with
# anything else.

_CRM: list[Signature] = [
    Signature(
        name="HubSpot",
        category="crm",
        confidence="high",
        script_src_patterns=[
            r"js\.hs-scripts\.com",
            r"js\.hsforms\.net",
            r"js\.hs-analytics\.net",
            r"js\.hubspot\.com",
        ],
        dom_patterns=[
            r"<meta[^>]*name=['\"]generator['\"][^>]*content=['\"][^'\"]*HubSpot",
        ],
        cookie_patterns=[
            r"^hubspotutk$",
        ],
    ),
    Signature(
        name="Salesforce / Pardot",
        category="crm",
        confidence="high",
        patterns=[
            r"\bpardot\b",
        ],
        script_src_patterns=[
            r"pi\.pardot\.com",
            r"go\.pardot\.com",
        ],
        dom_patterns=[
            r"<form[^>]*action=['\"][^'\"]*webto\.salesforce\.com",
        ],
    ),
    Signature(
        name="Marketo",
        category="crm",
        confidence="high",
        patterns=[
            r"Munchkin\.init",
        ],
        script_src_patterns=[
            r"munchkin\.marketo\.net",
            r"\.mktoresp\.com",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Ad pixels
# ---------------------------------------------------------------------------
# Advertising / analytics pixels are typically loaded from a single, well-known
# CDN per platform and initialized with a small, predictable inline JS call
# (e.g., `fbq('init', ...)`). The CDN URL is usually the strongest signal; the
# inline call is a useful backup when the loader is bundled or proxied.
#
# GA4, GTM, and similar are marked `medium` because almost every site carries
# them — they're real signals, but they don't differentiate companies the way
# a CRM or a sales tool does.

_AD_PIXELS: list[Signature] = [
    Signature(
        name="Meta Pixel",
        category="ad_pixel",
        confidence="high",
        patterns=[
            r"fbq\(\s*['\"]init['\"]",
        ],
        script_src_patterns=[
            r"connect\.facebook\.net/en_US/fbevents\.js",
        ],
        dom_patterns=[
            r"facebook\.com/tr\?id=",
        ],
    ),
    Signature(
        name="Google Ads / gtag",
        category="ad_pixel",
        confidence="high",
        patterns=[
            r"gtag\(\s*['\"]config['\"]\s*,\s*['\"]AW-",
        ],
        script_src_patterns=[
            r"googletagmanager\.com/gtag/js",
        ],
    ),
    Signature(
        name="Google Analytics 4",
        category="ad_pixel",
        confidence="medium",
        patterns=[
            r"gtag\(\s*['\"]config['\"]\s*,\s*['\"]G-",
        ],
        script_src_patterns=[
            r"googletagmanager\.com/gtag/js\?id=G-",
        ],
    ),
    Signature(
        name="Google Tag Manager",
        category="ad_pixel",
        confidence="medium",
        patterns=[
            r"GTM-[A-Z0-9]+",
        ],
        script_src_patterns=[
            r"googletagmanager\.com/gtm\.js",
        ],
    ),
    Signature(
        name="LinkedIn Insight Tag",
        category="ad_pixel",
        confidence="high",
        patterns=[
            r"_linkedin_partner_id",
        ],
        script_src_patterns=[
            r"snap\.licdn\.com/li\.lms-analytics/insight\.min\.js",
        ],
    ),
    Signature(
        name="TikTok Pixel",
        category="ad_pixel",
        confidence="high",
        patterns=[
            r"ttq\.load\(",
        ],
        script_src_patterns=[
            r"analytics\.tiktok\.com/i18n/pixel/events\.js",
        ],
    ),
    Signature(
        name="X / Twitter Pixel",
        category="ad_pixel",
        confidence="high",
        patterns=[
            r"twq\(\s*['\"]config['\"]",
        ],
        script_src_patterns=[
            r"static\.ads-twitter\.com/uwt\.js",
        ],
    ),
    Signature(
        name="Reddit Pixel",
        category="ad_pixel",
        confidence="high",
        patterns=[
            r"rdt\(\s*['\"]init['\"]",
        ],
        script_src_patterns=[
            r"redditstatic\.com/ads/pixel\.js",
        ],
    ),
    Signature(
        name="Pinterest Tag",
        category="ad_pixel",
        confidence="high",
        patterns=[
            r"pintrk\(\s*['\"]load['\"]",
        ],
        script_src_patterns=[
            r"s\.pinimg\.com/ct/core\.js",
        ],
    ),
    Signature(
        name="Bing / Microsoft UET",
        category="ad_pixel",
        confidence="high",
        patterns=[
            r"uetq\.push",
        ],
        script_src_patterns=[
            r"bat\.bing\.com/bat\.js",
        ],
    ),
    Signature(
        name="HubSpot Ad Pixels",
        category="ad_pixel",
        confidence="high",
        script_src_patterns=[
            r"js\.hsadspixel\.net/pixels\.js",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Martech (marketing technology)
# ---------------------------------------------------------------------------
# Marketing tools — analytics CDPs, A/B testing, on-site engagement, email,
# session replay. Most ship a loader script from a known CDN and expose a
# global object on `window`. We keep two HubSpot entries: the CRM signature
# above (cookie + analytics scripts) and a separate "HubSpot Forms" entry
# here, which is medium confidence because the forms script can be embedded
# on sites that don't otherwise use HubSpot CRM.

_MARTECH: list[Signature] = [
    Signature(
        name="Segment",
        category="martech",
        confidence="high",
        patterns=[
            r"analytics\.load\(",
        ],
        script_src_patterns=[
            r"cdn\.segment\.com/analytics\.js",
        ],
    ),
    Signature(
        name="Mixpanel",
        category="martech",
        confidence="high",
        patterns=[
            r"mixpanel\.init",
        ],
        script_src_patterns=[
            r"cdn\.mxpnl\.com/libs/mixpanel",
        ],
    ),
    Signature(
        name="Amplitude",
        category="martech",
        confidence="high",
        patterns=[
            r"amplitude\.getInstance",
        ],
        script_src_patterns=[
            r"cdn\.amplitude\.com",
        ],
    ),
    Signature(
        name="Hotjar",
        category="martech",
        confidence="high",
        patterns=[
            r"hjid:",
        ],
        script_src_patterns=[
            r"static\.hotjar\.com/c/hotjar-",
        ],
    ),
    Signature(
        name="Drift",
        category="martech",
        confidence="high",
        patterns=[
            r"drift\.load",
        ],
        script_src_patterns=[
            r"js\.driftt\.com/include",
        ],
    ),
    Signature(
        name="Intercom",
        category="martech",
        confidence="high",
        patterns=[
            r"Intercom\(\s*['\"]boot['\"]",
        ],
        script_src_patterns=[
            r"widget\.intercom\.io/widget/",
        ],
    ),
    Signature(
        name="Mailchimp",
        category="martech",
        confidence="medium",
        script_src_patterns=[
            r"chimpstatic\.com",
        ],
        dom_patterns=[
            r"<form[^>]*action=['\"][^'\"]*list-manage\.com",
        ],
    ),
    Signature(
        name="Klaviyo",
        category="martech",
        confidence="high",
        patterns=[
            r"_learnq",
        ],
        script_src_patterns=[
            r"static\.klaviyo\.com/onsite/js/klaviyo\.js",
        ],
    ),
    Signature(
        name="Google Optimize",
        category="martech",
        confidence="medium",
        script_src_patterns=[
            r"googleoptimize\.com/optimize\.js",
        ],
    ),
    Signature(
        name="Optimizely",
        category="martech",
        confidence="high",
        script_src_patterns=[
            r"cdn\.optimizely\.com",
        ],
    ),
    Signature(
        name="HubSpot Forms",
        category="martech",
        confidence="medium",
        script_src_patterns=[
            r"js\.hsforms\.net/forms",
        ],
    ),
    Signature(
        name="Reo",
        category="martech",
        confidence="high",
        patterns=[
            r"Reo\.init\(",
        ],
        script_src_patterns=[
            r"static\.reo\.dev",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Salestech (sales technology)
# ---------------------------------------------------------------------------
# Sales tooling: chat-to-meeting, scheduling, ABM/intent providers, and
# inbound qualification. Several entries (Drift, Intercom) are duplicated
# from martech because the same loader script is a legitimate signal in
# both categories — the orchestrator will report them under each bucket.
# `Outreach` is `low` because outreach.io references usually appear on
# tracked outbound landing pages rather than the corporate site itself.

_SALESTECH: list[Signature] = [
    Signature(
        name="Drift",
        category="salestech",
        confidence="high",
        patterns=[
            r"drift\.load",
        ],
        script_src_patterns=[
            r"js\.driftt\.com/include",
        ],
    ),
    Signature(
        name="Intercom",
        category="salestech",
        confidence="high",
        patterns=[
            r"Intercom\(\s*['\"]boot['\"]",
        ],
        script_src_patterns=[
            r"widget\.intercom\.io/widget/",
        ],
    ),
    Signature(
        name="Qualified",
        category="salestech",
        confidence="high",
        patterns=[
            r"qualified-loader",
        ],
        script_src_patterns=[
            r"qualified\.com",
        ],
    ),
    Signature(
        name="Chili Piper",
        category="salestech",
        confidence="high",
        patterns=[
            r"ChiliPiper\.submit",
        ],
        script_src_patterns=[
            r"na-cdn\.chilipiper\.com",
        ],
    ),
    Signature(
        name="Calendly",
        category="salestech",
        confidence="medium",
        script_src_patterns=[
            r"assets\.calendly\.com/assets/external/widget\.js",
        ],
        dom_patterns=[
            r"calendly\.com/",
        ],
    ),
    Signature(
        name="6sense",
        category="salestech",
        confidence="high",
        script_src_patterns=[
            r"j\.6sc\.co",
            r"6si\.com",
        ],
    ),
    Signature(
        name="Demandbase",
        category="salestech",
        confidence="high",
        script_src_patterns=[
            r"tag\.demandbase\.com",
            r"company-target\.com",
        ],
    ),
    Signature(
        name="ZoomInfo FormComplete / WebSights",
        category="salestech",
        confidence="high",
        script_src_patterns=[
            r"ws\.zoominfo\.com",
            r"formcomplete\.zoominfo\.com",
        ],
    ),
    Signature(
        name="Apollo.io tracker",
        category="salestech",
        confidence="high",
        script_src_patterns=[
            r"assets\.apollo\.io/micro/website-tracker",
            r"apollo\.io/tracker",
        ],
    ),
    Signature(
        name="G2",
        category="salestech",
        confidence="high",
        script_src_patterns=[
            r"tracking-api\.g2\.com/attribution_tracking",
        ],
    ),
    Signature(
        name="Factors.ai",
        category="salestech",
        confidence="high",
        script_src_patterns=[
            r"app\.factors\.ai/assets/factors\.js",
        ],
    ),
    Signature(
        name="AISDR",
        category="salestech",
        confidence="high",
        script_src_patterns=[
            r"api\.aisdr\.com/scripts/",
        ],
    ),
    Signature(
        name="Outreach",
        category="salestech",
        confidence="low",
        dom_patterns=[
            r"<iframe[^>]*src=['\"][^'\"]*outreach\.io",
        ],
    ),
]


SIGNATURES: list[Signature] = [*_CRM, *_AD_PIXELS, *_MARTECH, *_SALESTECH]


def load_signatures() -> list[Signature]:
    """Return the full signature list.

    Indirected through a function so tests / experiments can monkeypatch
    or extend the library without mutating the module-level constant.
    """
    return list(SIGNATURES)


def get_signatures_by_category(category: str) -> list[Signature]:
    """Return all signatures belonging to a single category.

    Args:
        category: One of `"crm"`, `"ad_pixel"`, `"martech"`, `"salestech"`.

    Returns:
        A list of `Signature` objects in the order they were declared.
        Returns an empty list for unknown categories rather than raising,
        so callers can iterate over an arbitrary set of bucket names
        without first validating each one.
    """
    return [sig for sig in load_signatures() if sig.category == category]
