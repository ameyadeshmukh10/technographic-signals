# Technographic Signals

A workflow that pulls a list of companies from HubSpot, visits each company's
website, detects the go-to-market technologies they use (CRM, ad pixels,
marketing tools, sales tools), and writes the results back to a custom HubSpot
property called `technographic_signals`.

Detection is signature-based — no third-party enrichment API like BuiltWith
is used. The signature library lives in [src/detectors/signatures.py](src/detectors/signatures.py).

## Stack

- Python 3.11+ (also runs on 3.9 thanks to `from __future__ import annotations`)
- `requests` + `beautifulsoup4` for HTML fetching and parsing
- `playwright` (headless Chromium) as a fallback for JS-rendered pages
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

Fetches the URL (static + Playwright fallback if needed), runs all four
detectors, and prints fetch metadata, per-vendor evidence, and the final
formatted `technographic_signals` string. **No HubSpot calls.** Useful when
tuning signatures.

```bash
python -m src.cli detect-one https://www.hubspot.com
python -m src.cli detect-one example.com  # https:// is added automatically
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
    __init__.py         # DetectionHit + shared _run_detection helper
    signatures.py       # the signature library
    crm.py
    ad_pixels.py
    martech.py
    salestech.py
  orchestrator.py       # ties it all together; run report + console summary
  cli.py                # entry point
tests/
  conftest.py
  test_signatures.py    # detector tests against saved HTML fixtures
  fixtures/             # HTML fixtures (committed selectively with `git add -f`)
logs/                   # run reports written here
```

## Tests

```bash
python -m pytest tests/ -v
```

Five tests cover: each fixture's expected vendors, no false positives on a
minimal fixture, and per-bucket assertions for cross-category vendors
(Drift, Intercom).
