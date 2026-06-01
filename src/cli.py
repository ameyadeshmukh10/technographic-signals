"""Command-line interface for the technographic signals workflow.

Three subcommands:

  python -m src.cli check-list URL_OR_ID
      Verify HubSpot connectivity. Read-only; prints company count and
      the first 5 records.

  python -m src.cli detect-one URL
      Fetch a single site and print what we'd detect. Useful when
      tuning signatures — no HubSpot calls.

  python -m src.cli run URL_OR_ID [--dry-run] [--limit N]
      The full workflow. `--dry-run` skips HubSpot writes; `--limit N`
      processes only the first N companies.
"""

from __future__ import annotations

import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import config
from .detectors import DetectionHit, ad_pixels, crm, martech, salestech
from .hubspot_client import HubSpotClient
from .orchestrator import Orchestrator, filter_low_confidence, format_signals
from .site_fetcher import SiteFetcher


_CONSOLE = Console()


@click.group(help="Technographic signals workflow.")
def cli() -> None:
    pass


@cli.command("check-list", help="Verify HubSpot connectivity. Read-only.")
@click.argument("url_or_id")
def check_list_cmd(url_or_id: str) -> None:
    try:
        list_id = HubSpotClient.extract_list_id(url_or_id)
    except ValueError as exc:
        _CONSOLE.print(f"[red]{exc}[/red]")
        sys.exit(1)

    client = HubSpotClient(config.HUBSPOT_ACCESS_TOKEN)
    _CONSOLE.print(f"[bold]Resolved list ID:[/bold] {list_id}")
    _CONSOLE.print("[dim]Streaming companies (read-only)…[/dim]")

    count = 0
    first_five: list[dict] = []
    for company in client.get_companies_in_list(list_id):
        count += 1
        if len(first_five) < 5:
            first_five.append(company)

    _CONSOLE.print(f"[bold]Total companies:[/bold] {count}")

    if not first_five:
        _CONSOLE.print("[yellow]List is empty (or no companies returned).[/yellow]")
        return

    table = Table(title="First 5 companies")
    table.add_column("ID", overflow="fold")
    table.add_column("Name")
    table.add_column("Domain")
    table.add_column("Website", overflow="fold")
    for c in first_five:
        table.add_row(
            str(c.get("id") or "-"),
            c.get("name") or "(unnamed)",
            c.get("domain") or "-",
            c.get("website") or "-",
        )
    _CONSOLE.print(table)


@cli.command("detect-one", help="Fetch a single URL and print detections. No HubSpot calls.")
@click.argument("url")
def detect_one_cmd(url: str) -> None:
    fetcher = SiteFetcher()
    fr = fetcher.fetch(url)

    summary = Table(title=f"Fetch: {fr.url}", show_header=False)
    summary.add_row("Status", str(fr.status))
    summary.add_row("Rendered", str(fr.rendered))
    summary.add_row("HTML length", f"{len(fr.html):,} chars")
    summary.add_row("Script srcs", str(len(fr.script_srcs)))
    summary.add_row("Cookies", str(len(fr.cookies)))
    summary.add_row("Error", fr.error or "-")
    _CONSOLE.print(summary)

    if fr.error and fr.status == 0 and not fr.html:
        _CONSOLE.print("[yellow]Fetch failed; skipping detection.[/yellow]")
        return

    all_hits: list[DetectionHit] = []
    for module in (crm, ad_pixels, martech, salestech):
        all_hits.extend(module.detect(fr))
    filtered = filter_low_confidence(all_hits)
    formatted = format_signals(filtered)

    if not filtered:
        _CONSOLE.print(Panel("No signals detected.", border_style="dim"))
        return

    detect_table = Table(title="Detected vendors")
    detect_table.add_column("Category")
    detect_table.add_column("Vendor")
    detect_table.add_column("Confidence")
    detect_table.add_column("Evidence", overflow="fold")
    for h in filtered:
        detect_table.add_row(
            h.category,
            h.name,
            h.confidence,
            "\n".join(h.evidence) if h.evidence else "-",
        )
    _CONSOLE.print(detect_table)
    _CONSOLE.print(Panel(formatted, title="Formatted technographic_signals"))


@cli.command("run", help="Run the full workflow on URL_OR_ID.")
@click.argument("url_or_id")
@click.option("--dry-run", is_flag=True, help="Skip HubSpot writes; just compute and log.")
@click.option("--limit", type=int, default=None, help="Process only the first N companies.")
def run_cmd(url_or_id: str, dry_run: bool, limit: int | None) -> None:
    try:
        list_id = HubSpotClient.extract_list_id(url_or_id)
    except ValueError as exc:
        _CONSOLE.print(f"[red]{exc}[/red]")
        sys.exit(1)

    if dry_run:
        _CONSOLE.print(Panel(
            "[bold yellow]DRY RUN[/bold yellow] — no HubSpot writes will be performed.",
            border_style="yellow",
        ))
    if limit is not None:
        _CONSOLE.print(f"[dim]Limit: processing first {limit} companies only.[/dim]")

    client = HubSpotClient(config.HUBSPOT_ACCESS_TOKEN)
    fetcher = SiteFetcher()
    Orchestrator(client, fetcher).run(list_id=list_id, dry_run=dry_run, limit=limit)


if __name__ == "__main__":
    cli()
