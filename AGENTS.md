# AGENTS.md — Technographic Signals

This file is the entry point for any AI agent (Claude, or anything that
reads `AGENTS.md`) working on this project. Read it before doing
anything destructive.

## What this project does

The pipeline pulls a list of companies from HubSpot, visits each
company's website, signature-matches the HTML/JS for go-to-market
technologies (CRM, ad pixels, marketing tools, sales tools), and writes
the result back to a custom HubSpot company property,
`technographic_signals`, formatted as:

```
CRM: HubSpot | Ad Pixels: Meta Pixel, LinkedIn Insight Tag | Martech: Segment | Salestech: Calendly
```

Detection is **signature-based, not third-party-enriched** — no BuiltWith,
no Wappalyzer. The signature library lives at
[`src/detectors/signatures.py`](src/detectors/signatures.py) and is the
brain of the system. Adding/improving signatures is the most common
maintenance task.

Two fetch paths exist: a fast static path via `requests`, and a
Playwright/Chromium fallback for JS-rendered sites. Fallback triggers when
the static response is small (<50 KB), is a SPA shell, returns 4xx/5xx, or
errors out. Some enterprise sites (Salesforce, UBS) block headless
Chromium — accept this as a real-world limit; don't try to bypass.

## Layout

```
technographic_signals/
├── AGENTS.md, SKILLS.md         ← entry docs (you are here)
├── README.md                    ← human-facing intro
├── skills/                      ← one SKILL.md per named playbook
├── scripts/                     ← helper scripts the skills shell out to
├── src/
│   ├── cli.py                   ← `python -m src.cli {check-list, detect-one, run}`
│   ├── orchestrator.py          ← Orchestrator.run / run_companies / ensure_property
│   ├── hubspot_client.py        ← thin facade over hubspot-api-client
│   ├── site_fetcher.py          ← requests + Playwright fallback
│   ├── detectors/
│   │   ├── signatures.py        ← the signature library
│   │   ├── crm.py, ad_pixels.py, martech.py, salestech.py
│   │   └── __init__.py          ← DetectionHit + _run_detection
│   └── config.py                ← env loading; HUBSPOT_ACCESS_TOKEN required
├── tests/                       ← pytest, fixtures, conftest
├── logs/
│   ├── run_*.json               ← one per pipeline invocation
│   └── checkpoints/             ← list_<id>.json checkpoints for chunked runs
└── .env, .env.example, .gitignore, requirements.txt
```

## Setup (first run only)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# Fill in HUBSPOT_ACCESS_TOKEN (and optionally HUBSPOT_LIST_ID).
```

## Credentials

- The only required secret is `HUBSPOT_ACCESS_TOKEN` (a HubSpot Private
  App token). Set it in `.env`; `.env` is gitignored.
- `HUBSPOT_CLIENT_SECRET` may be present but is not currently read by
  the code (it'd only matter for OAuth flows).
- If a token is ever pasted in chat, treat it as compromised and rotate
  via HubSpot Settings → Integrations → Private Apps.

## How to run the pipeline

**Read [SKILLS.md](SKILLS.md) before invoking any command.** That file
is the single source of truth for which mode to pick. The short version:

| You want to… | Skill |
|---|---|
| Sanity-check connectivity / list size | `check-list` |
| Preview what would be written | `dry-run` |
| Write to HubSpot | `run-end-to-end` |
| Write a large list (>500) | `run-chunked` |
| Re-write from an existing dry-run JSON | `run-from-report` |
| Retry the fetch-error rows with longer timeouts | `retry-fetch-errors` |
| Debug detection on one URL | `detect-one` |
| Add a new vendor signature | `add-signature` |
| Verify HubSpot writes landed | `verify-writes` |

## Decision defaults (codified from session experience)

These are the rules an agent should follow unless the user overrides them:

1. **Bare URL with no other instruction** → run `check-list` only and
   present a numbered menu of options (`dry-run`, `run-end-to-end`,
   `run-chunked` if >500). Do NOT auto-run.
2. **Lists with >500 companies** → offer `run-chunked` as the first
   menu option. A single foreground `cli run` is unlikely to finish before
   the harness kills it.
3. **"approved" after a dry-run summary** → use `run-from-report` on the
   most recent `logs/run_*.json`, not a fresh fetch. Preserves the exact
   data the user reviewed; avoids Playwright non-determinism between
   dry-run and real-run (we lost Simpro on list 1911 this way).
4. **Fetch errors** → default behavior is to write `"No signals detected"`
   to those rows. User can opt out with "skip fetch errors", in which case
   call `run-from-report --skip-errors=true` (the default) so the existing
   HubSpot value is preserved.
5. **Real writes** → always require explicit user confirmation
   (`approved`, `go`, or equivalent) before dropping `--dry-run`. The only
   exception is when the user has explicitly waived the gate ("skip dry
   run", "just run it end to end").
6. **Spot-check after a real run** → use `verify-writes` to read back 3-5
   companies. Confirms property is live on HubSpot, not just in our report.

## Where state lives

- **Run reports** — `logs/run_YYYYMMDD_HHMMSS.json`. Authoritative
  record of what was processed in a given invocation, including per-
  company `signals_string`, `error`, and `status`.
- **Checkpoints** — `logs/checkpoints/list_<id>.json`. Created by
  `scripts/run_chunked.py`. Tracks pending vs. done IDs so a kill mid-run
  can resume.
- **Environment** — `.env`. Never committed.

## Testing

```bash
.venv/bin/python -m pytest tests/ -q
```

Tests cover the signature library against four saved HTML fixtures.
When adding new signatures, follow the `add-signature` skill — it
includes the test-fixture step.

## Things that are intentionally out of scope

- Playwright stealth (for sites that block headless Chromium).
- DNS / TLS-cert fallbacks (dead domains and broken HTTPS are real-world
  data quality issues, not bugs).
- Scheduling / cron — invoke skills manually for now.
- An `--offset` flag on `src.cli run`. The chunked runner gives us the
  same outcome.
