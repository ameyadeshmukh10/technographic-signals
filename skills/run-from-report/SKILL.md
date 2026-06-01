---
name: run-from-report
description: "Write technographic_signals to HubSpot using the per-company signals_string from a saved dry-run report. No refetch. Use after a dry-run has been reviewed and approved."
argument-hint: "[REPORT_PATH] [--skip-errors/--no-skip-errors] [--limit N]"
---

# run-from-report

## When to use

- The user just approved a dry-run summary you posted. **This is the
  default skill for "approved" after a dry-run** — preferred over
  `run-end-to-end` because it writes exactly what the user saw.
- The user said "approved, skip fetch errors" or "B" (selecting the
  skip-errors option from the menu the dry-run skill posts).
- You need to re-write a list that already has a clean dry-run on disk
  and you don't want to refetch.

## When NOT to use

- No dry-run report exists. Use `run-end-to-end` or `run-chunked`.
- More than ~24 h has passed since the dry-run — fingerprints may have
  drifted on the live sites; redo the dry-run.

## Inputs

- `REPORT_PATH`: path to a `logs/run_*.json` file (you should have
  captured this when you ran the dry-run).
- `--skip-errors` (default true): skip rows where the dry-run had a
  fetch error. Leaves the live HubSpot value untouched for those.
- `--no-skip-errors`: write `"No signals detected"` to fetch-error rows
  too. The dry-run skill should have offered this choice in its
  approval menu.
- `--limit N`: only write the first N eligible rows.
- `--dry-run`: print what would be written, don't write.

## Procedure

```bash
# Default — write only the clean-fetch rows:
.venv/bin/python scripts/run_from_report.py logs/run_<timestamp>.json

# Write everything including fetch-error "No signals detected":
.venv/bin/python scripts/run_from_report.py logs/run_<timestamp>.json --no-skip-errors

# Preview only:
.venv/bin/python scripts/run_from_report.py logs/run_<timestamp>.json --dry-run --limit 5
```

The script:
1. Loads the saved report.
2. Filters to rows where `status == "succeeded"` and `signals_string`
   is present (and `error is None` if `--skip-errors`).
3. Calls `client.update_company` for each. Sequential; HubSpot's
   ~19 req/sec burst limit is respected by the retry decorator in
   `HubSpotClient`.

## Outputs (what to tell the user in chat)

1. **Counters**: how many rows were written, how many were skipped (and
   why — fetch error vs. limit cap).
2. **Pointer** to the source report and the duration.
3. **A `verify-writes` suggestion** with 3–5 random names from the
   written set.

## Why prefer this over `run-end-to-end` after a dry-run?

- **No drift**. Playwright's `networkidle` is a real-time race; rendered
  fetches catch different scripts between runs. On list 1911 we lost
  Simpro (13 vendors in dry-run → 0 in real-run due to a transient 15 s
  timeout). `run-from-report` writes exactly the data the user reviewed.
- **Faster**. ~10 ms per write × N rows. A 1650-row list took 13 min
  (single-threaded writes with retry backoff).
- **Safer**. The user has already approved the exact strings.

## What can go wrong

- **Report has stale company IDs** (rare; HubSpot rarely deletes IDs).
  Each affected write logs `update_failed company_id=...` and continues.
- **Property renamed** in HubSpot — the bootstrap call
  (`ensure_property_exists`) catches the "missing" case and creates it.
  Doesn't catch "renamed".
