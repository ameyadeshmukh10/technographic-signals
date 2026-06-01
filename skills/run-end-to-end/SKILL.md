---
name: run-end-to-end
description: "One-shot fetch + detect + write to HubSpot. For lists ≤500 companies. Requires explicit user approval unless the gate was waived."
argument-hint: "[URL_OR_ID] [--limit N]"
---

# run-end-to-end

## When to use

- User has approved a dry-run AND we don't have a saved report to
  replay (rare — usually use `run-from-report` instead).
- User explicitly skips the dry-run gate ("skip dry run", "just run it
  end to end").
- List size ≤500. Larger lists are unlikely to finish in one shell call.

## When NOT to use

- **No user approval yet.** Run `dry-run` first.
- **List size >500.** Use `run-chunked` — single-shell runs of that size
  have been killed twice in observed history.
- **You're following an approval after a dry-run summary.** Use
  `run-from-report` instead. It writes exactly the data the user reviewed,
  with no Playwright non-determinism between dry-run and real-run.

## Inputs

- `URL_OR_ID`: HubSpot list URL or numeric ID.
- `--limit N` (optional): only process the first N companies.

## Procedure

```bash
.venv/bin/python -m src.cli run "<URL_OR_ID>" [--limit N]
```

The orchestrator:
1. Calls `ensure_property_exists` for `technographic_signals` (idempotent).
2. Materializes the company list from HubSpot.
3. For each company: fetch → detect → format → write.
4. Writes a `logs/run_YYYYMMDD_HHMMSS.json` report and a Rich console
   summary.

## Outputs (what to tell the user in chat)

1. **Counters table** — succeeded / skipped / failed / duration.
2. **Top 10 detected vendors** (already in the CLI output).
3. **Any fetch errors**, with a note that they got `"No signals detected"`
   written — flag if any look like recoverable Playwright timeouts (offer
   `retry-fetch-errors`).
4. **A spot-check suggestion** — offer to run `verify-writes --sample 3`.

## Cumulative-tally guidance

If the user has done multiple list runs in this session, include the
cumulative-total figure for them ("today across N lists, K companies tagged").
Pulled from session memory, not from disk.

## What can go wrong

- **Bash auto-background** after ~2 min runtime if you're invoking via
  the harness; output gets buffered. If you see that, stream the
  task-output file with `tail -f` or just wait for the task notification.
- **Harness kills** for runs >10–15 min. Recovery is hard because we lose
  the report. Use `run-chunked` for anything large.
- **Playwright non-determinism**: dry-run says "Drata has 12 vendors";
  real-run gets 11. Network timing. Real but rare.

## When the user pastes URL + "skip dry run"

Acknowledge the waiver. Then check size before invoking:

- ≤500: run this skill.
- >500: warn that a single shell command will likely be killed, recommend
  `run-chunked`, and ask whether to proceed anyway.
