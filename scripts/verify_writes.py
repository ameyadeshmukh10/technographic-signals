"""Spot-check that `technographic_signals` writes landed in HubSpot.

Reads N rows from a saved run report (or specific names) and fetches the
live property value from HubSpot, printing expected vs actual side by
side. Codifies the manual spot-checks done throughout the session.

Usage:
    python scripts/verify_writes.py REPORT_PATH [--sample N] [--names "Foo,Bar"]
                                    [--show-misses]

Examples:
    # Random 5 spot-checks:
    python scripts/verify_writes.py logs/run_20260519_141338.json --sample 5

    # Specific named companies:
    python scripts/verify_writes.py logs/run_20260514_160123.json --names "Drata,HungerRush,LILT AI"

    # Show only the mismatches:
    python scripts/verify_writes.py logs/run_20260519_141338.json --sample 20 --show-misses
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

# Allow `python scripts/verify_writes.py …` (without -m).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console  # noqa: E402
from rich.table import Table

from src import config
from src.hubspot_client import HubSpotClient


_CONSOLE = Console()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify HubSpot writes against a saved report.")
    parser.add_argument("report_path", help="Path to a logs/run_*.json file.")
    parser.add_argument("--sample", type=int, default=5, help="Random sample size (default 5).")
    parser.add_argument("--names", default=None, help="Comma-separated company names to check (overrides sample).")
    parser.add_argument("--show-misses", action="store_true", help="Print only mismatched rows.")
    args = parser.parse_args()

    report = json.loads(Path(args.report_path).read_text())
    succeeded = [r for r in report.get("results", []) if r.get("status") == "succeeded" and r.get("signals_string")]
    if not succeeded:
        _CONSOLE.print("[yellow]No successful rows in the report.[/yellow]")
        return 0

    if args.names:
        wanted = {n.strip() for n in args.names.split(",") if n.strip()}
        chosen = [r for r in succeeded if r.get("name") in wanted]
        missing = wanted - {r.get("name") for r in chosen}
        if missing:
            _CONSOLE.print(f"[yellow]Names not in report:[/yellow] {sorted(missing)}")
    else:
        chosen = random.sample(succeeded, min(args.sample, len(succeeded)))

    client = HubSpotClient(config.HUBSPOT_ACCESS_TOKEN)

    matches = mismatches = errors = 0
    table = Table(show_lines=True)
    table.add_column("Company", overflow="fold")
    table.add_column("Match?")
    table.add_column("Expected (report)", overflow="fold")
    table.add_column("Actual (HubSpot)", overflow="fold")

    for r in chosen:
        cid = r.get("company_id")
        expected = r.get("signals_string") or ""
        try:
            resp = client._client.crm.companies.basic_api.get_by_id(
                company_id=cid, properties=["name", "technographic_signals"],
            )
            actual = (resp.properties or {}).get("technographic_signals") or ""
        except Exception as exc:
            errors += 1
            table.add_row((r.get("name") or "")[:30], "[red]ERROR[/red]", expected[:80], f"lookup failed: {exc}")
            continue
        if actual.strip() == expected.strip():
            matches += 1
            if args.show_misses:
                continue
            table.add_row((r.get("name") or "")[:30], "[green]ok[/green]", expected[:120], actual[:120])
        else:
            mismatches += 1
            table.add_row((r.get("name") or "")[:30], "[red]MISMATCH[/red]", expected[:120], actual[:120])

    _CONSOLE.print(table)
    _CONSOLE.print(
        f"\n[bold]Summary:[/bold] matches={matches} mismatches={mismatches} "
        f"errors={errors} of {len(chosen)} checked."
    )
    return 0 if mismatches == 0 and errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
