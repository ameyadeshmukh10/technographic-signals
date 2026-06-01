# SKILLS.md — Playbook Registry

Each row is a named playbook. Click into the SKILL.md for full procedure.
The agent reading this file routes user requests to the right skill, then
follows that skill's procedure exactly.

## Routing rules

| If the user says / does this… | Run skill |
|---|---|
| Pastes a HubSpot list URL with no other context | [`check-list`](skills/check-list/SKILL.md), then offer a numbered menu |
| "dry run X" / "preview X" / "what would land for X" | [`dry-run`](skills/dry-run/SKILL.md) |
| "run X end to end" / "skip dry run X" / "just run it" | [`run-end-to-end`](skills/run-end-to-end/SKILL.md) (if <500 companies; offer `run-chunked` otherwise) |
| "chunked run X" / list size is >500 | [`run-chunked`](skills/run-chunked/SKILL.md) |
| Just "approved" / "go" after I posted a dry-run summary | [`run-from-report`](skills/run-from-report/SKILL.md) on the most recent `logs/run_*.json` |
| "approved, skip fetch errors" / "B" | [`run-from-report`](skills/run-from-report/SKILL.md) with `--skip-errors` (default true) |
| "retry the fetch errors" / "retry errors with N seconds" | [`retry-fetch-errors`](skills/retry-fetch-errors/SKILL.md) on the most recent report |
| Pastes a single URL (not a HubSpot list) / "what does X load" | [`detect-one`](skills/detect-one/SKILL.md) |
| "we missed X on Y" / "add a signature for X" | [`add-signature`](skills/add-signature/SKILL.md) |
| "did the writes land" / "spot-check the last run" | [`verify-writes`](skills/verify-writes/SKILL.md) |

## Skill registry

| Skill | Writes? | One-line summary |
|---|---|---|
| [`check-list`](skills/check-list/SKILL.md) | no | Resolve a list URL, print count + first 5 records. |
| [`dry-run`](skills/dry-run/SKILL.md) | no | Full pipeline without HubSpot writes; produces a `logs/run_*.json` for review. |
| [`run-end-to-end`](skills/run-end-to-end/SKILL.md) | YES | One-shot fetch + detect + write. For lists ≤500. |
| [`run-chunked`](skills/run-chunked/SKILL.md) | YES | Checkpointed chunked execution. For lists >500 or unreliable runs. |
| [`run-from-report`](skills/run-from-report/SKILL.md) | YES | Replay a saved dry-run JSON as writes only. No refetch. |
| [`retry-fetch-errors`](skills/retry-fetch-errors/SKILL.md) | YES | Retry the rows that errored last time, with longer timeout. |
| [`detect-one`](skills/detect-one/SKILL.md) | no | Fetch one URL, show all detector hits + evidence. |
| [`add-signature`](skills/add-signature/SKILL.md) | no | Procedure for adding a new vendor fingerprint. |
| [`verify-writes`](skills/verify-writes/SKILL.md) | no | Read N companies from HubSpot and diff against a report. |

## Defaults the agent must respect

These come from session experience and are documented in detail in
[`AGENTS.md`](AGENTS.md#decision-defaults-codified-from-session-experience).
Summary:

- Never run a write skill (`run-end-to-end`, `run-from-report`,
  `retry-fetch-errors`, `run-chunked` without `--dry-run`) without an
  explicit user "approved" / "go" / "yes" — UNLESS the user
  preemptively waived it ("skip dry run", "just run it").
- Always prefer `run-from-report` over `run-end-to-end` when the user
  approved a dry-run that's already on disk. It writes exactly what they
  reviewed, with no Playwright non-determinism between runs.
- For lists >500, default to `run-chunked` even if the user asked for
  `run-end-to-end`. Explain why (kill-resilience) and offer it as the
  first option.

## After every write run

Suggest [`verify-writes`](skills/verify-writes/SKILL.md) to spot-check 3-5
companies. Cheap, catches the edge cases (Playwright drift, 429 throttle,
field-name typos) that would otherwise show up as "we ran it but the
data isn't there".
