---
name: dry-run
description: "Run the full pipeline against a HubSpot list without writing to HubSpot. Produces a logs/run_*.json report with per-company signals_string for review. Use before any first-time write."
argument-hint: "[URL_OR_ID] [--limit N]"
---

# dry-run

## When to use

- The user says "dry run X", "preview X", "what would land for X".
- Before the first real run against any list — safety gate.
- When the user is iterating on signatures and wants to see what fires.

## When NOT to use

- The user has explicitly waived the gate ("skip dry run", "just run it
  end to end") — use `run-end-to-end` directly.
- For lists >500, prefer `run-chunked --dry-run` if you also want
  checkpoint resumability.

## Inputs

- `URL_OR_ID`: HubSpot list URL or numeric ID.
- `--limit N` (optional): only process the first N companies. Useful for
  cheap initial sanity checks on big lists.

## Procedure

```bash
.venv/bin/python -m src.cli run "<URL_OR_ID>" --dry-run [--limit N]
```

This writes a JSON report to `logs/run_YYYYMMDD_HHMMSS.json`. **Capture
that path** — the `run-from-report` skill needs it if the user approves.

## Outputs (what to tell the user in chat)

Always include, in this order:

1. **Counters table** — total, with signals, "No signals detected" (clean
   fetch), fetch errors, skipped (no URL).
2. **Per-company breakdown** of `signals_string` for every row
   (truncate name and domain to 20–25 chars for table width).
3. **The 5–10 heaviest stacks** if the list is large (≥50 companies)
   so the user can sanity-check signature coverage.
4. **Any fetch errors** with categorization (DNS / TLS / Timeout /
   protocol).
5. **A clear approval prompt**: "Reply `approved` to write all N rows,
   or `approved, skip fetch errors` to leave the K erroring rows
   untouched." Specify the report path.

## Pull the per-company breakdown like this

```bash
.venv/bin/python -c "
import json
from pathlib import Path
report = json.loads(Path('logs/run_<timestamp>.json').read_text())
for r in report['results']:
    n = (r['name'] or '(unnamed)')[:24]
    d = (r['domain'] or '')[:22]
    print(f'{n:24s} {d:22s}  -> {r[\"signals_string\"]}')
"
```

## What to expect

- Static-only fetches: ~0.3–0.5 s/company.
- Mixed with Playwright fallback: ~0.5–1.5 s/company.
- A 234-row dry-run took 77 s; 1700 rows took 927 s; 5336 rows did NOT
  finish in a single foreground call (use `run-chunked` for those).

## Approval gate

After printing the summary, **WAIT for explicit user approval before
running any write skill**. The phrases that count as approval:
`approved`, `go`, `yes`, `ship it`, or a single-letter `A`/`B` choice
when you offered a numbered menu. Anything else is "hold".
