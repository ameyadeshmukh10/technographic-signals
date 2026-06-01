---
name: check-list
description: "Resolve a HubSpot list URL or numeric ID and print the company count plus the first 5 records. Read-only. Use this as the default response to a bare list URL in chat."
argument-hint: "[URL_OR_ID]"
---

# check-list

## When to use

- The user pastes a HubSpot list URL with no other instructions.
- The user asks "how big is list X" or "what's in list X".
- Before any write skill, to confirm connectivity and size.

## When NOT to use

- The user explicitly says "run X" / "skip dry run" — go straight to
  `run-end-to-end` or `run-chunked`.
- The URL is a single company website (use `detect-one` instead).

## Inputs

- `URL_OR_ID`: either a numeric list ID (`1916`), an EU-region URL
  (`https://app-eu1.hubspot.com/contacts/<portal>/objectLists/<id>/…`),
  or the US-region equivalent. Query strings are stripped automatically.

## Procedure

```bash
.venv/bin/python -m src.cli check-list "<URL_OR_ID>"
```

That's it. The CLI prints:
- The resolved list ID.
- The total company count.
- A Rich table of the first 5 records (id, name, domain, website).

## Outputs (what to tell the user in chat)

1. **The total count** — single most important number.
2. **A note if any first-5 record is missing both `domain` and `website`** —
   these will be skipped by any subsequent run skill.
3. **A recommendation** based on count:
   - 0 companies → "list is empty; confirm filters in HubSpot".
   - 1–500 → offer `dry-run` and `run-end-to-end` as menu options.
   - >500 → lead with `run-chunked` as the recommended option.

## Example

```
User: https://app-eu1.hubspot.com/contacts/144358290/objectLists/2076/...
You:  [run check-list]
You:  "List 2076 has 5336 companies. At this size a single foreground
       run is likely to be killed before it finishes. I recommend
       `run-chunked` with --chunk 250 (~21 chunks, fully resumable).
       Alternatives: `dry-run` to preview, or `run-end-to-end` if you
       want to risk it."
```

## Notes

- `HUBSPOT_ACCESS_TOKEN` must be set (in `.env` or env). The CLI
  validates this at import time.
- This skill makes one paginated HubSpot read. Cheap. Counts against the
  daily API quota but not in any way that matters at human-typed pace.
