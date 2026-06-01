"""Chunked runner for large HubSpot lists.

Materializes the full company list once into a JSON checkpoint, then
processes it in fixed-size chunks. Each chunk produces its own
`logs/run_*.json` report, and the checkpoint is updated atomically after
each chunk — so a kill mid-run loses at most one chunk and the next
invocation resumes from where it stopped.

Usage:
    python scripts/run_chunked.py URL_OR_ID [--chunk N] [--checkpoint PATH]
                                  [--dry-run] [--max-chunks N]

Examples:
    # 5336-company list, 250 per chunk, real writes:
    python scripts/run_chunked.py 2076 --chunk 250

    # Resume the same list (auto-skips done IDs):
    python scripts/run_chunked.py 2076 --chunk 250

    # Dry run the first 3 chunks for sanity:
    python scripts/run_chunked.py 2076 --chunk 250 --dry-run --max-chunks 3
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Allow `python scripts/run_chunked.py …` (without -m) by putting the
# project root on sys.path before importing src.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console  # noqa: E402

from src import config  # noqa: E402
from src.hubspot_client import HubSpotClient
from src.orchestrator import Orchestrator
from src.site_fetcher import SiteFetcher


_CONSOLE = Console()


def _checkpoint_path(list_id: str, override: str | None) -> Path:
    if override:
        return Path(override)
    return config.LOGS_DIR / "checkpoints" / f"list_{list_id}.json"


def _materialize_or_load(
    client: HubSpotClient, list_id: str, ckpt_path: Path,
) -> dict:
    if ckpt_path.exists():
        ckpt = json.loads(ckpt_path.read_text())
        _CONSOLE.print(
            f"[dim]Loaded checkpoint: {ckpt_path} "
            f"({len(ckpt['companies'])} companies total, "
            f"{sum(1 for c in ckpt['companies'] if c['status'] == 'done')} already done)[/dim]"
        )
        return ckpt
    _CONSOLE.print(f"[dim]No checkpoint at {ckpt_path} — materializing list…[/dim]")
    companies = list(client.get_companies_in_list(list_id))
    ckpt = {
        "list_id": list_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "companies": [
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "domain": c.get("domain"),
                "website": c.get("website"),
                "status": "pending",
            }
            for c in companies
        ],
    }
    ckpt_path.parent.mkdir(parents=True, exist_ok=True)
    ckpt_path.write_text(json.dumps(ckpt, indent=2))
    _CONSOLE.print(f"[dim]Wrote checkpoint: {ckpt_path} ({len(companies)} companies)[/dim]")
    return ckpt


def _save_checkpoint(ckpt: dict, ckpt_path: Path) -> None:
    tmp = ckpt_path.with_suffix(ckpt_path.suffix + ".tmp")
    tmp.write_text(json.dumps(ckpt, indent=2))
    tmp.replace(ckpt_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Chunked runner for large HubSpot lists.")
    parser.add_argument("url_or_id", help="HubSpot list URL or numeric ID.")
    parser.add_argument("--chunk", type=int, default=250, help="Companies per chunk (default 250).")
    parser.add_argument("--checkpoint", default=None, help="Checkpoint JSON path.")
    parser.add_argument("--dry-run", action="store_true", help="Skip HubSpot writes.")
    parser.add_argument("--max-chunks", type=int, default=None, help="Stop after N chunks.")
    args = parser.parse_args()

    list_id = HubSpotClient.extract_list_id(args.url_or_id)
    ckpt_path = _checkpoint_path(list_id, args.checkpoint)

    client = HubSpotClient(config.HUBSPOT_ACCESS_TOKEN)
    fetcher = SiteFetcher()
    orch = Orchestrator(client, fetcher)
    orch.ensure_property()

    ckpt = _materialize_or_load(client, list_id, ckpt_path)
    pending = [c for c in ckpt["companies"] if c["status"] == "pending"]
    done_before = len(ckpt["companies"]) - len(pending)
    _CONSOLE.print(
        f"[bold]List {list_id}[/bold]: {len(ckpt['companies'])} total, "
        f"{done_before} done, {len(pending)} pending. chunk={args.chunk} dry_run={args.dry_run}"
    )

    if not pending:
        _CONSOLE.print("[green]Nothing pending — checkpoint already complete.[/green]")
        return 0

    total_succeeded = total_skipped = total_failed = 0
    chunks_done = 0
    for offset in range(0, len(pending), args.chunk):
        if args.max_chunks is not None and chunks_done >= args.max_chunks:
            _CONSOLE.print(f"[yellow]Stopping after {args.max_chunks} chunk(s) per --max-chunks.[/yellow]")
            break
        batch = pending[offset:offset + args.chunk]
        chunk_idx = chunks_done + 1
        _CONSOLE.print(
            f"\n[bold cyan]Chunk {chunk_idx}[/bold cyan]: "
            f"processing {len(batch)} companies (offset {offset} of {len(pending)} pending)"
        )
        # Strip the `status` field — orchestrator expects bare company dicts.
        companies_for_orch = [
            {k: v for k, v in c.items() if k != "status"} for c in batch
        ]
        report = orch.run_companies(
            companies_for_orch,
            dry_run=args.dry_run,
            list_id_for_log=f"{list_id}-chunk{chunk_idx}",
        )
        total_succeeded += report.succeeded
        total_skipped += report.skipped
        total_failed += report.failed

        # Mark IDs as done in the checkpoint (only when not dry-run — dry runs
        # don't change HubSpot state, so we don't want them to advance the checkpoint).
        if not args.dry_run:
            done_ids = {c["id"] for c in batch}
            for c in ckpt["companies"]:
                if c["id"] in done_ids:
                    c["status"] = "done"
            _save_checkpoint(ckpt, ckpt_path)

        chunks_done += 1

    remaining = sum(1 for c in ckpt["companies"] if c["status"] == "pending")
    _CONSOLE.print()
    _CONSOLE.print(
        f"[bold]Chunked run complete.[/bold] "
        f"chunks_processed={chunks_done} succeeded={total_succeeded} "
        f"skipped={total_skipped} failed={total_failed} "
        f"remaining_pending={remaining}"
    )
    if args.dry_run:
        _CONSOLE.print("[yellow](dry-run — checkpoint NOT advanced)[/yellow]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
