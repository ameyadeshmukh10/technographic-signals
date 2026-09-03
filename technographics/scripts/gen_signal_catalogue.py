"""Generate docs/SIGNAL_CATALOGUE.md from the live signature library.

Deterministic: re-running against the same library produces byte-identical
output (no wall-clock timestamp; sorted everywhere). Re-run after every
`import-master` so the catalogue never drifts.

    cd technographics && PYTHONPATH=src python scripts/gen_signal_catalogue.py
"""

from __future__ import annotations

import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIG = ROOT / "signatures"
MASTER = SIG / "master"
OUT = ROOT / "docs" / "SIGNAL_CATALOGUE.md"

# --- 12-domain taxonomy over the 108 Wappalyzer categories -------------------
# Every Wappalyzer category name maps to exactly one domain. Two synthetic
# display categories ("Sales engagement", "Data infrastructure") hold curated
# vendors that have no Wappalyzer category.
DOMAINS: list[tuple[str, str, list[str]]] = [
    ("Sales & CRM", "Pipeline, accounts, and revenue tooling.",
     ["CRM", "Customer data platform", "Appointment scheduling", "Sales engagement"]),
    ("Marketing Automation & Messaging", "Lifecycle, email, and campaign engines.",
     ["Marketing automation", "Email", "Webmail", "Cart abandonment", "Loyalty & rewards",
      "Referral marketing", "Affiliate programs", "Fundraising & donations"]),
    ("Advertising & Tag Management", "Paid media pixels, retargeting, and tag containers.",
     ["Advertising", "Retargeting", "Tag managers"]),
    ("Analytics & Optimization", "Measurement, experimentation, and personalization.",
     ["Analytics", "RUM", "A/B Testing", "Personalisation", "Segmentation", "Surveys",
      "User onboarding", "SEO", "Content curation", "Form builders"]),
    ("Customer Support & Engagement", "Chat, helpdesk, reviews, and on-site engagement.",
     ["Live chat", "Reviews", "Comment systems", "Translation", "Accessibility"]),
    ("Commerce", "Storefronts, payments, fulfilment, and post-purchase.",
     ["Ecommerce", "Ecommerce frontends", "Shopify apps", "Shopify themes", "Payment processors",
      "Buy now pay later", "Returns", "Shipping carriers", "Fulfilment", "Reservations & delivery",
      "Ticket booking", "Cross border ecommerce"]),
    ("Content & Web Platforms", "CMS, site builders, and content systems.",
     ["CMS", "Page builders", "WordPress plugins", "WordPress themes", "Drupal themes", "Blogs",
      "Wikis", "Documentation", "Photo galleries", "Static site generator", "Message boards",
      "LMS", "DMS", "Digital asset management", "Editors", "Rich text editors", "Feed readers"]),
    ("Web Development & Frameworks", "Front-end libraries, frameworks, and media.",
     ["JavaScript libraries", "JavaScript frameworks", "JavaScript graphics", "Web frameworks",
      "UI frameworks", "Mobile frameworks", "Programming languages", "Font scripts", "Widgets",
      "Maps", "Video players", "Livestreaming", "Media servers", "Augmented reality",
      "Geolocation", "Feature management", "Webcams"]),
    ("Infrastructure, Hosting & CDN", "Where and how the site is served.",
     ["CDN", "Hosting", "Hosting panels", "PaaS", "IaaS", "Web servers", "Web server extensions",
      "Reverse proxies", "Load balancers", "Caching", "Performance", "Containers", "CI",
      "Network storage", "Network devices", "Control systems", "Operating systems", "Databases",
      "Database managers", "Remote access", "Domain parking", "Data infrastructure"]),
    ("Security, Privacy & Identity", "Protection, consent, and authentication.",
     ["Security", "Cookie compliance", "Authentication", "SSL/TLS certificate authorities",
      "Browser fingerprinting", "Cryptominers"]),
    ("Business Operations", "Back-office and engineering operations.",
     ["ERP", "Accounting", "Recruitment & staffing", "Issue trackers", "Development", "Search engines"]),
    ("Miscellaneous", "Everything else.", ["Miscellaneous"]),
]

# curated snake_case category -> display category used in the taxonomy
CURATED_CAT = {
    "sales_engagement": "Sales engagement",
    "data_infrastructure": "Data infrastructure",
    "marketing_automation": "Marketing automation",
    "advertising": "Advertising",
    "crm": "CRM",
    "cdp": "Customer data platform",
    "customer_support": "Live chat",
    "analytics": "Analytics",
    "email_productivity": "Webmail",
    "cdn_security": "CDN",
    "erp": "ERP",
}

# Well-known vendor_ids surfaced first in "notable" lists (deterministic).
MARQUEE = {
    "hubspot", "salesforce", "pipedrive", "marketo", "pardot", "klaviyo", "mailchimp",
    "braze", "iterable", "customer_io", "activecampaign", "constant_contact", "sendgrid",
    "segment", "rudderstack", "mparticle", "tealium", "google_analytics", "mixpanel",
    "amplitude", "heap", "hotjar", "fullstory", "contentsquare", "microsoft_clarity",
    "optimizely", "vwo", "ab_tasty", "google_ads", "google_ads_conversion_tracking",
    "google_tag_manager", "facebook_pixel", "linkedin_insight_tag", "linkedin_ads",
    "tiktok_pixel", "twitter_ads", "reddit_ads", "pinterest_conversion_tag",
    "microsoft_advertising", "snap_pixel", "quora_pixel", "criteo", "the_trade_desk",
    "outbrain", "taboola", "6sense", "demandbase", "zoominfo", "leadfeeder",
    "clearbit_reveal", "albacross", "warmly", "koala", "gong", "drift", "intercom",
    "zendesk", "qualified", "chili_piper", "calendly", "typeform", "g2", "factors_ai",
    "reo", "aisdr", "shopify", "woocommerce", "magento", "bigcommerce", "stripe",
    "paypal", "adyen", "braintree", "klarna", "afterpay", "wordpress", "drupal", "wix",
    "squarespace", "webflow", "contentful", "react", "vue_js", "angular", "next_js",
    "jquery", "bootstrap", "tailwind_css", "cloudflare", "akamai", "fastly", "amazon_cloudfront",
    "amazon_web_services", "google_cloud", "vercel", "netlify", "nginx", "apache",
    "onetrust", "cookiebot", "recaptcha", "cloudflare_bot_management", "auth0", "okta",
    "snowflake", "databricks", "fivetran", "hightouch", "atlassian_statuspage",
    "amazon_ses", "mailgun", "twilio_sendgrid", "intercom_articles",
}

NOTABLE_PER_CATEGORY = 12


def read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def build_universe():
    catname = {int(k): v["name"] for k, v in read_json(MASTER / "categories.json").items()}
    master = read_json(MASTER / "vendors.json")
    curated = read_json(SIG / "vendors.json")

    # web / dns coverage sets (master shards + curated files)
    web, dns = set(), set()
    for f in glob.glob(str(MASTER / "web" / "*.json")):
        web |= set(read_json(Path(f)))
    for f in glob.glob(str(SIG / "web" / "*.json")):
        web.add(read_json(Path(f))["vendor_id"])
    dns |= set(read_json(MASTER / "dns" / "all.json"))
    for f in glob.glob(str(SIG / "dns" / "*.json")):
        d = read_json(Path(f))
        if any(d.get(k) for k in ("cname_patterns", "txt_patterns", "mx_patterns",
                                  "ns_patterns", "a_patterns", "soa_patterns")):
            dns.add(d["vendor_id"])

    vendors: dict[str, dict] = {}
    for vid, m in master.items():
        wc = m.get("wappalyzer_cats") or []
        cat = catname.get(wc[0]) if wc else "Miscellaneous"
        vendors[vid] = {"id": vid, "name": m.get("vendor_name", vid), "category": cat,
                        "curated": False}
    for vid, c in curated.items():
        cat = CURATED_CAT.get(c.get("category", ""), vendors.get(vid, {}).get("category") or "Miscellaneous")
        # curated overrides: keep master's Wappalyzer category for ids in master,
        # but tag curated; curated-only ids use the mapped display category.
        if vid in vendors:
            vendors[vid]["curated"] = True
        else:
            vendors[vid] = {"id": vid, "name": c.get("vendor_name", vid), "category": cat,
                            "curated": True}
    for v in vendors.values():
        v["web"] = v["id"] in web
        v["dns"] = v["id"] in dns
    return vendors, catname


def notable(cat_vendors: list[dict]) -> list[str]:
    def rank(v):
        return (0 if v["curated"] else 1, 0 if v["id"] in MARQUEE else 1, v["name"].lower())
    picked = sorted(cat_vendors, key=rank)[:NOTABLE_PER_CATEGORY]
    return [f"{v['name']}{'★' if v['curated'] else ''}" for v in picked]


# --------------------------------------------------------------------------- #
# Prose blocks
# --------------------------------------------------------------------------- #

def header(total, web_n, dns_n, curated_n, ncat, commit):
    return f"""# Technographic Signal Catalogue

> The complete inventory of technologies this agent can detect on a company's
> web presence, the taxonomy that organizes them, why the detection is accurate,
> and how the system is configured for a specific client.

## Executive summary

| Metric | Count |
|---|---:|
| **Total vendors in the library** | **{total:,}** |
| Detectable via the **JS / Web pipeline** | {web_n:,} |
| Detectable via the **DNS pipeline** | {dns_n} |
| Hand-curated, high-precision signatures | {curated_n} |
| Wappalyzer categories | {ncat} |
| Top-level domains (this document's taxonomy) | {len(DOMAINS)} |

Two independent detection pipelines share one vendor taxonomy:

1. **DNS pipeline** — inspects CNAME / TXT / MX / NS / SOA / A records. Catches
   infrastructure and back-office tools that leave no front-end trace — e.g.
   Marketo via a `*.mktoweb.com` CNAME, SendGrid via an SPF `include:sendgrid.net`,
   Microsoft 365 via `*.mail.protection.outlook.com`.
2. **JS / Web pipeline** — inspects script `src` URLs, JS `window.*` globals,
   cookies, response headers, HTML, and meta tags from the rendered page.

A vendor can be detected by **both** pipelines; results are fused. A third path —
**portal probes** — extends the web matcher to internal ERP systems that never
appear on the marketing site (see *Portal probes — the ERP bucket*). The two
tiers of signatures — a hand-curated core and the imported Wappalyzer master
library — are merged at load time, with **curated signatures overriding** the
master entry for the same vendor (so hand-tuned precision always wins).

_Generated from the live library (upstream commit `{commit}`). Regenerate with
`PYTHONPATH=src python scripts/gen_signal_catalogue.py`._
"""


HOW_IT_WORKS = """## How detection works (high level)

For each target domain the agent runs two collectors and two matchers, then fuses
the results:

```
                 ┌─────────────── domain ───────────────┐
                 ▼                                       ▼
        DNS collector (dnspython)            Web collector (Playwright / requests)
        A · MX · TXT · NS · SOA · CNAME      script srcs · window globals · cookies
                 │                            headers · HTML · meta tags
                 ▼                                       ▼
           DNS matcher                              Web matcher
                 │                                       │
            [Detection]  ──────── fusion (noisy-OR) ──────  [Detection]
                                       │
                                  ranked detections
```

**Signature schema.** Every signal is a `Pattern` = `{value, match_type, strength}`:

- **5 match types** — `exact`, `contains`, `prefix`, `suffix`, `regex`
  (case-insensitive; DNS values are dot-normalized).
- **4 strength buckets** — `definitive (1.0)`, `strong (0.85)`, `moderate (0.6)`,
  `weak (0.3)`.

A vendor groups many patterns across channels (script srcs, JS globals, cookie
prefixes, headers, HTML, meta, and the DNS record types).

**Confidence per vendor.** `base = max(strength of matched patterns)`, plus a
small corroboration boost `0.05 × (matches − 1)` capped at `+0.15`, clamped to
`1.0`. More independent signals → higher confidence, but a single definitive
signal already scores high.

**Fusion.** When DNS and Web both flag a vendor, confidences combine with a
**noisy-OR**: `1 − (1 − dns) × (1 − web)` — agreement across independent
pipelines pushes confidence up.

**Rendering enrichment.** The web collector can execute the page (headless
Chromium) and enumerate `window.*`, capturing tools that inject themselves at
runtime (Microsoft Clarity, Hotjar, Demandbase, Meta Pixel…) and are invisible to
a static HTML fetch.

Implementation lives in `schema.py`, `dns_matcher.py`, `web_matcher.py`,
`fusion.py`, the collectors, and the integration adapter `src/detectors/engine.py`.
"""

WHY_ACCURATE = """## Why it is high-accuracy

- **Independent, corroborating channels.** A vendor is rarely judged on one clue:
  script src + JS global + cookie + DNS record all vote. The confidence formula
  rewards agreement, and fusion rewards agreement *across pipelines* (a web hit
  plus a DNS hit is near-certain).
- **DNS signals are hard to fake.** CNAME/MX/TXT/SOA records reflect real
  infrastructure choices (email vendor, CDN, marketing-domain setup). They can't
  be spoofed by a tag a competitor copied, and they reveal tools with no
  front-end footprint at all.
- **Precise patterns, not keyword soup.** Patterns are anchored regexes on script
  hosts, cookie *name prefixes*, exact `window` globals, and specific DNS targets
  — chosen to fire on the vendor and nothing else. Strength weighting demotes
  shared/ambiguous signals (e.g. a generic `gtag.js` loader is weak; the
  `AW-` conversion id is strong).
- **Rendered window-globals.** Executing the page catches runtime-injected tools
  that static scanners miss, materially raising recall on modern JS sites.
- **Tier indicators.** Selected vendors carry `paid` / `enterprise` indicators
  (e.g. a custom Intercom Help Center domain implies a paid plan), adding
  qualitative signal beyond "present / absent".
- **Curated overrides + provenance.** A hand-tuned core overrides the bulk import
  per-vendor; every imported pattern records its source in `notes`, so signals
  are auditable and improvable.
- **Guardrails.** A schema linter (`technographics validate`) checks every
  signature file, and the package ships a test suite (96 tests) covering the
  matchers, loader, fusion, and importer.
"""


def taxonomy_section(vendors, catname):
    # category -> domain
    cat2dom = {}
    declared = set()
    for dom, _desc, catlist in DOMAINS:
        for c in catlist:
            cat2dom[c] = dom
            declared.add(c)
    # warn if any real Wappalyzer category is unmapped
    missing = sorted(set(catname.values()) - declared)
    # group vendors by domain/category
    grouped: dict[str, dict[str, list[dict]]] = {d[0]: {} for d in DOMAINS}
    for v in vendors.values():
        dom = cat2dom.get(v["category"], "Miscellaneous")
        grouped.setdefault(dom, {}).setdefault(v["category"], []).append(v)

    lines = ["## The signal taxonomy",
             "",
             f"All {len(catname)} Wappalyzer categories (plus two curated additions — "
             "*Sales engagement*, *Data infrastructure*) roll up into "
             f"{len(DOMAINS)} domains. ★ marks a hand-curated signature. "
             "Full per-vendor lists are in [Appendix A](#appendix-a--full-vendor-enumeration).",
             ""]
    if missing:
        lines.append(f"> ⚠ Unmapped categories (placed in Miscellaneous): {', '.join(missing)}")
        lines.append("")

    for dom, desc, catlist in DOMAINS:
        cats = grouped.get(dom, {})
        dom_total = sum(len(vs) for vs in cats.values())
        dom_web = sum(1 for vs in cats.values() for v in vs if v["web"])
        dom_dns = sum(1 for vs in cats.values() for v in vs if v["dns"])
        lines.append(f"### {dom}  ·  {dom_total:,} vendors")
        lines.append(f"_{desc}_  (web: {dom_web:,} · DNS: {dom_dns})")
        lines.append("")
        lines.append("| Category | Vendors | DNS | Notable |")
        lines.append("|---|---:|---:|---|")
        # order categories as declared, then any extras alphabetically
        ordered = [c for c in catlist if c in cats] + sorted(c for c in cats if c not in catlist)
        for c in ordered:
            vs = cats[c]
            dnsn = sum(1 for v in vs if v["dns"])
            lines.append(f"| {c} | {len(vs):,} | {dnsn or ''} | {', '.join(notable(vs))} |")
        lines.append("")
    return "\n".join(lines)


GTM_LENS = """## The GTM lens (how the configured agent buckets signals)

The marketing/sales configuration collapses the master taxonomy into **five
output buckets** written to HubSpot's `technographic_signals` property. Because
the master library files ad pixels under *Analytics/Advertising* and intent tools
under *Analytics/Marketing automation*, a per-vendor override map
(`src/detectors/category_map.py`) re-routes them:

- **CRM** — Salesforce, HubSpot, Pipedrive
- **Ad Pixels** — Meta Pixel, Google Ads, Google Ads Conversion, Google Tag
  Manager, LinkedIn Insight Tag, LinkedIn Ads, TikTok, X/Twitter, Reddit,
  Pinterest, Microsoft Advertising (Bing UET), Snap, Quora
- **Martech** — Marketo, Pardot, Klaviyo, Mailchimp, Braze, Iterable, Customer.io,
  ActiveCampaign, Constant Contact, ConvertKit, Drip, SendGrid · Segment,
  RudderStack, mParticle, Tealium · Google Analytics, Mixpanel, Amplitude, Heap,
  Hotjar, FullStory, Contentsquare, Microsoft Clarity · Optimizely, VWO, AB Tasty ·
  Typeform
- **Salestech** — Outreach, Salesloft, Apollo · 6sense, Demandbase, ZoomInfo,
  Leadfeeder, Clearbit Reveal, Albacross, Warmly, Koala, Gong · Drift, Intercom,
  Qualified · Chili Piper, Calendly · G2, Factors.ai, Reo.dev, AiSDR
- **ERP** — Oracle E-Business Suite, Oracle Fusion Cloud ERP, Oracle PeopleSoft,
  Oracle JD Edwards EnterpriseOne. Never on the marketing page — surfaced by the
  portal-probe step (see *Portal probes — the ERP bucket*).

This ~70-vendor set is the default `selection.marketing_sales.json`. A different
client gets a different selection (next section) — the five buckets and the
override map are reused. One such alternative ships with the package:
`selection.erp.json` scopes detection to just the four probe-enabled ERP suites,
for clients that sell against ERP estates rather than GTM tooling.
"""


PORTAL_PROBES_INTRO = """## Portal probes — the ERP bucket

Enterprise ERP suites are invisible to both the web and DNS pipelines: they run
on internal hosts, never on the marketing site the scanner fetches. A third
detection path — **probe-then-fetch** — closes that gap for systems that expose a
web login on a conventionally-named host.

A vendor opts in by declaring **both** `subdomains_to_probe` (in its
`dns/<vendor>.json` — candidate hosts) and `probe_paths` (in its
`web/<vendor>.json` — well-known paths). For each `https://<sub>.<domain><path>`
the engine issues a cheap static GET (no Chromium) and matches **only that
vendor's** web signature against the response. Two guards keep catch-all servers
from producing false positives:

1. **4xx/5xx responses are discarded.**
2. **A match whose only evidence is the probe URL we constructed is discarded** —
   *unless* the server organically redirected the probe off the probed site (e.g.
   `erp.bk.rw` → `*.fa.ocs.oraclecloud.com`), which is genuine evidence. A
   redirect back to the apex/`www` marketing site does not count.

The per-vendor probe budget is capped (`MAX_PROBES_PER_VENDOR`, path-major: the
primary path covers every candidate host before secondary paths). All failures
(NXDOMAIN, TLS, timeout, firewall) are swallowed — probing never blocks the main
pipelines. Detections carry `source="probe"` and land in the **ERP** bucket. The
signatures key on **structural** artifacts (auth cookies, servlet paths, SaaS pod
hostnames), never editorial mentions — a page that says "we run PeopleSoft" does
not match — and their fingerprints are disjoint, so the suites are told apart.

**Reach and limits.** The probe finds portals only on *conventionally-named*
hosts; a custom host (e.g. `gullnet.<domain>`) is missed by blind guessing but is
identified with certainty when the pipeline is pointed straight at it
(`detect-one <url>`). Behind a firewall or SSO, nothing is externally detectable.
The internal data-plane tools around an ERP (ETL, replication, archiving) leave
no public footprint and are not signature-detectable — they need enrichment data.
"""


def portal_probes_section(vendors):
    rows = []
    for f in sorted(glob.glob(str(SIG / "web" / "*.json"))):
        w = read_json(Path(f))
        paths = w.get("probe_paths") or {}
        if not paths:
            continue
        vid = w["vendor_id"]
        dns = read_json(SIG / "dns" / f"{vid}.json") if (SIG / "dns" / f"{vid}.json").is_file() else {}
        subs = dns.get("subdomains_to_probe") or []
        if not subs:
            continue
        # definitive (strength 1.0) signals, across the channels the matcher reads
        signals = []
        for key in ("cookie_patterns", "html_patterns", "url_patterns", "script_src_patterns"):
            for p in w.get(key) or []:
                if float(p.get("strength", 0)) >= 1.0:
                    signals.append(p["value"])
        name = vendors.get(vid, {}).get("name", vid)
        sub_str = ",".join(subs[:6]) + ("…" if len(subs) > 6 else "")
        rows.append((name, vid, "`" + "`, `".join(signals[:3]) + "`" if signals else "—",
                     f"`{sub_str}` @ `{'`, `'.join(paths)}`"))

    out = [PORTAL_PROBES_INTRO, f"### Probe-enabled vendors ({len(rows)})", "",
           "| Vendor | vendor_id | Confirmed by (definitive signals) | Probe hosts / paths |",
           "|---|---|---|---|"]
    for name, vid, sig, hp in rows:
        out.append(f"| {name} | `{vid}` | {sig} | {hp} |")
    out.append("")
    return "\n".join(out)


def dns_section(vendors):
    master = read_json(MASTER / "dns" / "all.json")
    rows = []
    for vid in sorted(master):
        d = master[vid]
        types = [k.replace("_patterns", "").upper()
                 for k in ("soa_patterns", "txt_patterns", "ns_patterns", "cname_patterns",
                           "mx_patterns", "a_patterns") if d.get(k)]
        name = vendors.get(vid, {}).get("name", vid)
        rows.append((name, vid, "/".join(types)))
    # curated dns
    crows = []
    for f in sorted(glob.glob(str(SIG / "dns" / "*.json"))):
        d = read_json(Path(f))
        types = [k.replace("_patterns", "").upper()
                 for k in ("soa_patterns", "txt_patterns", "ns_patterns", "cname_patterns",
                           "mx_patterns", "a_patterns") if d.get(k)]
        if not types:
            continue
        name = vendors.get(d["vendor_id"], {}).get("name", d["vendor_id"])
        crows.append((name, d["vendor_id"], "/".join(types)))

    out = ["## DNS signature catalogue",
           "",
           "DNS detection resolves a domain's records and matches them against vendor "
           "patterns. Record types and what they typically reveal:",
           "",
           "- **SOA / NS** — managed-DNS and hosting providers (the authoritative nameserver).",
           "- **MX** — the email platform (Google Workspace, Microsoft 365, …).",
           "- **TXT** — domain-verification and SPF includes (email senders, SaaS verifications).",
           "- **CNAME** — vendor-hosted custom subdomains (marketing pages, help centers, trackers).",
           "",
           f"### Curated DNS signatures ({len(crows)})",
           "Hand-authored, GTM-focused, with paid/enterprise tier hints where applicable.",
           "",
           "| Vendor | vendor_id | Records |",
           "|---|---|---|"]
    for name, vid, t in sorted(crows):
        out.append(f"| {name} | `{vid}` | {t} |")
    out += ["",
            f"### Master DNS signatures ({len(rows)})",
            "Imported from Wappalyzer — predominantly hosting/email/CDN providers.",
            "",
            "| Vendor | vendor_id | Records |",
            "|---|---|---|"]
    for name, vid, t in rows:
        out.append(f"| {name} | `{vid}` | {t} |")
    out.append("")
    return "\n".join(out)


CONFIG_SECTION = """## Configuration — how a client is onboarded

The agent ships with thousands of signatures, but a given client only cares about
a slice. Scoping is done with a **selection file** — a JSON list of `vendor_id`s:

```json
{ "selected": ["hubspot", "marketo", "segment", "6sense", "google_tag_manager", "..."] }
```

The loader honors it (`load_library(selection=…)`), so the matchers, the
`stats`/`scan` CLI, and the HubSpot run all operate on just that subset. Scoping
is also a big speed win (65 vendors vs 7,500) and reduces false positives.

### The configuration agent

The **configuration agent** turns a plain-English client brief into a
`selection.<client>.json`. It reads the taxonomy in this document and chooses the
`vendor_id`s that matter for that client. It is the automation layer on top of the
selection seam (today selections are hand-authored; the agent generates them).

**What the agent needs in its prompt:**

| Input | Why it matters |
|---|---|
| **Client profile** — who they are, what they sell | Anchors which categories are relevant (e.g. a CDP vendor cares about *Customer data platform* + *Analytics* + *Tag managers*). |
| **ICP / target accounts** — industry, size, region | Picks the right tier of tools (enterprise vs SMB, ecommerce vs B2B SaaS). |
| **Named competitors & "replaces" targets** | Forces those exact `vendor_id`s into the selection so the client can spot displacement opportunities. |
| **GTM motion** — PLG / sales-led / ABM / ecommerce | Weights buckets: ABM → intent/visitor-ID; ecommerce → Klaviyo/Shopify/reviews; PLG → product analytics. |
| **Domains/categories of interest** from the taxonomy | Lets the agent include whole categories wholesale (e.g. "all of *Advertising* + *Tag managers*"). |
| **Must-have / must-exclude vendors** | Hard constraints the agent honors verbatim. |
| **Precision vs recall preference** | Narrow marquee set vs the full long tail of a category. |
| **Render budget** (speed vs JS-global recall) | Whether to enable always-render (catches runtime-injected tools, slower). |

**Example prompt:**

> "Configure for **Acme**, a B2B revenue-intelligence platform selling to RevOps
> at mid-market SaaS. Competitors: Gong, Clari, Salesloft, Outreach. ABM motion.
> I care about CRM, marketing automation, CDP/analytics, ad pixels, and
> sales-intent/visitor-ID tools. Must include 6sense, Demandbase, ZoomInfo.
> Precision over recall. Optimize for JS-global recall (render on)."

**Example output** (`selection.acme.json`):

```json
{
  "client": "acme",
  "render": "always",
  "selected": [
    "salesforce", "hubspot",
    "marketo", "pardot", "hubspot",
    "segment", "rudderstack", "google_analytics", "amplitude", "mixpanel",
    "google_tag_manager", "google_ads", "facebook_pixel", "linkedin_insight_tag",
    "6sense", "demandbase", "zoominfo", "gong", "salesloft", "outreach",
    "clearbit_reveal", "leadfeeder", "warmly", "koala", "qualified", "chili_piper"
  ]
}
```

Run it: `SELECTION_FILE=…/selection.acme.json ALWAYS_RENDER=true python -m src.cli run <LIST>`.
"""


def appendix_a(vendors, catname):
    cat2dom = {}
    for dom, _d, catlist in DOMAINS:
        for c in catlist:
            cat2dom[c] = dom
    grouped: dict[str, dict[str, list[dict]]] = {d[0]: {} for d in DOMAINS}
    for v in vendors.values():
        dom = cat2dom.get(v["category"], "Miscellaneous")
        grouped.setdefault(dom, {}).setdefault(v["category"], []).append(v)

    out = ["## Appendix A — full vendor enumeration",
           "",
           "Every vendor in the library, grouped Domain → Category. ★ = curated. "
           "Collapsed by domain; expand to read.",
           ""]
    for dom, _desc, catlist in DOMAINS:
        cats = grouped.get(dom, {})
        total = sum(len(v) for v in cats.values())
        out.append(f"<details>\n<summary><b>{dom}</b> — {total:,} vendors</summary>\n")
        ordered = [c for c in catlist if c in cats] + sorted(c for c in cats if c not in catlist)
        for c in ordered:
            names = sorted((f"{v['name']}{'★' if v['curated'] else ''}" for v in cats[c]),
                           key=str.lower)
            out.append(f"**{c}** ({len(names)}): " + ", ".join(names) + "\n")
        out.append("</details>\n")
    return "\n".join(out)


APPENDIX_B = """## Appendix B — reference

**Match types:** `exact`, `contains`, `prefix`, `suffix`, `regex`
(case-insensitive; DNS dot-normalized).
**Strength buckets:** definitive `1.0`, strong `0.85`, moderate `0.6`, weak `0.3`.

**File layout:**
```
signatures/
  vendors.json  categories.json          # curated taxonomy
  dns/<id>.json  web/<id>.json            # curated signatures (one per vendor)
  selection.marketing_sales.json          # default GTM selection
  selection.erp.json                       # ERP-only selection (probe-enabled suites)
  master/
    vendors.json  categories.json  _meta.json
    dns/all.json  web/<letter>.json       # imported Wappalyzer library (sharded)
```

**Refresh the master library:** `python -m technographics.cli import-master`
then regenerate this doc: `PYTHONPATH=src python scripts/gen_signal_catalogue.py`.
"""


def main() -> int:
    vendors, catname = build_universe()
    total = len(vendors)
    web_n = sum(1 for v in vendors.values() if v["web"])
    dns_n = sum(1 for v in vendors.values() if v["dns"])
    curated_n = sum(1 for v in vendors.values() if v["curated"])
    meta = read_json(MASTER / "_meta.json")
    commit = (meta.get("upstream_commit") or "")[:10] or "unknown"

    parts = [
        header(total, web_n, dns_n, curated_n, len(catname), commit),
        HOW_IT_WORKS,
        WHY_ACCURATE,
        taxonomy_section(vendors, catname),
        GTM_LENS,
        dns_section(vendors),
        portal_probes_section(vendors),
        CONFIG_SECTION,
        appendix_a(vendors, catname),
        APPENDIX_B,
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
    print(f"wrote {OUT}  ({total:,} vendors · {web_n:,} web · {dns_n} dns · {curated_n} curated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
