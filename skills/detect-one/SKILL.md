---
name: detect-one
description: "Fetch a single URL, run all four detectors, and print fetch metadata, per-vendor evidence, and the formatted technographic_signals string. No HubSpot calls."
argument-hint: "[URL]"
---

# detect-one

## When to use

- The user pastes a single website URL (not a HubSpot list).
- Debugging a signature ("why didn't we detect X on Y?").
- Confirming a new signature fires on a known-good site before adding
  it to the library.
- Investigating a `No signals detected` row from a recent run.

## When NOT to use

- The URL is actually a HubSpot list URL (use `check-list`).
- You need to detect across many URLs at once (use `dry-run` against a
  HubSpot list).

## Inputs

- `URL`: any HTTPS or HTTP URL. The fetcher normalizes — bare hostnames
  (`example.com`) get `https://` prepended automatically.

## Procedure

```bash
.venv/bin/python -m src.cli detect-one "<URL>"
```

The CLI:
1. Fetches via `SiteFetcher.fetch()` (static, with Playwright fallback
   if static is thin / failed / 4xx-5xx / a SPA shell).
2. Runs all four detectors.
3. Applies the low-confidence filter.
4. Prints:
   - Fetch summary (status, rendered?, HTML length, script-src count,
     cookie count, error).
   - A table of every detected vendor with category, confidence, and
     evidence (truncated to 200 chars per snippet, max 3 per vendor).
   - The final formatted `technographic_signals` string.

## Outputs (what to tell the user in chat)

Usually paste the CLI output as-is — Rich formatting carries through.
Then add one short interpretation:

- **If everything looks right**: "Looks healthy — N vendors detected,
  no surprises."
- **If a vendor is missing that the user expected**: identify why. Three
  common cases:
  1. The site loads it via JS but you ran static-only — try forcing
     rendered: `site_fetcher.SiteFetcher().fetch_rendered(URL)`.
  2. The signature in `signatures.py` doesn't match the actual fingerprint
     on the page — open the site, view source, grep for the vendor's
     CDN domain, compare against `signatures.py`. If different, use
     `add-signature`.
  3. The site is blocking the fetch entirely (Playwright 403) — note as
     a real-world limitation.

## When you suspect signatures are out of date

Force-render and grep the body for a known fingerprint substring:

```bash
.venv/bin/python -c "
from src.site_fetcher import SiteFetcher
fr = SiteFetcher().fetch_rendered('<URL>')
import re
for needle in ['hubspot', 'fbq', 'gtag', 'munchkin', 'pardot', 'segment.com']:
    n = len(re.findall(needle, fr.html, re.IGNORECASE))
    if n: print(f'{needle:20s} {n:3d} hits')
print('First 10 scripts:')
for s in fr.script_srcs[:10]: print(' ', s)
"
```

If you find a needle but the signature didn't fire, the pattern in
`signatures.py` is wrong → use `add-signature`.

## Caveats

- Detect-one bypasses HubSpot entirely. `HUBSPOT_ACCESS_TOKEN` still
  needs to be set (config validates it on import) but the value can be a
  stub.
- Some sites (Salesforce, UBS) block headless Chromium with HTTP 403. We
  see this as a fetch_error in rendered mode but static may still 200.
  Inspect both paths if in doubt.
