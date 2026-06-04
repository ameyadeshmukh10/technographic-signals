# technographics

Dual-pipeline technographic vendor detection with a shared signature library.

> 📖 **[Signal Catalogue](docs/SIGNAL_CATALOGUE.md)** — the full inventory of all
> 7,500+ detectable vendors, the 12-domain taxonomy, why detection is accurate,
> and how a client is configured. Regenerate with
> `PYTHONPATH=src python scripts/gen_signal_catalogue.py`.

Two independent detection pipelines share one vendor taxonomy:

1. **DNS pipeline** — inspects CNAME / TXT / MX / NS / A / SOA records
   (custom-domain setups, domain-verification tokens, email authentication,
   edge CNAMEs, SOA-keyed hosting providers).
2. **JS/Web pipeline** — inspects JS globals, script `src`s, cookies, response
   headers, HTML, meta tags, and the final URL of a rendered page.

A vendor (e.g. *Intercom*) can have signatures in **both** pipelines. They live
in separate files (`signatures/dns/intercom.json`, `signatures/web/intercom.json`)
but reference the same stable `vendor_id`, and a fusion step combines their
signals.

## Two tiers: curated + master

The library has two tiers, loaded together by default:

- **Curated** (`signatures/{dns,web}/<vendor_id>.json`) — ~31 hand-authored
  vendors with tight signatures, paid-tier indicators, subdomain probe lists,
  and notes explaining each pattern. These are the vendors we care about most;
  patterns are verified against vendor docs.

- **Master** (`signatures/master/`) — 7,500+ vendors imported from
  [enthec/webappanalyzer](https://github.com/enthec/webappanalyzer) (GPLv3).
  Sharded by letter: 27 files under `master/web/` plus one `master/dns/all.json`.
  Covers the long tail (analytics, ecommerce, CMS, payment, infra) and gives
  the detector breadth out of the box.

**Curated overrides master** at the vendor level: if both tiers describe
`intercom`, the curated signature wins as a whole (so hand-tuned
`paid_indicators` always survive). The `Vendor.source` field is set to
`"curated"` or `"wappalyzer"` so you can tell where each entry came from.

A `selection.json` file lets you scope detection to just the vendors a
customer cares about — huge perf win at scan time (7,500 → 50). The
forthcoming onboarding/config agent will write this file.

## Architecture

```
              signatures/
   +-----------------------------+---------------------------+
   |  curated tier (~31)         |  master tier (~7,500)     |
   |  dns/<vendor_id>.json       |  master/dns/all.json      |
   |  web/<vendor_id>.json       |  master/web/<letter>.json |
   |  vendors.json categories.json   master/vendors.json     |
   +--------------+--------------+--------------+------------+
                  |                             |
                  v                             v
                 loader.py  ->  SignatureLibrary
                 (curated overrides master per vendor_id;
                  optional selection filter)
                          |
                          v
   domain --> dns_collector       web_collector <-- domain
                 (dnspython)         (Playwright)
                          |              |
                       DNSRecords      PageData
                          |              |
                     dns_matcher      web_matcher
                          |              |
                     [Detection]    [Detection]
                              \\    //
                              fusion.py  (noisy-OR)
                                   |
                              [Detection]
                                   |
                                 cli.py
                       (scan, scan-batch, stats,
                        validate, import-master)
```

Both matchers share one confidence formula:

```
base  = max(strength of matched patterns)
boost = min(0.15, 0.05 * (num_matched_patterns - 1))
final = min(1.0, base + boost)
```

Fusion uses noisy-OR for vendors detected in both pipelines:
`confidence = 1 - (1 - dns_conf) * (1 - web_conf)`.

## Install

```bash
pip install -e .            # core (DNS + matching + CLI)
pip install -e '.[web]'     # adds Playwright for the web collector
playwright install chromium # one-time browser download (web pipeline only)
pip install -e '.[dev]'     # pytest + pytest-asyncio
```

Python 3.9+.

## Quickstart

```bash
# single domain, both pipelines, fused
technographics scan stripe.com --fuse

# DNS only, JSON output
technographics scan stripe.com --dns-only --json

# web only
technographics scan stripe.com --web-only

# batch, 10 concurrent workers -> JSONL
technographics scan-batch domains.txt --out results.jsonl --workers 10

# library coverage (curated/master split, top 20 categories)
technographics stats
technographics stats --vendors           # full per-vendor table (long!)
technographics stats --selection signatures/selection.example.json

# scope detection to a chosen vendor subset (the future onboarding-agent seam)
technographics scan stripe.com --selection signatures/selection.example.json
technographics scan stripe.com --curated-only   # skip master, ~31 vendors

# lint every signature file against the schema (both tiers)
technographics validate

# (re)import the full Wappalyzer library into signatures/master/
technographics import-master              # idempotent
technographics import-master --force      # wipe master/web/ first

# legacy: merge a small named vendor set into curated signatures/web/
technographics import-wappalyzer --seed-curated
```

Run the same things from source without installing:

```bash
PYTHONPATH=src python -m technographics.cli scan stripe.com --dns-only
```

## Schema

A `Pattern` is `{value, match_type, strength, notes}` where `match_type` is one
of `exact | contains | suffix | prefix | regex`. Matching is case-insensitive
and strips leading/trailing dots (except `regex`, which runs against the raw,
case-folded candidate). `strength` snaps to the nearest `SignalStrength` bucket
(`1.0 / 0.85 / 0.6 / 0.3`).

**Curated tier:**

- `signatures/vendors.json` — `{vendor_id: {vendor_name, vendor_url, category,
  subcategory, typical_buyer, company_stage, price_tier, typically_replaces,
  typically_replaced_by}}`
- `signatures/categories.json` — `{category_id: {name, description}}`
- `signatures/dns/<vendor_id>.json` — one `DNSSignature`
- `signatures/web/<vendor_id>.json` — one `WebSignature`

**Master tier** (imported by `scripts/import_wappalyzer.py --full`):

- `signatures/master/vendors.json` — all 7,500+ vendor metadata entries (one
  dict, keyed by vendor_id; includes `wappalyzer_cats`, `implies`, `excludes`,
  `cpe`, `description`, `icon`, `saas`, `oss`, `pricing`, `source`)
- `signatures/master/categories.json` — full upstream taxonomy (108 categories)
- `signatures/master/dns/all.json` — `{vendor_id: DNSSignature dict}` (~80 entries)
- `signatures/master/web/<letter>.json` — 27 sharded files keyed by vendor_id
- `signatures/master/_meta.json` — `{source, upstream_commit, total_*}`
- `signatures/master/NOTICE.md` — GPLv3 attribution to enthec/webappanalyzer

The schema captures upstream's full signal surface (`dom_patterns`,
`inline_script_patterns`, `text_patterns`, `css_patterns`, `xhr_patterns`,
`robots_patterns`, `cert_issuer_patterns`, `probe_paths`). The current
matchers act on the subset they understand (js, scriptSrc, cookies, headers,
html, meta, url for web; A/MX/TXT/NS/SOA/CNAME for DNS). Future matcher
passes for DOM / inline scripts / probes won't require a re-import.

See `src/technographics/schema.py` for the full dataclass definitions.

## Contributing signatures

1. **One vendor per file.** `vendor_id` is lowercase `snake_case` and **stable**
   — never rename it after creation (add aliases instead).
2. Add the vendor's metadata to `signatures/vendors.json` first; its `category`
   must exist in `signatures/categories.json`.
3. Create `signatures/dns/<vendor_id>.json` and/or `signatures/web/<vendor_id>.json`.
   If you can't confidently produce patterns for a pipeline, write the file with
   **empty arrays** and a top-level `"_notes"` explaining why — **do not fabricate**.
4. Ground DNS patterns in vendor "custom domain" / "domain verification" /
   email-authentication docs. Ground web patterns in
   [enthec/webappanalyzer](https://github.com/enthec/webappanalyzer) or vendor
   SDK docs, and record the source in each pattern's `notes`.
5. Every `paid_indicators` / `enterprise_indicators` pattern **must** have a
   non-empty `notes` explaining *why* it signals a paid/enterprise tier.
6. Run `technographics validate` after every batch of edits.

### Importing from Wappalyzer

`scripts/import_wappalyzer.py` fetches the latest enthec/webappanalyzer
fingerprints and converts them to our schema (`js` → `js_globals`, `scriptSrc` →
`script_src_patterns`, `cookies` → `cookie_patterns`, etc.), stripping
`\;confidence:N` / `\;version:` modifiers and mapping confidence to `strength`.
It is **idempotent** and **merges** by default — new patterns are appended,
existing entries (and their hand-edited `notes`) are preserved. Use `--force` to
overwrite. The source technology name is captured in every imported pattern's
`notes`.

## Layout

```
src/technographics/
  schema.py         # dataclasses, enums, Pattern.matches(), (de)serialization
  loader.py         # signature files -> SignatureLibrary
  dns_matcher.py    # DNSRecords + DNSMatcher + shared confidence formula
  web_matcher.py    # PageData + WebMatcher
  dns_collector.py  # dnspython async record collection
  web_collector.py  # Playwright page-data collection
  fusion.py         # noisy-OR merge of DNS + Web detections
  cli.py            # Click entrypoint
signatures/
  vendors.json  categories.json
  dns/<vendor_id>.json  web/<vendor_id>.json         # curated tier
  selection.example.json                              # subset for onboarding agent
  master/                                             # imported (~7,500 vendors)
    vendors.json  categories.json  _meta.json  NOTICE.md
    dns/all.json   web/<letter>.json
scripts/
  import_wappalyzer.py   # --full master import OR --seed-curated (legacy)
  _slugs.py              # slug + override map (curated <-> upstream name)
  validate_signatures.py # schema linter for both tiers
  _gen_dns_seed.py       # generator for the curated DNS seed
tests/                   # schema, loader, matchers, fusion, importer + fixtures
```

## Tests

```bash
PYTHONPATH=src python -m pytest tests/ -v
```
