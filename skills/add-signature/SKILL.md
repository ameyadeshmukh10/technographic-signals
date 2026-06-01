---
name: add-signature
description: "Procedure for adding a new vendor fingerprint to the signature library. Use when a real-world site uses a tool we don't yet detect."
argument-hint: "[vendor name] [example URL where it appears]"
---

# add-signature

## When to use

- The user says "we missed X on Y" / "add a signature for X".
- During detection debugging, you found a script src or inline JS
  pattern that uniquely identifies a vendor.
- A new MarTech/SalesTech tool launches and you want it covered.

## When NOT to use

- The vendor IS detected but you want to change its category — that's a
  smaller in-place edit to `signatures.py`, not a full add-signature
  workflow.
- You only have a single weak signal (a single word like
  "demandbase") — too risky. Wait for a confident unique fingerprint
  (CDN domain, inline JS call, cookie name).

## Inputs

- **Vendor canonical name**, exactly as it should appear in the
  `technographic_signals` HubSpot string. Examples already in the
  library: `HubSpot`, `Salesforce / Pardot`, `Meta Pixel`,
  `Google Ads / gtag`. Match the slash-separated style if applicable.
- **Category**: one of `crm`, `ad_pixel`, `martech`, `salestech`.
- **At least one example URL** where the vendor appears, ideally one
  that's small / fast to fetch.

## Procedure

### Step 1. Confirm the fingerprint

Run `detect-one` against the example URL. Identify the unique
script-src pattern, body pattern, dom pattern, or cookie pattern that
isn't already in `signatures.py`. Use the "force-render + grep" pattern
from the `detect-one` skill if needed.

### Step 2. Choose confidence level

- **high** — the pattern is essentially unique to this vendor
  (e.g., `js.hsadspixel.net/pixels.js` only ships with HubSpot Ad Pixels).
- **medium** — probable but could collide; OK with a single signal but
  worth corroboration.
- **low** — only worth reporting when something else corroborates it
  in the same page (Outreach iframe references are the example).

### Step 3. Add to `signatures.py`

Open [`src/detectors/signatures.py`](../../src/detectors/signatures.py).
Find the right category list (`_CRM`, `_AD_PIXELS`, `_MARTECH`,
`_SALESTECH`) and add:

```python
Signature(
    name="<canonical name>",
    category="<crm|ad_pixel|martech|salestech>",
    confidence="<high|medium|low>",
    script_src_patterns=[
        r"<escaped\.regex>",
    ],
    patterns=[             # body / inline JS — omit if none
        r"<escaped\.regex>",
    ],
    dom_patterns=[         # raw HTML markup — omit if none
        r"<escaped\.regex>",
    ],
    cookie_patterns=[      # cookie names — omit if none
        r"^cookiename$",
    ],
),
```

Rules:
- Use `re.IGNORECASE` semantics — do NOT embed `(?i)` flags in the
  pattern strings; the matcher applies the flag.
- Escape `.` in domain names: `js\.example\.com`.
- Two same-name signatures across categories is fine (Drift,
  Intercom, HubSpot Forms vs HubSpot) — they each produce a hit in
  their own bucket.

### Step 4. Add a fixture and test (if confidence ≥ medium)

If you're confident enough that this should be regression-tested,
create a fixture under
[`tests/fixtures/`](../../tests/fixtures/) containing a minimal HTML
page with the fingerprint, then either extend an existing test in
[`tests/test_signatures.py`](../../tests/test_signatures.py) or add a
new one. Mirror the structure of the existing four fixtures.

### Step 5. Verify

```bash
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m src.cli detect-one "<example URL>"
```

Both should now show the vendor.

### Step 6. (Optional) Re-run recent lists

If we've already processed a HubSpot list in this session and the new
signature is one a meaningful fraction of those companies might use,
offer to re-run with the user's approval. Use `run-from-report` if a
dry-run report still exists, or `run-chunked` if the list is big.

## Output (what to tell the user in chat)

1. Confirm the fingerprint you used (the regex, where it came from).
2. Confirm the test suite passes.
3. Show the `detect-one` output proving the new signature fires.
4. Suggest the re-run if applicable.

## Examples of signatures added this way

- `HubSpot Ad Pixels` — `js\.hsadspixel\.net/pixels\.js` (high) — caught
  35 hits on the 1700-row list 1911 that the prior library missed.
- `Reo` — `static\.reo\.dev` + body pattern `Reo\.init\(` (high).
- `G2` — `tracking-api\.g2\.com/attribution_tracking` (high).
- `Apollo.io tracker` (modified) — added
  `assets\.apollo\.io/micro/website-tracker` because the legacy
  `apollo\.io/tracker` pattern no longer matched their current loader URL.
