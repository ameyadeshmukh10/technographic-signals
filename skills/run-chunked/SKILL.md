---
name: run-chunked
description: "Checkpointed chunked execution of the pipeline. Materializes the list once, processes in fixed batches, and is resumable across kills. Use for lists >500 or after any kill of run-end-to-end."
argument-hint: "[URL_OR_ID] [--chunk N] [--dry-run] [--max-chunks N]"
---

# run-chunked

## When to use

- List size >500 companies. Single-shell `cli run` will likely be killed.
- A `run-end-to-end` invocation was killed and you need to resume cleanly.
- You want per-batch reports for finer-grained debugging.

## When NOT to use

- List size ≤500 — `run-end-to-end` is simpler.
- The user wants a single review-then-approve cycle. Chunked runs write
  per chunk; if you need a single all-at-once preview, use `dry-run`
  first and then `run-from-report` after approval.

## Inputs

- `URL_OR_ID`: HubSpot list URL or numeric ID.
- `--chunk N` (optional, default 250): companies per batch.
- `--checkpoint PATH` (optional): override checkpoint path. Default is
  `logs/checkpoints/list_<id>.json`.
- `--dry-run` (optional): skip writes; also does NOT advance the
  checkpoint (so the next non-dry invocation processes the same companies).
- `--max-chunks N` (optional): stop after N chunks. Useful for "process
  the first 1000 and check before doing the rest".

## Procedure

```bash
# First invocation — materializes the list and starts chunk 1:
.venv/bin/python scripts/run_chunked.py "<URL_OR_ID>" --chunk 250

# Resume (auto-skips done IDs):
.venv/bin/python scripts/run_chunked.py "<URL_OR_ID>" --chunk 250

# Dry-run the first 2 chunks to sanity-check before committing:
.venv/bin/python scripts/run_chunked.py "<URL_OR_ID>" --chunk 250 --dry-run --max-chunks 2
```

The checkpoint at `logs/checkpoints/list_<id>.json` tracks each company
as `pending` or `done`. On startup the script:
1. If the checkpoint exists, loads it. Otherwise materializes the list
   from HubSpot and writes one.
2. Selects all `pending` IDs.
3. Processes them in batches of `--chunk`. Each batch calls
   `Orchestrator.run_companies()` which writes its own `logs/run_*.json`.
4. After each successful batch (not in dry-run), marks those IDs `done`
   and persists the checkpoint atomically.

## Outputs (what to tell the user in chat)

1. **Confirmation of materialization** — total companies, how many were
   already done in the checkpoint (if resuming).
2. **Per-chunk one-line summaries** — chunk #, count, succeeded /
   skipped / failed. (Or just say "21 chunks, all green" if uneventful.)
3. **A final tally** — total written across the whole list, remaining
   pending (should be 0 on a clean finish).
4. **Pointers** to the latest per-chunk report and the checkpoint file.

## What can go wrong

- **Mid-chunk kill** loses at most that chunk; the next invocation
  re-runs only the pending IDs. Safe.
- **Mid-write kill within a chunk** is the only sketchy case: some
  companies in the chunk got their property updated, some didn't, but
  the chunk wasn't marked `done` so all of them get retried. The
  successfully-written ones are simply overwritten with the same value
  on retry — no harm.
- **Network flakes** that hit per-company timeouts get logged as fetch
  errors and written as `"No signals detected"` (default) — see
  `retry-fetch-errors` for the second pass.

## Recovery from a stale checkpoint

If the user wants to redo a list from scratch:

```bash
rm logs/checkpoints/list_<id>.json
.venv/bin/python scripts/run_chunked.py <id> --chunk 250
```

Or, if they want to redo only some IDs, edit the checkpoint JSON
manually and flip those rows' `status` back to `pending`.
