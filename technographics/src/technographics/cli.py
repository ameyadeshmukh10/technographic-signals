"""Click CLI for the technographic detector."""

from __future__ import annotations

import asyncio
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import click

# Allow `from scripts import ...` whether running from source or installed.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if (_REPO_ROOT / "scripts").is_dir() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from technographics.dns_collector import collect_dns_async
from technographics.dns_matcher import DNSMatcher
from technographics.fusion import fuse
from technographics.loader import load_library, load_selection
from technographics.schema import Detection
from technographics.web_collector import collect_web_async
from technographics.web_matcher import WebMatcher


def _all_subdomains(library) -> set[str]:
    subs: set[str] = set()
    for sig in library.dns_signatures.values():
        subs.update(sig.subdomains_to_probe)
    return subs


def _resolve_selection(selection_path: str | None) -> set[str] | None:
    return load_selection(selection_path) if selection_path else None


async def _scan_async(domain: str, library, dns_only: bool, web_only: bool):
    dns_dets: list[Detection] = []
    web_dets: list[Detection] = []

    if not web_only:
        records = await collect_dns_async(domain, subdomains=_all_subdomains(library))
        dns_dets = DNSMatcher(library.dns_signatures, library.vendors).match(records)
    if not dns_only:
        page = await collect_web_async(domain)
        web_dets = WebMatcher(library.web_signatures, library.vendors).match(page)

    return dns_dets, web_dets


def _render(domain, dns_dets, web_dets, do_fuse: bool):
    if do_fuse:
        results = fuse(dns_dets, web_dets)
    else:
        results = sorted([*dns_dets, *web_dets], key=lambda d: d.confidence, reverse=True)
    return results


def _print_human(domain, results):
    click.echo(click.style(f"\n{domain}", bold=True))
    if not results:
        click.echo("  no signals detected")
        return
    for d in results:
        tier = f" [{d.tier_signal}]" if d.tier_signal else ""
        line = f"  {d.confidence:0.2f}  {d.vendor_name} ({d.category}) <{d.source}>{tier}"
        click.echo(line)
        for ev in d.evidence[:6]:
            click.echo(f"        - {ev}")


@click.group()
def cli() -> None:
    """Dual-pipeline (DNS + JS/Web) technographic detection."""


@cli.command()
@click.argument("domain")
@click.option("--dns-only", is_flag=True, help="run only the DNS pipeline")
@click.option("--web-only", is_flag=True, help="run only the JS/Web pipeline")
@click.option("--fuse", "do_fuse", is_flag=True, help="fuse DNS + Web signals")
@click.option("--json", "as_json", is_flag=True, help="emit JSON")
@click.option("--selection", type=click.Path(exists=True), default=None,
              help="path to a selection.json file ({\"selected\": [\"intercom\", ...]})")
@click.option("--curated-only", is_flag=True, help="skip the master tier; use only hand-curated signatures")
def scan(domain, dns_only, web_only, do_fuse, as_json, selection, curated_only):
    """Run detection against a single DOMAIN."""
    if dns_only and web_only:
        raise click.UsageError("--dns-only and --web-only are mutually exclusive")
    library = load_library(
        include_master=not curated_only,
        selection=_resolve_selection(selection),
    )
    dns_dets, web_dets = asyncio.run(_scan_async(domain, library, dns_only, web_only))
    results = _render(domain, dns_dets, web_dets, do_fuse)
    if as_json:
        click.echo(json.dumps({"domain": domain, "detections": [asdict(d) for d in results]}, indent=2))
    else:
        _print_human(domain, results)


@cli.command(name="scan-batch")
@click.argument("domains_file", type=click.Path(exists=True))
@click.option("--out", required=True, type=click.Path(), help="JSONL output path")
@click.option("--workers", default=10, show_default=True, help="concurrent scans")
@click.option("--fuse", "do_fuse", is_flag=True, help="fuse DNS + Web signals")
@click.option("--selection", type=click.Path(exists=True), default=None,
              help="path to a selection.json file")
@click.option("--curated-only", is_flag=True, help="skip the master tier")
def scan_batch(domains_file, out, workers, do_fuse, selection, curated_only):
    """Scan every domain in DOMAINS_FILE (one per line); write JSONL to --out."""
    library = load_library(
        include_master=not curated_only,
        selection=_resolve_selection(selection),
    )
    with open(domains_file) as fh:
        domains = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

    def run_one(domain):
        dns_dets, web_dets = asyncio.run(_scan_async(domain, library, False, False))
        results = _render(domain, dns_dets, web_dets, do_fuse)
        return {"domain": domain, "detections": [asdict(d) for d in results]}

    written = 0
    with open(out, "w") as out_fh, ThreadPoolExecutor(max_workers=workers) as pool:
        for record in pool.map(run_one, domains):
            out_fh.write(json.dumps(record) + "\n")
            written += 1
            click.echo(f"  scanned {record['domain']}: {len(record['detections'])} detections")
    click.echo(f"wrote {written} records to {out}")


@cli.command()
def validate():
    """Lint all signature files against the schema."""
    from scripts import validate_signatures  # type: ignore

    sys.exit(validate_signatures.run())


@cli.command(name="import-master")
@click.option("--force", is_flag=True, help="wipe signatures/master/web/ before writing")
def import_master(force):
    """Import the full enthec/webappanalyzer library into signatures/master/.

    Idempotent: re-runs against the same upstream commit produce byte-identical
    files. Curated signatures in signatures/{dns,web}/ are untouched.
    """
    from scripts import import_wappalyzer as importer  # type: ignore

    saved = sys.argv
    sys.argv = ["import_wappalyzer", "--full"] + (["--force"] if force else [])
    try:
        sys.exit(importer.main())
    finally:
        sys.argv = saved


@cli.command(name="import-wappalyzer")
@click.option("--seed-curated", is_flag=True, help="merge into signatures/web/ instead of master/")
@click.option("--force", is_flag=True, help="overwrite existing files")
def import_wappalyzer(seed_curated, force):
    """Alias for `import-master`. Pass --seed-curated for the legacy mode
    that merges a small named vendor set into signatures/web/."""
    from scripts import import_wappalyzer as importer  # type: ignore

    saved = sys.argv
    mode_flag = ["--seed-curated"] if seed_curated else ["--full"]
    sys.argv = ["import_wappalyzer"] + mode_flag + (["--force"] if force else [])
    try:
        sys.exit(importer.main())
    finally:
        sys.argv = saved


@cli.command()
@click.option("--selection", type=click.Path(exists=True), default=None,
              help="path to a selection.json file")
@click.option("--vendors", is_flag=True, help="print the full per-vendor table (long!)")
def stats(selection, vendors):
    """Print signature library coverage statistics."""
    sel = _resolve_selection(selection)
    library = load_library(selection=sel)
    s = library.stats()
    click.echo(f"total vendors:    {s['total_vendors']}")
    click.echo(f"  curated:        {s['curated']}")
    click.echo(f"  master:         {s['master']}")
    if sel is not None:
        click.echo(f"  selection size: {len(sel)} (filtered)")
    click.echo(f"  with DNS sigs:  {s['with_dns']}")
    click.echo(f"  with web sigs:  {s['with_web']}")
    click.echo(f"  with both:      {s['with_both']}")
    click.echo("by category (top 20):")
    top = sorted(s["by_category"].items(), key=lambda kv: -kv[1])[:20]
    for cat, n in top:
        click.echo(f"  {cat:30s} {n}")

    if not vendors:
        click.echo("\n(pass --vendors to print the full per-vendor table)")
        return

    click.echo("\nvendor_id                       src           has_dns  has_web  category")
    web_ids = {vid for vid, sig in library.web_signatures.items() if _has_web_patterns(sig)}
    for vid in sorted(library.vendors):
        vendor = library.vendors[vid]
        has_dns = "yes" if _has_dns_patterns(library.dns_signatures.get(vid)) else "-"
        has_web = "yes" if vid in web_ids else "-"
        src = library.source(vid)
        click.echo(f"  {vid:30s} {src:12s}  {has_dns:7s}  {has_web:7s}  {vendor.category}")


def _has_dns_patterns(sig) -> bool:
    if sig is None:
        return False
    return any([
        sig.cname_patterns, sig.txt_patterns, sig.mx_patterns,
        sig.ns_patterns, sig.a_patterns, sig.soa_patterns,
    ])


def _has_web_patterns(sig) -> bool:
    return any([
        sig.js_globals, sig.script_src_patterns, sig.cookie_patterns,
        sig.header_patterns, sig.html_patterns, sig.meta_patterns, sig.url_patterns,
        sig.inline_script_patterns, sig.text_patterns, sig.css_patterns,
        sig.xhr_patterns, sig.dom_patterns,
    ])


if __name__ == "__main__":
    cli()
