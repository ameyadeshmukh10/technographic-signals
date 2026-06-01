"""Write `technographic_signals` to HubSpot from an existing dry-run report.

The orchestrator's dry-run produces a `logs/run_*.json` with the full
per-company `signals_string` that *would* have been written. This script
takes that report and performs only the writes — no refetching, no
detection rerun. Useful when:

  - You've reviewed a dry-run table and want to write exactly what you
    reviewed (no drift from a fresh fetch).
  - You want to skip the fetch-error rows so HubSpot keeps its existing
    values for those companies (`--skip-errors`, the default).

Usage:
    python scripts/run_from_report.py REPORT_PATH [--skip-errors/--no-skip-errors]
                                      [--limit N] [--dry-run]

Examples:
    # Honor the dry-run exactly, skip fetch errors:
    python scripts/run_from_report.py logs/run_20260514_160123.json

    # Write everything including "No signals detected" for fetch errors:
    python scripts/run_from_report.py logs/run_20260514_160123.json --no-skip-errors

    # Sanity-check on the first 5 only, no writes:
    python scripts/run_from_report.py logs/run_20260514_160123.json --dry-run --limit 5
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Allow `python scripts/run_from_report.py …` (without -m).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console  # noqa: E402
from rich.progress import (
    BarColumn, MofNCompleteColumn, Progress, SpinnerColumn,
    TextColumn, TimeElapsedColumn,
)

from src import config
from src.hubspot_client import HubSpotClient


_CONSOLE = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a HubSpot batch from a saved dry-run report.")
    parser.add_argument("report_path", help="Path to a logs/run_*.json file.")
    parser.add_argument(
        "--skip-errors", dest="skip_errors", action="store_true", default=True,
        help="Leave fetch-error rows untouched (default).",
    )
    parser.add_argument(
        "--no-skip-errors", dest="skip_errors", action="store_false",
        help="Also write 'No signals detected' to fetch-error rows.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N rows.")
    parser.add_argument("--dry-run", action="store_true", help="Print but do not write.")
    args = parser.parse_args()

    report_path = Path(args.report_path)
    report = json.loads(report_path.read_text())
    results = report.get("results", [])

    eligible = []
    for r in results:
        if r.get("status") != "succeeded":
            continue
        if not r.get("signals_string"):
            continue
        if args.skip_errors and r.get("error"):
            continue
        eligible.append(r)
    if args.limit is not None:
        eligible = eligible[:args.limit]

    _CONSOLE.print(
        f"[bold]Source:[/bold] {report_path}\n"
        f"[bold]Eligible to write:[/bold] {len(eligible)} of {len(results)} "
        f"(skip_errors={args.skip_errors}, limit={args.limit}, dry_run={args.dry_run})"
    )

    if not eligible:
        _CONSOLE.print("[yellow]Nothing to write.[/yellow]")
        return 0

    if not args.dry_run:
        client = HubSpotClient(config.HUBSPOT_ACCESS_TOKEN)
        client.ensure_property_exists(
            object_type="companies", property_name="technographic_signals",
            label="Technographic Signals",
        )
    else:
        client = None

    started = time.monotonic()
    ok = fail = 0
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(),
    ) as p:
        task = p.add_task("Writing to HubSpot", total=len(eligible))
        for r in eligible:
            cid = r.get("company_id")
            sig = r.get("signals_string")
            if not cid or not sig:
                fail += 1
            elif args.dry_run:
                ok += 1  # would-write
            else:
                try:
                    client.update_company(cid, {"technographic_signals": sig})
                    ok += 1
                except Exception as exc:
                    fail += 1
                    _CONSOLE.print(f"[red]update failed cid={cid} name={r.get('name')}: {exc}[/red]")
            p.advance(task)

    duration = time.monotonic() - started
    _CONSOLE.print()
    label = "Would have written" if args.dry_run else "Wrote"
    _CONSOLE.print(f"[bold]Done.[/bold] {label} {ok}, failed {fail}, duration {duration:.1f}s.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
