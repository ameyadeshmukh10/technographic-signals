"""Orchestrator — wires HubSpot, the site fetcher, and the detectors
together for an end-to-end run.

Per-company flow:
  list member → website URL → fetch → 4 detectors → low-conf filter →
  formatted signals string → HubSpot company patch.

Concurrency: fetch + detect runs in a `ThreadPoolExecutor` sized to
`MAX_CONCURRENT_FETCHES`. The HubSpot writes happen in the main thread,
sequentially — keeps rate limiting trivial and lets us preserve a
deterministic ordering when iterating `as_completed`.

Robustness:
  - The fetcher and detectors are already defensive; the orchestrator
    catches anything else so one bad company can never abort the run.
  - Per-company timeout is enforced via `Future.result(timeout=60)` so
    a hung worker doesn't stall the batch.
  - A run report is written to `logs/run_YYYYMMDD_HHMMSS.json` and
    summarized in the console at the end of every run.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FuturesTimeoutError,
    as_completed,
)
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from . import config
from .detectors import DetectionHit, ad_pixels, crm, martech, salestech

if TYPE_CHECKING:
    from .hubspot_client import HubSpotClient
    from .site_fetcher import SiteFetcher


_logger = logging.getLogger("technographic.orchestrator")
if not _logger.handlers:
    _logger.addHandler(RichHandler(show_path=False, rich_tracebacks=False, markup=False))
    _logger.setLevel(config.LOG_LEVEL)
    _logger.propagate = False


_PER_COMPANY_TIMEOUT_S = 60
_NO_SIGNALS = "No signals detected"
_PROPERTY_NAME = "technographic_signals"
_PROPERTY_LABEL = "Technographic Signals"

_CATEGORY_DISPLAY: list[tuple[str, str]] = [
    ("crm", "CRM"),
    ("ad_pixel", "Ad Pixels"),
    ("martech", "Martech"),
    ("salestech", "Salestech"),
    ("erp", "ERP"),
]


def filter_low_confidence(hits: list[DetectionHit]) -> list[DetectionHit]:
    """Drop a low-confidence hit unless the same vendor name also
    appears with high/medium confidence somewhere in the result set
    (i.e., another category has corroborated it)."""
    strong = {h.name for h in hits if h.confidence in ("high", "medium")}
    return [h for h in hits if h.confidence != "low" or h.name in strong]


def format_signals(hits: list[DetectionHit]) -> str:
    """`CRM: A | Ad Pixels: B, C | Martech: D | Salestech: E`.

    Empty categories are omitted entirely. If nothing was detected
    the literal string `"No signals detected"` is returned so the
    downstream HubSpot value distinguishes "we ran" from "we never
    ran" (an empty cell would mean the latter).
    """
    if not hits:
        return _NO_SIGNALS
    by_cat: dict[str, set[str]] = defaultdict(set)
    for h in hits:
        by_cat[h.category].add(h.name)
    parts: list[str] = []
    for key, label in _CATEGORY_DISPLAY:
        vendors = sorted(by_cat.get(key, set()))
        if vendors:
            parts.append(f"{label}: {', '.join(vendors)}")
    return " | ".join(parts) if parts else _NO_SIGNALS


@dataclass
class RunReport:
    started_at: str
    finished_at: str = ""
    duration_seconds: float = 0.0
    total_companies: int = 0
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[dict] = field(default_factory=list)


class Orchestrator:
    def __init__(
        self,
        hubspot_client: "HubSpotClient",
        site_fetcher: "SiteFetcher",
    ) -> None:
        self.hubspot = hubspot_client
        self.fetcher = site_fetcher
        self._engine = None
        if config.DETECTION_ENGINE == "technographics":
            from .detectors.engine import TechEngine

            self._engine = TechEngine(
                selection_path=config.SELECTION_FILE,
                enable_dns=config.ENABLE_DNS,
                dns_timeout=config.DNS_TIMEOUT,
                enable_probes=config.ENABLE_SUBDOMAIN_PROBES,
                probe_timeout=config.PROBE_TIMEOUT,
            )
            _logger.info(
                "engine=technographics vendors=%d dns=%s",
                len(self._engine.library.vendors), config.ENABLE_DNS,
            )
        else:
            _logger.info("engine=legacy")

    def ensure_property(self) -> None:
        """Idempotently create the `technographic_signals` company property.
        Exposed publicly so chunked runners can call it once at the top
        of a multi-chunk session instead of on every chunk."""
        self.hubspot.ensure_property_exists(
            object_type="companies",
            property_name=_PROPERTY_NAME,
            label=_PROPERTY_LABEL,
        )

    def run(
        self,
        list_id: str,
        dry_run: bool = False,
        limit: int | None = None,
    ) -> RunReport:
        self.ensure_property()

        companies = list(self.hubspot.get_companies_in_list(list_id))
        if limit is not None and limit > 0:
            companies = companies[:limit]

        return self.run_companies(
            companies, dry_run=dry_run, list_id_for_log=list_id, limit_for_log=limit,
        )

    def run_companies(
        self,
        companies: list[dict],
        dry_run: bool = False,
        list_id_for_log: str | None = None,
        limit_for_log: int | None = None,
    ) -> RunReport:
        """Run fetch+detect+(optional) write for a pre-materialized list of
        company dicts (each must have `id`, `name`, `domain`, `website`).
        Used both by `run()` for the standard list-driven path and by the
        chunked runner (`scripts/run_chunked.py`)."""
        started = datetime.now()
        report = RunReport(started_at=started.isoformat(timespec="seconds"))
        report.total_companies = len(companies)
        _logger.info(
            "run_start list_id=%s total=%d dry_run=%s limit=%s",
            list_id_for_log, len(companies), dry_run, limit_for_log,
        )

        if not companies:
            return self._finalize(report, started)

        eligible = self._partition_eligible(companies, report)

        if not eligible:
            return self._finalize(report, started)

        self._process_eligible(eligible, report, dry_run)

        return self._finalize(report, started)

    def _partition_eligible(
        self, companies: list[dict], report: RunReport,
    ) -> list[tuple[dict, str]]:
        eligible: list[tuple[dict, str]] = []
        for company in companies:
            raw_url = company.get("website") or company.get("domain")
            if not raw_url:
                _logger.info(
                    "skip company_id=%s name=%s reason=no_url",
                    company.get("id"), company.get("name"),
                )
                report.skipped += 1
                report.results.append({
                    "company_id": company.get("id"),
                    "name": company.get("name"),
                    "domain": company.get("domain"),
                    "signals_string": None,
                    "error": "no website or domain property",
                    "status": "skipped",
                })
                continue
            _logger.info(
                "queue company_id=%s name=%s url=%s",
                company.get("id"), company.get("name"), raw_url,
            )
            eligible.append((company, raw_url))
        return eligible

    def _process_eligible(
        self,
        eligible: list[tuple[dict, str]],
        report: RunReport,
        dry_run: bool,
    ) -> None:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            transient=False,
        ) as progress:
            task = progress.add_task("Processing companies", total=len(eligible))

            with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_FETCHES) as pool:
                future_to_company = {
                    pool.submit(self._fetch_and_detect, company, url): company
                    for company, url in eligible
                }

                for fut in as_completed(future_to_company):
                    company = future_to_company[fut]
                    self._handle_result(fut, company, report, dry_run)
                    progress.advance(task)

    def _handle_result(
        self,
        fut,
        company: dict,
        report: RunReport,
        dry_run: bool,
    ) -> None:
        company_id = company.get("id")
        name = company.get("name")
        domain = company.get("domain")

        try:
            outcome = fut.result(timeout=_PER_COMPANY_TIMEOUT_S)
        except FuturesTimeoutError:
            _logger.error("timeout company_id=%s domain=%s", company_id, domain)
            report.failed += 1
            report.results.append({
                "company_id": company_id,
                "name": name,
                "domain": domain,
                "signals_string": None,
                "error": "per-company timeout (60s)",
                "status": "failed",
            })
            return
        except Exception as exc:
            _logger.error(
                "worker_failure company_id=%s domain=%s error=%s",
                company_id, domain, exc,
            )
            report.failed += 1
            report.results.append({
                "company_id": company_id,
                "name": name,
                "domain": domain,
                "signals_string": None,
                "error": str(exc),
                "status": "failed",
            })
            return

        signals_string = outcome["signals_string"]
        fetch_error = outcome.get("error")
        signals_count = outcome.get("count", 0)

        if not dry_run and company_id:
            self.hubspot.update_company(
                company_id, {_PROPERTY_NAME: signals_string},
            )

        _logger.info(
            "processed company_id=%s domain=%s signals=%d status=%s%s",
            company_id, domain, signals_count,
            "ok" if not fetch_error else "fetch_error",
            " [dry_run]" if dry_run else "",
        )
        report.succeeded += 1
        report.results.append({
            "company_id": company_id,
            "name": name,
            "domain": domain,
            "signals_string": signals_string,
            "error": fetch_error,
            "status": "succeeded",
        })

    def _fetch_and_detect(self, company: dict, url: str) -> dict:
        """Worker — fetch a single URL and detect technologies.

        With the technographics engine, this also runs a DNS pass keyed on
        the company's domain. Never raises: the fetcher is defensive and
        this `try` is belt-and-suspenders for the detectors / formatter.
        """
        try:
            fr = self.fetcher.fetch(url)
            if self._engine is not None:
                domain = company.get("domain") or company.get("website")
                hits = self._engine.detect(domain, url, fr)
            else:
                hits = []
                for module in (crm, ad_pixels, martech, salestech):
                    hits.extend(module.detect(fr))
            filtered = filter_low_confidence(hits)
            return {
                "signals_string": format_signals(filtered),
                "count": len(filtered),
                "error": fr.error,
            }
        except Exception as exc:
            return {
                "signals_string": _NO_SIGNALS,
                "count": 0,
                "error": str(exc),
            }

    def _finalize(self, report: RunReport, started: datetime) -> RunReport:
        finished = datetime.now()
        report.finished_at = finished.isoformat(timespec="seconds")
        report.duration_seconds = round((finished - started).total_seconds(), 2)
        self._write_report(report, started)
        self._print_summary(report)
        return report

    @staticmethod
    def _write_report(report: RunReport, started: datetime) -> None:
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        path = config.LOGS_DIR / f"run_{started.strftime('%Y%m%d_%H%M%S')}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, indent=2, default=str)
        _logger.info("report_written path=%s", path)

    @staticmethod
    def _print_summary(report: RunReport) -> None:
        console = Console()

        counters = Table(title="Run summary", show_header=False)
        counters.add_row("Started", report.started_at)
        counters.add_row("Finished", report.finished_at)
        counters.add_row("Duration", f"{report.duration_seconds:.1f}s")
        counters.add_row("Total companies", str(report.total_companies))
        counters.add_row("Succeeded", str(report.succeeded))
        counters.add_row("Skipped (no URL)", str(report.skipped))
        counters.add_row("Failed", str(report.failed))
        console.print(counters)

        vendor_counter: Counter[str] = Counter()
        for r in report.results:
            ss = r.get("signals_string")
            if not ss or ss == _NO_SIGNALS:
                continue
            for chunk in ss.split(" | "):
                _, _, names = chunk.partition(": ")
                for n in names.split(", "):
                    n = n.strip()
                    if n:
                        vendor_counter[n] += 1

        if vendor_counter:
            top = Table(title="Top detected vendors", show_header=True)
            top.add_column("Vendor")
            top.add_column("Hits", justify="right")
            for vendor_name, count in vendor_counter.most_common(10):
                top.add_row(vendor_name, str(count))
            console.print(top)
