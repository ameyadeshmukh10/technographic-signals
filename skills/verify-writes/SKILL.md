---
name: verify-writes
description: "Spot-check that technographic_signals writes landed in HubSpot. Reads N rows from a saved report and diffs against the live HubSpot value."
argument-hint: "[REPORT_PATH] [--sample N] [--names \"A,B\"]"
---

# verify-writes

## When to use

- Always offer after a write run (`run-end-to-end`, `run-from-report`,
  `run-chunked`, `retry-fetch-errors`). Catches drift between "we
  reported success" and "the property is actually live".
- The user asks "did the writes land" / "verify the last run".
- Building confidence before showing the dataset to a stakeholder.

## When NOT to use

- No write run has happened yet. Nothing to verify.
- The report is more than a few days old — live values may have been
  overwritten by a later run; mismatches don't indicate a bug.

## Inputs

- `REPORT_PATH`: path to a `logs/run_*.json` file. Usually the most
  recent.
- `--sample N` (default 5): random sample size. 3–5 is the right number
  for human-readable output.
- `--names "Foo,Bar,Baz"` (optional): specific company names to check.
  Overrides `--sample`.
- `--show-misses` (optional): only print mismatched rows. Useful when
  spot-checking dozens.

## Procedure

```bash
# Random 5 spot-checks:
.venv/bin/python scripts/verify_writes.py logs/run_<timestamp>.json --sample 5

# Specific picks (the heaviest stacks, for example):
.venv/bin/python scripts/verify_writes.py logs/run_<timestamp>.json --names "Drata,HungerRush,Carta"

# Bulk check, show only mismatches:
.venv/bin/python scripts/verify_writes.py logs/run_<timestamp>.json --sample 30 --show-misses
```

The script:
1. Loads the saved report.
2. Picks N rows (random or by name).
3. For each, fetches the live `technographic_signals` value from HubSpot
   via `client._client.crm.companies.basic_api.get_by_id`.
4. Compares to the report's `signals_string`.
5. Prints a Rich table: company, match status, expected, actual.
6. Exits 0 if all match (zero mismatches/errors), 1 otherwise.

## Outputs (what to tell the user in chat)

1. **The summary line** at the bottom of the script: matches /
   mismatches / errors.
2. **If mismatches exist** — list each one and propose causes:
   - Stale report (an earlier run already overwrote the value).
   - Property renamed in HubSpot.
   - Update API call failed silently (check the orchestrator's
     `update_failed` log lines for that company ID).
3. **A `verify-writes --sample 20 --show-misses`** suggestion if the
   user wants a deeper check.

## Examples of past spot-checks

- After list 1917: verified Workstream → `CRM: HubSpot | Ad Pixels:
  Google Tag Manager, Meta Pixel, Reddit Pixel`.
- After list 1911: verified Drata (12 vendors), HungerRush (14), LILT
  AI (10) — all matched.

## Caveats

- The script makes one HubSpot `get_by_id` per row. ~50 ms each. At
  `--sample 20` that's 1 s. At `--sample 1000` it's 50 s and counts
  against the daily quota — don't.
- Random sampling uses Python `random` with no seed. If you want
  reproducibility, pass `--names`.
