"""Technographics-backed detection engine.

Adapter that delegates per-company detection to the `technographics`
package (DNS + web + subdomain probes + noisy-OR fusion), scoped by a
selection file, and
maps the results back into the legacy `DetectionHit` shape so the rest of
the orchestrator (filtering, formatting, HubSpot writes) is unchanged.

The heavy library load + matcher construction happens once in
`__init__`; `detect()` is then cheap and thread-safe (read-only).
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import DetectionHit
from .category_map import bucket_for, confidence_bucket

# Make the sibling `technographics` package importable whether or not it's
# been pip-installed (`technographics/src/technographics`).
_REPO_ROOT = Path(__file__).resolve().parents[2]
_TECH_SRC = _REPO_ROOT / "technographics" / "src"
if _TECH_SRC.is_dir() and str(_TECH_SRC) not in sys.path:
    sys.path.insert(0, str(_TECH_SRC))

from technographics.dns_collector import collect_dns  # noqa: E402
from technographics.dns_matcher import DNSMatcher  # noqa: E402
from technographics.fusion import fuse  # noqa: E402
from technographics.loader import load_library, load_selection  # noqa: E402
from technographics.subdomain_prober import probe_specs, probe_subdomains  # noqa: E402
from technographics.web_matcher import PageData, WebMatcher  # noqa: E402

DEFAULT_SELECTION = _REPO_ROOT / "technographics" / "signatures" / "selection.marketing_sales.json"


def _clean_domain(domain: str | None) -> str | None:
    """Reduce a website/domain field to a bare apex-ish host for DNS."""
    if not domain:
        return None
    d = domain.strip().lower()
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    d = d.split("/", 1)[0].split("?", 1)[0]
    if d.startswith("www."):
        d = d[4:]
    return d or None


class TechEngine:
    def __init__(
        self,
        selection_path: str | Path | None = None,
        enable_dns: bool = True,
        dns_timeout: float = 3.0,
        enable_probes: bool = True,
        probe_timeout: float = 4.0,
    ) -> None:
        path = Path(selection_path) if selection_path else DEFAULT_SELECTION
        selection = load_selection(path) if path.is_file() else None
        self.library = load_library(selection=selection)
        self.web_matcher = WebMatcher(self.library.web_signatures, self.library.vendors)
        self.dns_matcher = DNSMatcher(self.library.dns_signatures, self.library.vendors)
        self.enable_dns = enable_dns
        self.dns_timeout = dns_timeout
        self.enable_probes = enable_probes
        self.probe_timeout = probe_timeout
        self._has_probe_specs = bool(
            probe_specs(self.library.dns_signatures, self.library.web_signatures)
        )
        self._subdomains = sorted(
            {
                sub
                for sig in self.library.dns_signatures.values()
                for sub in sig.subdomains_to_probe
            }
        )

    # -- web ---------------------------------------------------------------

    def _page_from_fetch(self, url: str, fetch_result) -> PageData:
        return PageData(
            final_url=url or getattr(fetch_result, "url", "") or "",
            js_globals=list(getattr(fetch_result, "js_globals", []) or []),
            script_srcs=list(getattr(fetch_result, "script_srcs", []) or []),
            cookies={name: "" for name in (getattr(fetch_result, "cookies", []) or [])},
            headers=dict(getattr(fetch_result, "headers", {}) or {}),
            html=getattr(fetch_result, "html", "") or "",
            meta_tags=dict(getattr(fetch_result, "meta_tags", {}) or {}),
        )

    # -- detect ------------------------------------------------------------

    def detect(self, domain: str | None, url: str, fetch_result) -> list[DetectionHit]:
        page = self._page_from_fetch(url, fetch_result)
        web_dets = self.web_matcher.match(page)

        dns_dets = []
        host = _clean_domain(domain) or _clean_domain(url)
        if self.enable_dns and host:
            try:
                records = collect_dns(host, subdomains=self._subdomains, timeout=self.dns_timeout)
                dns_dets = self.dns_matcher.match(records)
            except Exception:
                dns_dets = []  # DNS is best-effort; never block web detection

        probe_dets = []
        if self.enable_probes and self._has_probe_specs and host:
            try:
                probe_dets = probe_subdomains(
                    host,
                    self.library.dns_signatures,
                    self.library.web_signatures,
                    self.library.vendors,
                    timeout=self.probe_timeout,
                )
            except Exception:
                probe_dets = []  # probes are best-effort too

        fused = fuse(dns_dets, [*web_dets, *probe_dets])

        hits: list[DetectionHit] = []
        for det in fused:
            bucket = bucket_for(det.vendor_id, det.category)
            if bucket is None:
                continue
            hits.append(
                DetectionHit(
                    name=det.vendor_name,
                    category=bucket,
                    confidence=confidence_bucket(det.confidence),
                    evidence=list(det.evidence[:3]),
                )
            )
        return hits
