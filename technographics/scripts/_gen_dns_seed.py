"""One-shot generator for the seeded DNS signature files.

Each vendor's DNS footprint is grounded in publicly documented custom-domain /
domain-verification / email-authentication setups. Vendors with no reliable
public DNS footprint (pure JS SDKs, internal data tools, mailbox-based sales
tools) are written with empty pattern arrays and a TODO note, per the
"do not fabricate" rule.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "signatures" / "dns"

# strength buckets snap to SignalStrength enum: 1.0 / 0.85 / 0.6 / 0.3
DEF, STRONG, MOD, WEAK = 1.0, 0.85, 0.6, 0.3


def p(value, match_type, strength, notes=""):
    return {"value": value, "match_type": match_type, "strength": strength, "notes": notes}


# vendor_id -> partial DNSSignature dict (vendor_id added automatically)
DNS: dict[str, dict] = {
    "salesforce": {
        "subdomains_to_probe": ["community", "communities", "help", "support", "my"],
        "cname_patterns": [
            p("force.com", "suffix", MOD, "Experience/Community Cloud sites CNAME to *.force.com or *.live.siteforce.com"),
            p("live.siteforce.com", "suffix", STRONG, "Experience Cloud (Site.com) custom domain target"),
            p("salesforce.com", "suffix", MOD, "Salesforce-hosted subdomain target"),
        ],
        "txt_patterns": [],
        "enterprise_indicators": [
            p("live.siteforce.com", "suffix", STRONG, "Experience Cloud custom domains require paid Digital Experiences licensing"),
        ],
        "notes": "TODO: confirm Salesforce TXT domain-verification token format.",
    },
    "hubspot": {
        "subdomains_to_probe": ["www", "info", "get", "go", "try", "learn", "blog", "email", "email1", "email2", "hs1", "hs2"],
        "cname_patterns": [
            p("hs-sites.com", "suffix", STRONG, "HubSpot CMS / landing-page connected domains CNAME to *.hs-sites.com"),
            p("hubspotpagebuilder.com", "suffix", STRONG, "HubSpot page builder connected domain target"),
            p("hubspotemail.net", "suffix", STRONG, "HubSpot email DKIM CNAME target (hs1/hs2._domainkey)"),
            p("hs-domainkey.com", "suffix", STRONG, "HubSpot email sending DKIM domain"),
        ],
        "txt_patterns": [],
        "paid_indicators": [
            p("hubspotemail.net", "suffix", STRONG, "Connected email sending domain (DKIM to hubspotemail.net) requires Marketing Hub paid tier"),
        ],
        "enterprise_indicators": [],
    },
    "pipedrive": {
        "subdomains_to_probe": [],
        "notes": "TODO: Pipedrive has no well-known DNS footprint on customer domains (app-hosted). Left empty intentionally.",
    },
    "marketo": {
        "subdomains_to_probe": ["info", "pages", "go", "try", "learn", "email", "mkto"],
        "cname_patterns": [
            p("mktoweb.com", "suffix", STRONG, "Marketo landing-page domains CNAME to <munchkin>.mktoweb.com"),
        ],
        "txt_patterns": [],
        "notes": "TODO: confirm Marketo email branding-domain CNAME suffix and any TXT verification token.",
    },
    "pardot": {
        "subdomains_to_probe": ["go", "info", "pages", "email", "try", "www2", "marketing"],
        "cname_patterns": [
            p("pardot.com", "suffix", STRONG, "Pardot tracker domain CNAMEs to *.pardot.com (e.g. go.<domain>)"),
        ],
        "txt_patterns": [],
    },
    "customer_io": {
        "subdomains_to_probe": ["email", "e", "track", "link", "news"],
        "cname_patterns": [
            p("customeriomail.com", "suffix", STRONG, "Customer.io link/open tracking domain CNAMEs to *.customeriomail.com"),
        ],
        "txt_patterns": [],
        "notes": "TODO: confirm Customer.io DKIM CNAME selector format.",
    },
    "klaviyo": {
        "subdomains_to_probe": ["email", "trk", "send", "klaviyo", "e"],
        "cname_patterns": [
            p("klaviyomail.com", "suffix", STRONG, "Klaviyo dedicated sending/click-tracking domain target"),
            p("klaviyodns.com", "suffix", STRONG, "Klaviyo DKIM/branding CNAME target"),
        ],
        "txt_patterns": [],
    },
    "segment": {
        "subdomains_to_probe": [],
        "notes": "TODO: Segment is JS-delivered; custom CDN proxy domains are rare. Left empty intentionally.",
    },
    "rudderstack": {
        "subdomains_to_probe": [],
        "notes": "TODO: RudderStack data plane is usually vendor-hosted (*.dataplane.rudderstack.com); customer-domain CNAMEs are rare.",
    },
    "mparticle": {
        "subdomains_to_probe": [],
        "notes": "TODO: mParticle is SDK-delivered; no reliable customer-domain DNS footprint.",
    },
    "intercom": {
        "subdomains_to_probe": ["help", "support", "email", "mail", "community"],
        "cname_patterns": [
            p("custom.intercom.help", "contains", DEF, "Help Center custom domain — paid feature"),
            p("mail.intercom.com", "contains", DEF, "Email custom domain target"),
            p("customers.intercom.com", "contains", STRONG, "Intercom-hosted custom subdomain target"),
        ],
        "txt_patterns": [
            p("intercom-domain-verification", "contains", STRONG, "Intercom domain-verification TXT token"),
            p("intercom-verification", "contains", STRONG, "Intercom verification TXT token variant"),
        ],
        "paid_indicators": [
            p("custom.intercom.help", "contains", DEF, "Custom Help Center domain is available on Pro+ plans"),
        ],
    },
    "zendesk": {
        "subdomains_to_probe": ["support", "help", "helpdesk", "tickets"],
        "cname_patterns": [
            p("zendesk.com", "suffix", STRONG, "Zendesk host-mapping CNAME target (<subdomain>.zendesk.com)"),
        ],
        "txt_patterns": [
            p("zendesk_verification", "contains", STRONG, "Zendesk host-mapping/domain verification TXT token"),
        ],
        "mx_patterns": [
            p("mail.zendesk.com", "contains", MOD, "Zendesk email forwarding/SPF include"),
        ],
    },
    "gorgias": {
        "subdomains_to_probe": [],
        "notes": "TODO: Gorgias is app-hosted ecommerce helpdesk; no reliable customer-domain DNS footprint.",
    },
    "front": {
        "subdomains_to_probe": [],
        "notes": "TODO: Front shared-inbox custom domain footprint unconfirmed. Left empty intentionally.",
    },
    "outreach": {
        "subdomains_to_probe": [],
        "notes": "TODO: Outreach sends through the user's own mailbox; no distinctive DNS on the customer domain.",
    },
    "salesloft": {
        "subdomains_to_probe": [],
        "notes": "TODO: Salesloft sends through the user's own mailbox; no distinctive DNS on the customer domain.",
    },
    "apollo": {
        "subdomains_to_probe": [],
        "notes": "TODO: Apollo.io sends through connected mailboxes; no distinctive DNS on the customer domain.",
    },
    "google_workspace": {
        "subdomains_to_probe": [],
        "mx_patterns": [
            p("aspmx.l.google.com", "suffix", DEF, "Google Workspace primary MX host"),
            p("googlemail.com", "suffix", STRONG, "Google Workspace alternate MX host suffix"),
        ],
        "txt_patterns": [
            p("include:_spf.google.com", "contains", DEF, "Google Workspace SPF include"),
            p("google-site-verification=", "contains", WEAK, "Google domain verification - WEAK: also set by Search Console and other Google products, not Workspace-specific"),
        ],
    },
    "microsoft_365": {
        "subdomains_to_probe": ["autodiscover", "lyncdiscover", "enterpriseregistration"],
        "mx_patterns": [
            p("mail.protection.outlook.com", "suffix", DEF, "Microsoft 365 Exchange Online MX host"),
        ],
        "cname_patterns": [
            p("autodiscover.outlook.com", "contains", STRONG, "Microsoft 365 Autodiscover CNAME target"),
        ],
        "txt_patterns": [
            p("include:spf.protection.outlook.com", "contains", DEF, "Microsoft 365 SPF include"),
            p("MS=ms", "prefix", MOD, "Microsoft 365 domain-verification TXT token prefix"),
        ],
    },
    "google_analytics": {
        "subdomains_to_probe": [],
        "notes": "TODO: Google Analytics is JS-only; no DNS footprint. Detect via web pipeline.",
    },
    "mixpanel": {
        "subdomains_to_probe": [],
        "notes": "TODO: Mixpanel is JS/SDK-only; detect via web pipeline.",
    },
    "amplitude": {
        "subdomains_to_probe": [],
        "notes": "TODO: Amplitude is JS/SDK-only; custom tracking-domain CNAMEs are rare. Detect via web pipeline.",
    },
    "heap": {
        "subdomains_to_probe": [],
        "notes": "TODO: Heap is JS-only; detect via web pipeline.",
    },
    "fullstory": {
        "subdomains_to_probe": [],
        "notes": "TODO: FullStory is JS-only; detect via web pipeline.",
    },
    "snowflake": {
        "subdomains_to_probe": [],
        "notes": "TODO: Snowflake is internal data infra; no customer-domain DNS footprint.",
    },
    "databricks": {
        "subdomains_to_probe": [],
        "notes": "TODO: Databricks is internal data infra; no customer-domain DNS footprint.",
    },
    "fivetran": {
        "subdomains_to_probe": [],
        "notes": "TODO: Fivetran is internal data infra; no customer-domain DNS footprint.",
    },
    "hightouch": {
        "subdomains_to_probe": [],
        "notes": "TODO: Hightouch is internal data infra; no customer-domain DNS footprint.",
    },
    "cloudflare": {
        "subdomains_to_probe": [],
        "ns_patterns": [
            p("ns.cloudflare.com", "suffix", DEF, "Cloudflare-managed DNS nameservers (<name>.ns.cloudflare.com)"),
        ],
        "cname_patterns": [
            p("cdn.cloudflare.net", "suffix", STRONG, "Cloudflare CNAME-setup (partial) target"),
        ],
    },
    "akamai": {
        "subdomains_to_probe": ["www"],
        "cname_patterns": [
            p("edgekey.net", "suffix", DEF, "Akamai edge CNAME target"),
            p("edgesuite.net", "suffix", DEF, "Akamai edge CNAME target (legacy)"),
            p("akamaiedge.net", "suffix", DEF, "Akamai edge CNAME target"),
            p("akamai.net", "suffix", STRONG, "Akamai edge CNAME target"),
        ],
    },
    "fastly": {
        "subdomains_to_probe": ["www"],
        "cname_patterns": [
            p("fastly.net", "suffix", DEF, "Fastly edge CNAME target (e.g. *.global.ssl.fastly.net)"),
        ],
    },
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fields = [
        "cname_patterns", "txt_patterns", "mx_patterns", "ns_patterns",
        "a_patterns", "paid_indicators", "enterprise_indicators",
    ]
    for vendor_id, partial in DNS.items():
        doc = {"vendor_id": vendor_id}
        doc["subdomains_to_probe"] = partial.get("subdomains_to_probe", [])
        for f in fields:
            doc[f] = partial.get(f, [])
        doc["last_verified"] = None
        doc["verified_domains"] = []
        if "notes" in partial:
            doc["_notes"] = partial["notes"]
        (OUT / f"{vendor_id}.json").write_text(
            json.dumps(doc, indent=2) + "\n", encoding="utf-8"
        )
    print(f"wrote {len(DNS)} DNS signature files to {OUT}")


if __name__ == "__main__":
    main()
