# Technographic Signals

**A production-grade technographic enrichment engine that fingerprints any company's go-to-market stack straight from their public web presence — no BuiltWith, no Clearbit, no per-lookup API fees — and writes clean, grep-able signals into HubSpot at scale.**

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Vendors](https://img.shields.io/badge/detectable_vendors-7%2C500%2B-brightgreen)
![Pipelines](https://img.shields.io/badge/detection_pipelines-DNS%20%2B%20Web%2FJS-orange)
![Tests](https://img.shields.io/badge/automated_tests-84-informational)

Point it at a HubSpot list. It visits every company's website, runs two
independent detection pipelines (DNS records + rendered-page analysis) against a
**7,500+ vendor signature library**, fuses the evidence with a probabilistic
confidence model, and writes the result back to a custom
`technographic_signals` company property:

```
CRM: HubSpot | Ad Pixels: Google Tag Manager, LinkedIn Insight Tag, Meta Pixel | Martech: Segment | Salestech: Calendly
```

That string is deterministic — fixed category order, alphabetized vendors —
so it slots directly into HubSpot list filters, workflows, and lead scoring.
Segment by "companies running Marketo but not a sales-engagement tool" the day
the run finishes.

> 📖 **[Signal Catalogue](technographics/docs/SIGNAL_CATALOGUE.md)** — the
> auto-generated inventory of every detectable vendor, the taxonomy, why
> detection is accurate, and how a client is configured to a signal subset.

## Capabilities at a glance

| Capability | What's under the hood |
|---|---|
| **7,528-vendor detection library** | 7,518 technologies imported from the maintained Wappalyzer fork ([enthec/webappanalyzer](https://github.com/enthec/webappanalyzer)) across 108 categories, plus 36 hand-curated, doc-verified signatures that override the master tier |
| **DNS detection pipeline** | Async CNAME / TXT / MX / NS / SOA / A inspection (dnspython) — catches tools with zero front-end footprint: Marketo via a `*.mktoweb.com` CNAME, SendGrid via SPF `include:`, Microsoft 365 via MX records |
| **Web/JS detection pipeline** | Script `src` URLs, `window.*` JS globals, cookies, response headers, HTML, meta tags, and final URL — static `requests` fetch with headless-Chromium (Playwright) rendering for SPAs and JS-injected tags |
| **Confidence fusion** | Both pipelines share one scoring formula (4 strength tiers, multi-pattern corroboration boost); vendors seen by both are merged via noisy-OR: `1 − (1−dns)·(1−web)` |
| **Paid-tier inference** | Curated signatures carry `paid_indicators` / `enterprise_indicators`, each annotated with *why* it signals a paid plan — spend signals, not just presence signals |
| **Per-client scoping** | A `selection.json` scopes the 7,500-vendor library down to what a client sells against (the default marketing/sales selection is 65 vendors) — pure config, zero code changes |
| **HubSpot-native I/O** | Paste a list URL straight from the HubSpot UI; the client resolves it, paginates reads, batch-fetches properties, bootstraps the custom property, and retries 429/5xx with exponential backoff (tenacity) |
| **Production run mechanics** | Parallel fetches (thread pool), a 60-second per-company budget so one hung site can't stall a batch, per-row error isolation, JSON run reports for every invocation, checkpointed chunked runs that resume after a kill |
| **Safety gates** | Dry-run previews by default; `run-from-report` replays an approved dry-run as writes-only (you ship *exactly* what you reviewed); `verify-writes` reads companies back from HubSpot and diffs them against the report |
| **Agent-native operations** | 9 documented skills with routing rules and write-approval gates ([SKILLS.md](SKILLS.md)) — an AI agent can safely operate the whole pipeline conversationally |
| **Engineered for maintainers** | 84 automated tests, a schema linter for every signature file, an idempotent upstream importer that preserves hand-edits, and a [50 KB architecture reference](ARCHITECTURE.md) |

## How it works

```
HubSpot list URL ──► hubspot_client ──► companies
                                           │  (parallel, MAX_CONCURRENT_FETCHES workers)
                     ┌─────────────────────┴─────────────────────┐
                     ▼                                           ▼
          DNS collector (dnspython)                Web fetcher (requests → Playwright fallback)
          CNAME · TXT · MX · NS · SOA · A          script srcs · JS globals · cookies · headers
                     │                             HTML · meta tags · final URL
                     ▼                                           ▼
                DNS matcher                                 Web matcher
                     │                                           │
                [Detections] ───── fusion (noisy-OR) ───── [Detections]
                                        │
                        category mapping + confidence filter
                                        │
             "CRM: … | Ad Pixels: … | Martech: … | Salestech: …"
                                        │
                     HubSpot write (technographic_signals property)
                            + JSON run report in logs/
```

Two detection engines are selectable via `DETECTION_ENGINE`:

- **`technographics`** (default) — the dual-pipeline engine above, delegating to
  the standalone [`technographics/`](technographics/) package. Scoped by default
  to a focused marketing/sales vendor set
  ([`selection.marketing_sales.json`](technographics/signatures/selection.marketing_sales.json),
  65 vendors drawn from the full catalogue). Detections map into the four output
  buckets via [src/detectors/category_map.py](src/detectors/category_map.py);
  the adapter is [src/detectors/engine.py](src/detectors/engine.py).
- **`legacy`** — the original hand-coded 4-module detector
  ([src/detectors/signatures.py](src/detectors/signatures.py)), web signals only.
  Kept as a fallback and A/B reference.

Relevant env vars: `DETECTION_ENGINE` (`technographics`|`legacy`),
`SELECTION_FILE` (path to the selection JSON), `ENABLE_DNS` (default `true`),
`DNS_TIMEOUT` (seconds, default `3.0`), `ALWAYS_RENDER` (default `false`).

### The signature library: two tiers, one taxonomy

- **Curated tier** — 36 hand-authored vendors with tight patterns verified
  against vendor docs (custom-domain setups, domain-verification tokens, email
  authentication), paid/enterprise-tier indicators, and notes explaining every
  pattern. Curated **overrides** master per vendor, so hand-tuned precision
  always wins.
- **Master tier** — 7,518 vendors imported from the maintained Wappalyzer fork,
  sharded for fast loading, covering the long tail (analytics, ecommerce, CMS,
  payments, infra). The importer is idempotent: re-imports merge new upstream
  patterns without clobbering hand-edits.

Every signal is a typed `Pattern` (`exact | contains | prefix | suffix | regex`)
with a strength tier (`definitive 1.0 / strong 0.85 / moderate 0.6 / weak 0.3`).
A schema linter (`technographics validate`) checks every signature file in both
tiers. A low-confidence hit only survives the final filter if a stronger hit
corroborates the same vendor elsewhere — precision over noise, by default.

### Recall vs. speed: `ALWAYS_RENDER`

Many high-value vendors (Microsoft Clarity, Hotjar, Demandbase, Chili Piper,
Meta Pixel…) are only visible as a `window.*` JS global or a runtime-injected
script — invisible to a static fetch. By default the fetcher renders with
Chromium only as a thin-page/SPA fallback. Set `ALWAYS_RENDER=true` to render
every page and capture JS globals, response headers, and meta tags on every
scan — much higher recall, slower batches. Real example: `gong.io` yields *zero*
signals on a static fetch and **14 vendors across all four buckets** with
`ALWAYS_RENDER=true`.

To change which vendors are detected, edit the `selected` list in the selection
file — no code change needed. To re-pull the master catalogue:
`python -m technographics.cli import-master` (run from `technographics/`).

## Built to survive real runs

This isn't a demo script — it has run against thousands-of-row HubSpot lists,
and the failure modes it handles were all hit in production:

- **Observed throughput**: a 1,650-company list written end-to-end in ~13
  minutes; static fetches run 200–1500 ms, Chromium renders 3–9 s, detection
  itself is ~1–10 ms per page.
- **Rate-limit aware**: HubSpot 429s and 5xxs retry with exponential backoff;
  non-retryable errors are logged per-row and never take down the batch.
- **Kill-resilient**: `run-chunked` checkpoints pending vs. done IDs to disk, so
  a mid-run kill resumes where it stopped instead of restarting.
- **Auditable**: every invocation writes a JSON run report
  (`logs/run_YYYYMMDD_HHMMSS.json`) with per-company signals, status, and
  errors — the authoritative record of what was (or would be) written.
- **Reviewable before it's real**: the dry-run gate runs the full pipeline
  minus the write; `run-from-report` then replays the *approved* report as
  writes only, eliminating fetch non-determinism between preview and ship.
- **Distinguishes "ran" from "never ran"**: companies with no detections get
  the literal `No signals detected`, so coverage is queryable in HubSpot.

## Agent-native by design

The repo is built so an AI agent can operate it safely in conversation:
[AGENTS.md](AGENTS.md) is the agent entry point, and [SKILLS.md](SKILLS.md)
routes user intents ("dry run this list", "approved", "retry the errors",
"did the writes land?") to 9 documented playbooks — each marked read-only or
write, with hard rules like *never write to HubSpot without explicit approval*
codified from real session experience. GTM ops as a conversational interface,
with guardrails.

## GTM engineering, demonstrated

This project is a working answer to a question every revenue team asks:
*"Can we get technographic segmentation without paying for another enrichment
seat?"* What it shows:

- **Enrichment economics** — replaces a per-lookup enrichment API with
  first-party detection: marginal cost per account is compute, not credits,
  across 7,500+ detectable technologies.
- **Signal engineering beyond the pixel** — DNS-level detection (MX, SPF,
  verification TXT records, edge CNAMEs) surfaces back-office and email
  infrastructure that page-scraping tools structurally miss, and paid-tier
  indicators turn "they have it installed" into "they pay for it".
- **CRM operations at production quality** — deterministic write formats
  designed for downstream filters/workflows, property bootstrapping, batch +
  rate-limit handling, and a verify-writes audit loop, because enrichment that
  silently didn't land is worse than no enrichment.
- **Process safety as a feature** — dry-run-first defaults, approval gates,
  replay-what-was-reviewed writes, and checkpointed resumability: the
  operational habits that let a one-person GTM team run this against a live
  CRM without fear.
- **Leverage through AI operations** — the skills layer turns the whole
  pipeline into something an agent (or a teammate who's never read the code)
  can drive with plain English.

## Stack

- Python 3.9+ (`from __future__ import annotations`; developed on 3.11)
- `requests` + `beautifulsoup4` for HTML fetching and parsing
- `playwright` (headless Chromium) for JS-rendered pages
- `dnspython` for async DNS record collection
- `hubspot-api-client` for HubSpot reads/writes
- `tenacity` for retries, `click` + `rich` for the CLI

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# Then edit .env and fill in HUBSPOT_ACCESS_TOKEN (and optionally HUBSPOT_LIST_ID).
```

## Commands

All commands are subcommands of `python -m src.cli`. Run any with `--help`
for the latest options.

### `check-list URL_OR_ID` — verify HubSpot connectivity

Read-only. Prints the resolved list ID, total company count, and the first
5 records. Use this first to confirm your token + list are wired up.

```bash
python -m src.cli check-list 12345
# or paste the URL straight from the HubSpot UI:
python -m src.cli check-list "https://app.hubspot.com/contacts/12345/objectLists/678"
```

Recognized URL shapes:

- `https://app.hubspot.com/contacts/<portal>/objectLists/<id>/...`
- `https://app.hubspot.com/lists/<portal>/list/<id>`

### `detect-one URL` — debug detection on a single site

Fetches the URL (static + Playwright fallback if needed), runs the full
detection engine, and prints fetch metadata, per-vendor evidence, and the final
formatted `technographic_signals` string. **No HubSpot calls.** Useful when
tuning signatures.

```bash
python -m src.cli detect-one https://www.drift.com --domain drift.com
# -> Ad Pixels: Google Tag Manager | Martech: Marketo Engage, Sendgrid
python -m src.cli detect-one example.com            # https:// is added automatically
python -m src.cli detect-one https://example.com --legacy   # force the legacy engine
```

### `run URL_OR_ID [--dry-run] [--limit N]` — full workflow

Reads the list, processes each company in parallel (fetch + detect with
`MAX_CONCURRENT_FETCHES` workers), and writes the formatted signals back to
each company's `technographic_signals` property. Writes a JSON run report
to `logs/run_YYYYMMDD_HHMMSS.json` and prints a console summary.

```bash
# Always start here — dry run on the first 10 companies, no writes.
python -m src.cli run 12345 --dry-run --limit 10

# Real run on the entire list.
python -m src.cli run 12345

# Drop --dry-run for the real run; --limit alone is fine for incremental testing.
python -m src.cli run 12345 --limit 100
```

The standalone `technographics` package has its own CLI as well —
`scan`, `scan-batch` (concurrent JSONL output), `stats` (library coverage),
`validate` (signature linter), and `import-master` (upstream re-import). See
[technographics/README.md](technographics/README.md).

### Output format

The string written to `technographic_signals` looks like:

```
CRM: HubSpot | Ad Pixels: Google Tag Manager, LinkedIn Insight Tag, Meta Pixel | Martech: Segment | Salestech: Calendly
```

Categories appear in this fixed order — `CRM`, `Ad Pixels`, `Martech`,
`Salestech` — vendors are sorted alphabetically within each, and empty
categories are omitted entirely. If nothing is detected, the literal string
`No signals detected` is written so you can distinguish "we ran" from
"we never ran".

## Project layout

```
src/
  config.py             # env loading, typed constants
  hubspot_client.py     # HubSpot API facade (lists, batch reads, updates, property bootstrap)
  site_fetcher.py       # requests + Playwright fallback
  detectors/
    engine.py           # adapter into the technographics package (default engine)
    category_map.py     # vendor -> {CRM, Ad Pixels, Martech, Salestech} mapping
    signatures.py       # the legacy signature library
    crm.py / ad_pixels.py / martech.py / salestech.py
  orchestrator.py       # concurrency, budgets, dry-run gate, run report
  cli.py                # entry point
technographics/         # standalone dual-pipeline detection package
  src/technographics/   # schema, loader, DNS+web collectors/matchers, fusion, CLI
  signatures/           # curated tier + 7,500-vendor master tier + selections
  docs/SIGNAL_CATALOGUE.md
skills/                 # 9 agent playbooks (one SKILL.md each)
scripts/                # chunked runner, report replay, error retry, write verification
tests/                  # detector tests against saved HTML fixtures
logs/                   # run reports + chunked-run checkpoints
```

## Tests

```bash
python -m pytest tests/ -v                                   # pipeline: fixture-based detector tests
cd technographics && PYTHONPATH=src python -m pytest tests/  # package: schema, loader, matchers, fusion, importer
```

84 test functions across the two suites, plus `technographics validate` as a
schema lint over every signature file in both tiers.

## Documentation map

- [AGENTS.md](AGENTS.md) — entry doc for agents / contributors working on the codebase.
- [SKILLS.md](SKILLS.md) — operational playbooks (which command to run for what).
- [ARCHITECTURE.md](ARCHITECTURE.md) — deep technical reference (data flow, module map, schemas, error taxonomy, extension points).
- [Signal Catalogue](technographics/docs/SIGNAL_CATALOGUE.md) — the full vendor inventory, auto-generated from the live library.

---

Built by [Ameya Deshmukh](https://github.com/ameyadeshmukh10).
