"""Import technographic fingerprints from enthec/webappanalyzer.

Two modes:

* ``--full`` (default) — write the entire upstream library (~7,500 techs) into
  ``signatures/master/`` as the project's "master tier". This is the source of
  truth for the long tail of vendors. Files are sharded by letter to keep
  diffs and ``git status`` sane.

* ``--seed-curated`` — original behaviour: merge a hand-picked list of
  vendor names into ``signatures/web/<vendor_id>.json`` so we can hand-tune
  paid-tier indicators on top of the imported patterns.

Idempotent: re-running with the same upstream commit produces byte-identical
files. Determinism is enforced by sorting dict keys and pattern lists.

Every imported pattern records its provenance in ``notes`` so we can re-pull
or audit later. The upstream repo is GPLv3 — see ``signatures/master/NOTICE.md``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "signatures" / "web"
MASTER_DIR = ROOT / "signatures" / "master"

sys.path.insert(0, str(Path(__file__).parent))
from _slugs import assign_unique, vendor_id_for  # noqa: E402

UPSTREAM_REPO = "enthec/webappanalyzer"
RAW_BASE = f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/main/src/technologies"
RAW_CATS = f"https://raw.githubusercontent.com/{UPSTREAM_REPO}/main/src/categories.json"
COMMIT_API = f"https://api.github.com/repos/{UPSTREAM_REPO}/commits/main"
REPO_URL = f"https://github.com/{UPSTREAM_REPO}"
LETTERS = list("abcdefghijklmnopqrstuvwxyz") + ["_"]
_CONFIDENCE = re.compile(r"\\;confidence:(\d+)")

# Curated seed map preserved for --seed-curated mode.
SEED_VENDORS: dict[str, list[str]] = {
    "salesforce": ["Salesforce"],
    "hubspot": ["HubSpot"],
    "pipedrive": ["Pipedrive"],
    "marketo": ["Marketo", "Adobe Marketo Engage"],
    "pardot": ["Pardot"],
    "customer_io": ["Customer.io"],
    "klaviyo": ["Klaviyo"],
    "segment": ["Segment"],
    "rudderstack": ["RudderStack"],
    "mparticle": ["mParticle"],
    "intercom": ["Intercom"],
    "zendesk": ["Zendesk", "Zendesk Chat"],
    "gorgias": ["Gorgias"],
    "front": ["Front", "Front Chat"],
    "outreach": ["Outreach"],
    "salesloft": ["Salesloft", "SalesLoft"],
    "apollo": ["Apollo.io", "Apollo"],
    "google_workspace": ["Google Workspace"],
    "microsoft_365": ["Microsoft 365", "Office 365"],
    "google_analytics": ["Google Analytics"],
    "mixpanel": ["Mixpanel"],
    "amplitude": ["Amplitude"],
    "heap": ["Heap"],
    "fullstory": ["FullStory", "Fullstory"],
    "snowflake": ["Snowflake"],
    "databricks": ["Databricks"],
    "fivetran": ["Fivetran"],
    "hightouch": ["Hightouch"],
    "cloudflare": ["Cloudflare"],
    "akamai": ["Akamai"],
    "fastly": ["Fastly"],
}


# ---------------------------------------------------------------------------
# Upstream fetch
# ---------------------------------------------------------------------------

def fetch_all_technologies(client: httpx.Client) -> dict[str, dict]:
    techs: dict[str, dict] = {}
    for letter in LETTERS:
        resp = client.get(f"{RAW_BASE}/{letter}.json")
        if resp.status_code == 200:
            techs.update(resp.json())
    return techs


def fetch_categories(client: httpx.Client) -> dict[str, dict]:
    resp = client.get(RAW_CATS)
    resp.raise_for_status()
    return resp.json()


def fetch_upstream_commit(client: httpx.Client) -> str:
    try:
        resp = client.get(COMMIT_API, headers={"Accept": "application/vnd.github+json"})
        if resp.status_code == 200:
            return resp.json().get("sha", "")
    except Exception:
        pass
    return ""


# ---------------------------------------------------------------------------
# Field-mapping primitives (shared by both modes)
# ---------------------------------------------------------------------------

def _strip_modifiers(raw: str) -> str:
    """Drop Wappalyzer ``\\;confidence:N`` / ``\\;version:`` modifier tags."""
    return raw.split("\\;")[0]


def _strength(raw: str) -> float:
    m = _CONFIDENCE.search(raw)
    if m:
        return max(0.0, min(1.0, int(m.group(1)) / 100.0))
    return 1.0


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _pat(value: str, match_type: str, strength: float, source: str, extra: str = "") -> dict:
    note = f"imported from Wappalyzer ({source})"
    if extra:
        note = f"{extra}; {note}"
    return {"value": value, "match_type": match_type, "strength": strength, "notes": note}


def _convert_dom(raw, source: str) -> list[dict]:
    """Convert upstream ``dom`` field into our DomPattern dicts.

    Upstream formats observed in the wild:
      - "selector"                       → DomPattern(selector, exists=True)
      - ["selector1", "selector2"]       → list of the same
      - {"selector": {"exists": "", "attributes": {...}, "properties": {...}, "text": "..."}}
    """
    out: list[dict] = []

    def _attr_map(d) -> dict:
        if not isinstance(d, dict):
            return {}
        return {
            str(k): _pat(_strip_modifiers(str(v)) or ".*", "regex", _strength(str(v)), source, f"dom attr {k}")
            for k, v in d.items()
        }

    if isinstance(raw, str):
        out.append({"selector": raw, "exists": True, "attributes": {}, "properties": {}, "text": None, "strength": 0.85, "notes": f"imported from Wappalyzer ({source})"})
    elif isinstance(raw, list):
        for item in raw:
            out.extend(_convert_dom(item, source))
    elif isinstance(raw, dict):
        for selector, spec in raw.items():
            if not isinstance(spec, dict):
                out.append({"selector": selector, "exists": True, "attributes": {}, "properties": {}, "text": None, "strength": 0.85, "notes": f"imported from Wappalyzer ({source})"})
                continue
            text_raw = spec.get("text")
            text_pat = None
            if text_raw is not None:
                text_pat = _pat(_strip_modifiers(str(text_raw)) or ".*", "regex", _strength(str(text_raw)), source, "dom text")
            out.append({
                "selector": selector,
                "exists": bool(spec.get("exists", True)) if "exists" not in spec else True,
                "attributes": _attr_map(spec.get("attributes")),
                "properties": _attr_map(spec.get("properties")),
                "text": text_pat,
                "strength": 0.85,
                "notes": f"imported from Wappalyzer ({source})",
            })
    return out


def _convert_probe(raw, source: str) -> dict[str, list[dict]]:
    """Upstream probe shape: ``{path: regex}`` or ``{path: {regex: ...}}``."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[dict]] = {}
    for path, spec in raw.items():
        if isinstance(spec, dict):
            for k, v in spec.items():
                value = _strip_modifiers(str(v)) or ".*"
                out.setdefault(str(path), []).append(_pat(value, "regex", _strength(str(v)), source, f"probe {path} {k}"))
        else:
            value = _strip_modifiers(str(spec)) or ".*"
            out.setdefault(str(path), []).append(_pat(value, "regex", _strength(str(spec)), source, f"probe {path}"))
    return out


def convert_web(tech_name: str, fp: dict, source_url: str) -> dict:
    """Convert one upstream technology fingerprint to our WebSignature dict.

    Captures the full upstream superset; the web matcher consumes the subset
    it knows how to test today. New fields (dom, inline scripts, text, css,
    xhr, robots, cert issuer, probe) are stored for future matcher passes.
    """
    js_globals = [_pat(k, "exact", 1.0, source_url, "js global") for k in (fp.get("js") or {})]

    script_src = [
        _pat(_strip_modifiers(raw), "regex", _strength(raw), source_url, "scriptSrc")
        for raw in _as_list(fp.get("scriptSrc"))
    ]

    inline_scripts = [
        _pat(_strip_modifiers(raw), "regex", _strength(raw), source_url, "inline script")
        for raw in _as_list(fp.get("scripts"))
    ]

    cookies = [
        _pat(k, "prefix", 1.0, source_url, "cookie")
        for k in (fp.get("cookies") or {})
    ]

    headers: dict[str, list[dict]] = {}
    for name, raw in (fp.get("headers") or {}).items():
        value = _strip_modifiers(str(raw)) or ".*"
        headers.setdefault(name.lower(), []).append(
            _pat(value, "regex", _strength(str(raw)), source_url, f"header {name}")
        )

    html = [
        _pat(_strip_modifiers(raw), "regex", _strength(raw), source_url, "html")
        for raw in _as_list(fp.get("html"))
    ]
    text = [
        _pat(_strip_modifiers(raw), "regex", _strength(raw), source_url, "text")
        for raw in _as_list(fp.get("text"))
    ]
    css = [
        _pat(_strip_modifiers(raw), "regex", _strength(raw), source_url, "css")
        for raw in _as_list(fp.get("css"))
    ]
    xhr = [
        _pat(_strip_modifiers(raw), "regex", _strength(raw), source_url, "xhr")
        for raw in _as_list(fp.get("xhr"))
    ]
    robots = [
        _pat(_strip_modifiers(raw), "regex", _strength(raw), source_url, "robots")
        for raw in _as_list(fp.get("robots"))
    ]

    meta: dict[str, list[dict]] = {}
    for name, raw in (fp.get("meta") or {}).items():
        for one in _as_list(raw):
            value = _strip_modifiers(str(one)) or ".*"
            meta.setdefault(name.lower(), []).append(
                _pat(value, "regex", _strength(str(one)), source_url, f"meta {name}")
            )

    url = [
        _pat(_strip_modifiers(raw), "regex", _strength(raw), source_url, "url")
        for raw in _as_list(fp.get("url"))
    ]

    cert_issuer = []
    if fp.get("certIssuer"):
        v = fp["certIssuer"]
        cert_issuer.append(_pat(_strip_modifiers(str(v)) or ".*", "regex", _strength(str(v)), source_url, "cert issuer"))

    return {
        "js_globals": js_globals,
        "script_src_patterns": script_src,
        "inline_script_patterns": inline_scripts,
        "cookie_patterns": cookies,
        "header_patterns": headers,
        "html_patterns": html,
        "text_patterns": text,
        "css_patterns": css,
        "xhr_patterns": xhr,
        "robots_patterns": robots,
        "meta_patterns": meta,
        "url_patterns": url,
        "cert_issuer_patterns": cert_issuer,
        "dom_patterns": _convert_dom(fp.get("dom"), source_url),
        "probe_paths": _convert_probe(fp.get("probe"), source_url),
        "paid_indicators": [],
    }


# Upstream DNS record-type → our DNSSignature field name
DNS_FIELD_MAP = {
    "A": "a_patterns",
    "MX": "mx_patterns",
    "NS": "ns_patterns",
    "TXT": "txt_patterns",
    "SOA": "soa_patterns",
    "CNAME": "cname_patterns",
}


def convert_dns(tech_name: str, fp: dict, source_url: str) -> dict:
    """Pull the ``dns`` field into our DNSSignature schema, by record type."""
    dns = fp.get("dns") or {}
    out: dict[str, list[dict]] = {field: [] for field in DNS_FIELD_MAP.values()}
    for record_type, regexes in dns.items():
        target = DNS_FIELD_MAP.get(record_type.upper())
        if not target:
            continue
        for raw in _as_list(regexes):
            value = _strip_modifiers(str(raw)) or ".*"
            out[target].append(_pat(value, "regex", _strength(str(raw)), source_url, f"DNS {record_type}"))
    return out


# ---------------------------------------------------------------------------
# Determinism helpers
# ---------------------------------------------------------------------------

def _sort_patterns(patterns: list[dict]) -> list[dict]:
    return sorted(patterns, key=lambda p: (p.get("value", ""), p.get("match_type", ""), p.get("notes", "")))


def _sort_pattern_map(m: dict[str, list[dict]]) -> dict[str, list[dict]]:
    return {k: _sort_patterns(m[k]) for k in sorted(m)}


def _normalize_web_doc(doc: dict) -> dict:
    """Sort every list/map so the on-disk JSON is byte-stable."""
    out = {"vendor_id": doc["vendor_id"]}
    list_fields = (
        "js_globals", "script_src_patterns", "inline_script_patterns",
        "cookie_patterns", "html_patterns", "text_patterns", "css_patterns",
        "xhr_patterns", "robots_patterns", "url_patterns",
        "cert_issuer_patterns", "paid_indicators",
    )
    for f in list_fields:
        if doc.get(f):
            out[f] = _sort_patterns(doc[f])
    for f in ("header_patterns", "meta_patterns", "probe_paths"):
        if doc.get(f):
            out[f] = _sort_pattern_map(doc[f])
    if doc.get("dom_patterns"):
        out["dom_patterns"] = sorted(doc["dom_patterns"], key=lambda d: d.get("selector", ""))
    return out


def _normalize_dns_doc(doc: dict) -> dict:
    out = {"vendor_id": doc["vendor_id"]}
    for f in DNS_FIELD_MAP.values():
        if doc.get(f):
            out[f] = _sort_patterns(doc[f])
    for f in ("paid_indicators", "enterprise_indicators"):
        if doc.get(f):
            out[f] = _sort_patterns(doc[f])
    return out


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# --full master import
# ---------------------------------------------------------------------------

# Custom category override for our 9 GTM-focused buckets, mapping from
# Wappalyzer category names. Anything not in this map falls through to the
# upstream display name (slugified), so the master library is still usable.
WAPP_CAT_TO_OURS = {
    "CRM": "crm",
    "Marketing automation": "marketing_automation",
    "Customer data platform": "cdp",
    "Live chat": "customer_support",
    "Support": "customer_support",
    "Help desk": "customer_support",
    "Email": "email_productivity",
    "Webmail": "email_productivity",
    "Analytics": "analytics",
    "Product analytics": "analytics",
    "Cloud services": "data_infrastructure",
    "Databases": "data_infrastructure",
    "CDN": "cdn_security",
    "Security": "cdn_security",
    "DDoS protection": "cdn_security",
    "WAF": "cdn_security",
}


def _category_for(cats: list[int], cat_lookup: dict[int, str]) -> str:
    for cid in cats:
        wapp = cat_lookup.get(cid)
        if wapp and wapp in WAPP_CAT_TO_OURS:
            return WAPP_CAT_TO_OURS[wapp]
    # Fallback: slugified first upstream category, or "uncategorized"
    if cats:
        wapp = cat_lookup.get(cats[0])
        if wapp:
            return vendor_id_for(wapp)
    return "uncategorized"


def run_full(force: bool) -> int:
    print(f"fetching upstream library from {REPO_URL} ...")
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        techs = fetch_all_technologies(client)
        upstream_cats = fetch_categories(client)
        upstream_commit = fetch_upstream_commit(client)

    if not techs:
        print("ERROR: no technologies fetched")
        return 1

    print(f"fetched {len(techs)} technologies, {len(upstream_cats)} categories, commit {upstream_commit[:10] or '?'}")

    # Build slug map (collision-safe, deterministic).
    name_to_id = assign_unique(list(techs))
    cat_lookup = {int(cid): meta.get("name", "") for cid, meta in upstream_cats.items()}

    # Buckets: shard by first char of vendor_id; DNS goes in its own file.
    web_shards: dict[str, dict[str, dict]] = {L: {} for L in LETTERS}
    dns_doc: dict[str, dict] = {}
    vendor_meta: dict[str, dict] = {}

    for name in sorted(name_to_id):
        vendor_id = name_to_id[name]
        fp = techs[name]
        source_url = f"{REPO_URL} :: {name}"

        # Web signature
        web = convert_web(name, fp, source_url)
        web["vendor_id"] = vendor_id
        web_doc = _normalize_web_doc(web)
        if any(k for k in web_doc if k != "vendor_id"):
            letter = vendor_id[0] if vendor_id and vendor_id[0].isalpha() else "_"
            web_shards.setdefault(letter, {})[vendor_id] = web_doc

        # DNS signature
        dns = convert_dns(name, fp, source_url)
        dns["vendor_id"] = vendor_id
        dns_norm = _normalize_dns_doc(dns)
        if any(k for k in dns_norm if k != "vendor_id"):
            dns_doc[vendor_id] = dns_norm

        # Vendor metadata
        cats = list(fp.get("cats") or [])
        vendor_meta[vendor_id] = {
            "vendor_id": vendor_id,
            "vendor_name": name,
            "upstream_name": name,
            "vendor_url": fp.get("website", ""),
            "category": _category_for(cats, cat_lookup),
            "wappalyzer_cats": cats,
            "implies": [vendor_id_for(_strip_modifiers(str(x))) for x in _as_list(fp.get("implies"))],
            "excludes": [vendor_id_for(_strip_modifiers(str(x))) for x in _as_list(fp.get("excludes"))],
            "requires": [vendor_id_for(_strip_modifiers(str(x))) for x in _as_list(fp.get("requires"))],
            "requires_category": list(fp.get("requiresCategory") or []),
            "cpe": fp.get("cpe", "") or "",
            "description": fp.get("description", "") or "",
            "icon": fp.get("icon", "") or "",
            "saas": bool(fp.get("saas", False)),
            "oss": bool(fp.get("oss", False)),
            "pricing": list(fp.get("pricing") or []),
            "source": "wappalyzer",
        }

    MASTER_DIR.mkdir(parents=True, exist_ok=True)

    # Write web shards (only non-empty ones, but always touch the file so re-runs are stable).
    web_dir = MASTER_DIR / "web"
    if force and web_dir.exists():
        for old in web_dir.glob("*.json"):
            old.unlink()
    web_dir.mkdir(parents=True, exist_ok=True)
    for letter in LETTERS:
        shard = web_shards.get(letter, {})
        _write_json(web_dir / f"{letter}.json", {vid: shard[vid] for vid in sorted(shard)})

    # DNS — single file
    _write_json(MASTER_DIR / "dns" / "all.json", {vid: dns_doc[vid] for vid in sorted(dns_doc)})

    # Vendor metadata
    _write_json(MASTER_DIR / "vendors.json", {vid: vendor_meta[vid] for vid in sorted(vendor_meta)})

    # Upstream categories (verbatim, sorted)
    _write_json(MASTER_DIR / "categories.json", upstream_cats)

    # Meta + notice
    # Note: no `fetched_at` timestamp so re-imports against the same upstream
    # commit produce byte-identical files. Use `git log signatures/master/_meta.json`
    # to recover fetch dates.
    _write_json(MASTER_DIR / "_meta.json", {
        "source": REPO_URL,
        "upstream_commit": upstream_commit,
        "total_technologies": len(techs),
        "total_categories": len(upstream_cats),
        "license": "GPL-3.0 (upstream)",
        "shard_strategy": "first letter of vendor_id; '_' for non-alpha",
    })
    (MASTER_DIR / "NOTICE.md").write_text(NOTICE_TEXT, encoding="utf-8")

    # Reporting
    web_with = sum(1 for s in web_shards.values() for vid in s)
    dns_with = len(dns_doc)
    print(f"wrote master/web shards: {len(LETTERS)} files, {web_with} vendors with web patterns")
    print(f"wrote master/dns/all.json: {dns_with} vendors with DNS patterns")
    print(f"wrote master/vendors.json: {len(vendor_meta)} vendors")
    return 0


NOTICE_TEXT = """# NOTICE

The contents of this directory are derived from the
[enthec/webappanalyzer](https://github.com/enthec/webappanalyzer) project,
which is distributed under the GNU General Public License v3.0 (GPLv3).

Patterns have been converted into this project's schema by
`scripts/import_wappalyzer.py --full`. Each pattern records its upstream
technology name in its `notes` field; see `_meta.json` for the upstream
commit SHA at fetch time.

If you redistribute this directory (or this repository as a whole), the GPLv3
terms apply to the imported data.
"""


# ---------------------------------------------------------------------------
# --seed-curated mode (preserved from v1)
# ---------------------------------------------------------------------------

def _key(pat: dict) -> tuple[str, str]:
    return (pat["value"], pat["match_type"])


def _merge_list(existing: list[dict], incoming: list[dict]) -> list[dict]:
    seen = {_key(p) for p in existing}
    merged = list(existing)
    for pat in incoming:
        if _key(pat) not in seen:
            merged.append(pat)
            seen.add(_key(pat))
    return merged


def _merge_map(existing: dict, incoming: dict) -> dict:
    out = {k: list(v) for k, v in existing.items()}
    for key, patterns in incoming.items():
        out[key] = _merge_list(out.get(key, []), patterns)
    return out


def _curated_merge(old: dict, new: dict) -> dict:
    merged = {"vendor_id": old["vendor_id"]}
    for fld in ("js_globals", "script_src_patterns", "cookie_patterns",
                "html_patterns", "url_patterns", "paid_indicators",
                "inline_script_patterns", "text_patterns", "css_patterns",
                "xhr_patterns", "robots_patterns", "cert_issuer_patterns"):
        merged[fld] = _merge_list(old.get(fld, []), new.get(fld, []))
    for fld in ("header_patterns", "meta_patterns", "probe_paths"):
        merged[fld] = _merge_map(old.get(fld, {}), new.get(fld, {}))
    if old.get("dom_patterns") or new.get("dom_patterns"):
        seen = {d.get("selector") for d in old.get("dom_patterns", [])}
        merged["dom_patterns"] = list(old.get("dom_patterns", [])) + [
            d for d in new.get("dom_patterns", []) if d.get("selector") not in seen
        ]
    merged["last_verified"] = old.get("last_verified")
    merged["verified_domains"] = old.get("verified_domains", [])
    if "_notes" in old:
        merged["_notes"] = old["_notes"]
    return merged


def _empty_curated(vendor_id: str) -> dict:
    return {
        "vendor_id": vendor_id,
        "js_globals": [],
        "script_src_patterns": [],
        "cookie_patterns": [],
        "header_patterns": {},
        "html_patterns": [],
        "meta_patterns": {},
        "url_patterns": [],
        "paid_indicators": [],
        "last_verified": None,
        "verified_domains": [],
    }


def _is_empty_curated(path: Path) -> bool:
    try:
        doc = json.loads(path.read_text())
    except Exception:
        return False
    lists = [v for v in doc.values() if isinstance(v, list)]
    maps = [v for v in doc.values() if isinstance(v, dict)]
    return not any(lists) and not any(maps)


def run_seed_curated(force: bool) -> int:
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        techs = fetch_all_technologies(client)
    if not techs:
        print("ERROR: no technologies fetched")
        return 1
    print(f"fetched {len(techs)} Wappalyzer technologies")

    imported, skipped = [], []
    for vendor_id, candidates in SEED_VENDORS.items():
        match = next((c for c in candidates if c in techs), None)
        path = WEB_DIR / f"{vendor_id}.json"

        if match is None:
            if not path.exists() or _is_empty_curated(path):
                doc = _empty_curated(vendor_id)
                doc["_notes"] = f"TODO: no Wappalyzer entry for {candidates}; add hand-authored web patterns if a public footprint exists."
                path.write_text(json.dumps(doc, indent=2) + "\n")
            skipped.append((vendor_id, f"no Wappalyzer entry for {candidates}"))
            continue

        source_url = f"{REPO_URL} :: {match}"
        converted = convert_web(match, techs[match], source_url)
        converted["vendor_id"] = vendor_id
        converted.setdefault("last_verified", None)
        converted.setdefault("verified_domains", [])

        if path.exists() and not force:
            old = json.loads(path.read_text())
            doc = _curated_merge(old, converted)
        else:
            doc = _empty_curated(vendor_id)
            doc.update(converted)

        path.write_text(json.dumps(doc, indent=2) + "\n")
        n = sum(len(v) for v in doc.values() if isinstance(v, list))
        n += sum(len(p) for m in (doc["header_patterns"], doc["meta_patterns"]) for p in m.values())
        imported.append((vendor_id, match, n))

    print(f"\nimported {len(imported)} vendors:")
    for vendor_id, match, n in imported:
        print(f"  {vendor_id:18s} <- {match:24s} {n} patterns")
    print(f"\nskipped {len(skipped)} vendors:")
    for vendor_id, reason in skipped:
        print(f"  {vendor_id:18s} {reason}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Import Wappalyzer fingerprints into the technographics signature library.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--full", action="store_true", help="import the entire upstream library into signatures/master/ (default)")
    mode.add_argument("--seed-curated", action="store_true", help="merge a small named vendor set into signatures/web/ (curated tier)")
    parser.add_argument("--force", action="store_true", help="overwrite existing files instead of merging (where applicable)")
    args = parser.parse_args()

    if args.seed_curated:
        return run_seed_curated(args.force)
    return run_full(args.force)


if __name__ == "__main__":
    raise SystemExit(main())
