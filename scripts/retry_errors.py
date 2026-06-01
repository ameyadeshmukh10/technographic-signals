"""Retry the fetch-error rows from a saved run report.

For each row in REPORT_PATH where `status == "succeeded"` AND `error`
is set, re-fetches the company website with a longer per-request timeout
and writes the new detection to HubSpot if signals were found. Companies
that still fail are left untouched in HubSpot.

Reads the most recent report by default. Bumps both `REQUEST_TIMEOUT_SECONDS`
(static + Playwright `goto`) and the Playwright `networkidle` constant for
the duration of this script.

Usage:
    python scripts/retry_errors.py [REPORT_PATH] [--timeout SECONDS]
                                   [--workers N] [--dry-run]

Examples:
    # Retry the most recent run's errors with a 30s timeout:
    python scripts/retry_errors.py --timeout 30

    # Retry a specific report:
    python scripts/retry_errors.py logs/run_20260514_160123.json --timeout 30

    # Test what would be retried without writing:
    python scripts/retry_errors.py --timeout 30 --dry-run
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Allow `python scripts/retry_errors.py …` (without -m).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console  # noqa: E402


_CONSOLE = Console()


def _most_recent_report() -> Path | None:
    paths = sorted(glob.glob("logs/run_*.json"))
    return Path(paths[-1]) if paths else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry the fetch-error rows from a saved report.")
    parser.add_argument("report_path", nargs="?", default=None, help="Path to a logs/run_*.json file (default: most recent).")
    parser.add_argument("--timeout", type=int, default=30, help="REQUEST_TIMEOUT_SECONDS for the retry (default 30).")
    parser.add_argument("--workers", type=int, default=5, help="Concurrent fetch workers (default 5).")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to HubSpot.")
    args = parser.parse_args()

    # Set BEFORE importing config.
    os.environ["REQUEST_TIMEOUT_SECONDS"] = str(args.timeout)

    # Imports deferred until after env override.
    from src import config, site_fetcher  # noqa: E402
    from src.detectors import crm, ad_pixels, martech, salestech  # noqa: E402
    from src.hubspot_client import HubSpotClient  # noqa: E402
    from src.orchestrator import filter_low_confidence, format_signals  # noqa: E402
    from hubspot.crm.companies import BatchReadInputSimplePublicObjectId  # noqa: E402

    # Bump networkidle wait too (module constant).
    site_fetcher._NETWORKIDLE_TIMEOUT_MS = max(args.timeout * 1000 // 2, 8000)

    report_path = Path(args.report_path) if args.report_path else _most_recent_report()
    if report_path is None or not report_path.exists():
        _CONSOLE.print("[red]No report found.[/red]")
        return 1

    _CONSOLE.print(
        f"[bold]Source:[/bold] {report_path}\n"
        f"[bold]Config:[/bold] REQUEST_TIMEOUT_SECONDS={config.REQUEST_TIMEOUT_SECONDS} "
        f"networkidle={site_fetcher._NETWORKIDLE_TIMEOUT_MS}ms workers={args.workers} "
        f"dry_run={args.dry_run}"
    )

    report = json.loads(report_path.read_text())
    targets = [r for r in report["results"] if r.get("error") and r.get("status") == "succeeded"]
    _CONSOLE.print(f"[bold]Fetch-error rows in report:[/bold] {len(targets)}")
    if not targets:
        return 0

    client = HubSpotClient(config.HUBSPOT_ACCESS_TOKEN)
    fetcher = site_fetcher.SiteFetcher()

    ids = [t["company_id"] for t in targets if t.get("company_id")]
    body = BatchReadInputSimplePublicObjectId(
        inputs=[{"id": i} for i in ids],
        properties=["name", "domain", "website"],
        properties_with_history=[],
    )
    resp = client._client.crm.companies.batch_api.read(
        batch_read_input_simple_public_object_id=body,
    )
    companies = [
        {
            "id": c.id,
            "name": (c.properties or {}).get("name"),
            "domain": (c.properties or {}).get("domain"),
            "website": (c.properties or {}).get("website"),
        }
        for c in resp.results
    ]
    eligible = [(c, c.get("website") or c.get("domain")) for c in companies if c.get("website") or c.get("domain")]
    _CONSOLE.print(f"[bold]Eligible (have a URL):[/bold] {len(eligible)}\n")

    def process(c: dict, url: str):
        fr = fetcher.fetch(url)
        hits = []
        for m in (crm, ad_pixels, martech, salestech):
            hits.extend(m.detect(fr))
        filtered = filter_low_confidence(hits)
        return c, fr, filtered, format_signals(filtered)

    def label(c: dict) -> str:
        n = (c.get("name") or "?")[:30]
        d = (c.get("domain") or "?")[:30]
        return f"{n:30s} {d:30s}"

    succeeded: list[tuple[dict, str, int]] = []
    still_failed: list[tuple[dict, str]] = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process, c, u): (c, u) for c, u in eligible}
        for fut in as_completed(futures):
            c, _url = futures[fut]
            try:
                try:
                    _c, fr, hits, signals_string = fut.result(timeout=args.timeout * 4)
                except Exception as exc:
                    still_failed.append((c, f"worker exception: {exc}"))
                    _CONSOLE.print(f"  FAIL  {label(c)}  worker_exc={exc}")
                    continue
                if fr.error:
                    still_failed.append((c, fr.error))
                    short = (fr.error or "").split("\n")[0][:70]
                    _CONSOLE.print(f"  FAIL  {label(c)}  {short}")
                    continue
                succeeded.append((c, signals_string, len(hits)))
                _CONSOLE.print(f"  ok    {label(c)}  {len(hits):2d} vendors")
            except Exception as exc:
                still_failed.append((c, f"loop exception: {exc}"))
                _CONSOLE.print(f"  FAIL  loop_exc on cid={c.get('id')!r}: {exc}")

    _CONSOLE.print(f"\nRefetch: {len(succeeded)} succeeded, {len(still_failed)} still failed")

    if args.dry_run:
        _CONSOLE.print("[yellow](dry-run — not writing to HubSpot)[/yellow]")
        return 0

    if succeeded:
        _CONSOLE.print("\nWriting successful retries to HubSpot…")
        written = 0
        for c, signals_string, _ in succeeded:
            if c.get("id"):
                client.update_company(c["id"], {"technographic_signals": signals_string})
                written += 1
        _CONSOLE.print(f"Wrote {written} companies.")

    if still_failed:
        _CONSOLE.print("\nStill-failing companies (HubSpot left untouched):")
        for c, err in still_failed:
            short = (err or "").split("\n")[0][:80]
            _CONSOLE.print(f"  {label(c)}  {short}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
