---
name: retry-fetch-errors
description: "Refetch the fetch-error rows from a saved run report with a longer per-request timeout. Writes successful detections back to HubSpot; leaves persistent failures untouched."
argument-hint: "[REPORT_PATH] [--timeout SECONDS] [--dry-run]"
---

# retry-fetch-errors

## When to use

- A real-run had non-zero `fetch_error` rows and the user wants to
  recover the Playwright-timeout ones.
- The user says "retry the errors" / "retry fetch errors" / "try them
  with a longer timeout".
- Before going to your stakeholders with the dataset, as a polish pass
  on the slower sites.

## When NOT to use

- The report's only errors are DNS / TLS / connection-refused failures.
  Those are permanent — no timeout bump will help. Tell the user; don't
  burn cycles.
- You're in the middle of an active `run-chunked` invocation. Let that
  finish first.

## Inputs

- `REPORT_PATH` (optional): defaults to the most recent
  `logs/run_*.json`.
- `--timeout SECONDS` (default 30): bumps both
  `REQUEST_TIMEOUT_SECONDS` (used by `requests` and Playwright `goto`)
  and the Playwright `networkidle` constant.
- `--workers N` (default 5): concurrent fetch workers.
- `--dry-run`: refetch + detect but don't write.

## Procedure

```bash
# Default — most recent report, 30s timeout:
.venv/bin/python scripts/retry_errors.py --timeout 30

# Specific report:
.venv/bin/python scripts/retry_errors.py logs/run_20260514_160123.json --timeout 30

# Sanity check first:
.venv/bin/python scripts/retry_errors.py --timeout 30 --dry-run
```

The script:
1. Loads the report.
2. Selects rows where `status == "succeeded"` AND `error` is set.
3. Batch-reads those companies from HubSpot to get fresh `website` /
   `domain` (the report only has `domain`).
4. Refetches each in parallel (5 workers), with the bumped timeout.
5. For successful refetches with signals, writes the new
   `technographic_signals` to HubSpot.
6. Companies that still error are left untouched in HubSpot.

## Outputs (what to tell the user in chat)

1. **Refetch counters**: refetched, now succeeded with signals, still
   failing.
2. **Per-company ok/FAIL list** — useful so the user can see *which*
   sites were recoverable.
3. **Categorize the still-failing ones** — DNS dead / TLS broken /
   harder bot detection — and mark whether anything else is worth
   trying (usually no).

## Realistic expectations

From the session: of 49 fetch errors on list 1911 (15 Playwright
timeouts, 14 DNS, 11 TLS, 4 conn refused, 2 HTTP/2, 3 other), only the
15 Playwright timeouts had a chance of being recovered. The 31 permanent
failures stayed failed.

## What can go wrong

- **Some sites are slow even at 30 s.** Try 45 or 60 s on a second pass
  for the residual handful — but at that point, the data is probably
  not worth the wait.
- **Timeout bump cascades.** Increasing `REQUEST_TIMEOUT_SECONDS` also
  increases the `requests` connect timeout. Sites with bad DNS now take
  3× longer to fail. Annoying, not broken.

## A second sweep

You can run the script again with the same report — it'll re-refetch
only the ones still erroring in the *original* report. To narrow further
to "still erroring after first retry", run a fresh full pipeline pass
(`run-from-report --no-skip-errors` won't help; you'd want a new dry-run
or a targeted detect-one).
