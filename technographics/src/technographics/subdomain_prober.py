"""Probe-then-fetch: confirm portal-style vendors on named subdomains.

Some enterprise systems (Oracle E-Business Suite is the canonical case) are
invisible on the marketing site the pipeline fetches: the product lives on a
separate host (``erp.acme.com``, ``isupplier.acme.com``) that only reveals
itself when you request a well-known path (``/OA_HTML/AppsLogin``).

A vendor opts into probing by having BOTH:

- a :class:`DNSSignature` with ``subdomains_to_probe`` (candidate hosts), and
- a :class:`WebSignature` with ``probe_paths`` (well-known paths, with
  optional extra body patterns per path).

For each ``https://<sub>.<domain><path>`` a cheap static GET is issued (no
Chromium) and ONLY that vendor's web signature is matched against the
response, with the per-path ``probe_paths`` patterns folded in as extra HTML
patterns. Two guards keep catch-all servers from producing false positives:

- responses with a 4xx/5xx status are ignored, and
- a detection whose evidence is nothing but the URL we constructed ourselves
  is discarded (an SPA router happily 200s any path back at you). A redirect
  that lands OUTSIDE the probed site (e.g. ``erp.acme.com`` bouncing to an
  ``*.oraclecloud.com`` tenant) is organic evidence, so URL matches count
  there; a redirect back to the apex/www marketing site does not, since
  catch-alls routinely funnel every subdomain to www with the path intact.

All failures (NXDOMAIN, TLS, timeouts) are swallowed so probing never blocks
the main pipelines. TLS verification is off: on-prem portals routinely run
self-signed certs, and only the response shape is fingerprinted.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import replace
from typing import Awaitable, Callable, Optional
from urllib.parse import urlsplit

from technographics.schema import Detection, DNSSignature, Vendor, WebSignature
from technographics.web_matcher import PageData, WebMatcher

DEFAULT_TIMEOUT = 4.0
MAX_PROBES_PER_VENDOR = 8
_CONCURRENCY = 8
_MAX_BODY_CHARS = 512_000  # fingerprints sit in the first chunk of HTML

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_SCRIPT_SRC_RE = re.compile(r"<script[^>]+?src=[\"']([^\"']+)[\"']", re.IGNORECASE)
_META_RE = re.compile(
    r"<meta\s+[^>]*?(?:name|property)=[\"']([^\"']+)[\"'][^>]*?content=[\"']([^\"']*)[\"']",
    re.IGNORECASE,
)

# An async callable url -> PageData | None; injectable for tests.
Fetcher = Callable[[str], Awaitable[Optional[PageData]]]


def probe_specs(
    dns_signatures: dict[str, DNSSignature],
    web_signatures: dict[str, WebSignature],
) -> dict[str, tuple[list[str], dict[str, list]]]:
    """``vendor_id -> (subdomains, probe_paths)`` for vendors that opted in."""
    specs: dict[str, tuple[list[str], dict[str, list]]] = {}
    for vendor_id, web_sig in web_signatures.items():
        dns_sig = dns_signatures.get(vendor_id)
        if not web_sig.probe_paths or dns_sig is None or not dns_sig.subdomains_to_probe:
            continue
        specs[vendor_id] = (list(dns_sig.subdomains_to_probe), dict(web_sig.probe_paths))
    return specs


def _clean_domain(domain: str) -> str:
    d = domain.strip().strip(".").lower()
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    d = d.split("/", 1)[0].split("?", 1)[0]
    if d.startswith("www."):
        d = d[4:]
    return d


def _page_from_response(resp) -> PageData:
    html = resp.text[:_MAX_BODY_CHARS]
    cookies: dict[str, str] = {}
    for r in (*resp.history, resp):
        for set_cookie in r.headers.get_list("set-cookie"):
            name = set_cookie.split("=", 1)[0].strip()
            if name:
                cookies[name] = ""
    return PageData(
        final_url=str(resp.url),
        script_srcs=list(dict.fromkeys(_SCRIPT_SRC_RE.findall(html))),
        cookies=cookies,
        headers={k.lower(): v for k, v in resp.headers.items()},
        html=html,
        meta_tags={name.lower(): content for name, content in _META_RE.findall(html)},
    )


async def _default_fetch(url: str, timeout: float) -> PageData | None:
    import httpx

    for attempt_url in (url, url.replace("https://", "http://", 1)):
        try:
            async with httpx.AsyncClient(
                verify=False,
                follow_redirects=True,
                timeout=timeout,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                resp = await client.get(attempt_url)
        except Exception:
            continue
        if resp.status_code >= 400:
            return None
        return _page_from_response(resp)
    return None


def _has_non_url_evidence(detection: Detection) -> bool:
    """True when at least one evidence line came from the response itself.

    The probe URL is constructed by us, so a match on ``url_patterns`` alone
    only proves the server answered — not that the vendor is behind it.
    """
    return any(not ev.startswith("url ") for ev in detection.evidence)


def _url_evidence_trusted(requested_url: str, final_url: str, domain: str) -> bool:
    """True when ``final_url`` is an organic redirect worth matching on.

    A redirect that leaves the probed site (an ``*.oraclecloud.com`` tenant,
    an SSO host) was chosen by the server, not by us. A "redirect" to the
    requested URL itself, or back to the apex/www marketing site, is not
    trustworthy: wildcard-DNS + catch-all setups funnel every subdomain to
    www with the original path intact.
    """
    req = urlsplit(requested_url)
    fin = urlsplit(final_url)
    if not fin.netloc or fin.netloc.lower() == req.netloc.lower():
        return False
    host = (fin.hostname or "").lower()
    return host not in (domain, f"www.{domain}")


async def probe_subdomains_async(
    domain: str,
    dns_signatures: dict[str, DNSSignature],
    web_signatures: dict[str, WebSignature],
    vendors: dict[str, Vendor],
    timeout: float = DEFAULT_TIMEOUT,
    max_probes_per_vendor: int = MAX_PROBES_PER_VENDOR,
    fetcher: Fetcher | None = None,
) -> list[Detection]:
    domain = _clean_domain(domain)
    specs = probe_specs(dns_signatures, web_signatures)
    if not domain or not specs:
        return []

    fetch = fetcher
    if fetch is None:
        async def fetch(url: str) -> PageData | None:
            return await _default_fetch(url, timeout)

    semaphore = asyncio.Semaphore(_CONCURRENCY)

    async def _probe_one(
        vendor_id: str, sig: WebSignature, url: str, path_patterns: list
    ) -> Detection | None:
        async with semaphore:
            page = await fetch(url)
        if page is None or page.error:
            return None
        probe_sig = replace(
            sig, html_patterns=[*sig.html_patterns, *path_patterns], probe_paths={}
        )
        detections = WebMatcher({vendor_id: probe_sig}, vendors).match(page)
        for det in detections:
            if _has_non_url_evidence(det) or _url_evidence_trusted(
                url, page.final_url, domain
            ):
                return replace(
                    det,
                    source="probe",
                    evidence=[f"probe {page.final_url}", *det.evidence],
                )
        return None

    tasks = []
    for vendor_id, (subdomains, probe_paths) in specs.items():
        sig = web_signatures[vendor_id]
        # Path-major: cover every host on the primary (first-listed) path before
        # spending the per-vendor budget on secondary paths. Under the cap,
        # breadth of hosts matters more than depth of paths — a portal reveals
        # itself on one good path, but we don't know which host it lives on.
        pairs = [
            (f"https://{sub}.{domain}{path}", path)
            for path in probe_paths
            for sub in subdomains
        ][:max_probes_per_vendor]
        for url, path in pairs:
            tasks.append(_probe_one(vendor_id, sig, url, probe_paths[path]))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # One detection per vendor: keep the highest-confidence hit.
    best: dict[str, Detection] = {}
    for det in results:
        if not isinstance(det, Detection):
            continue
        current = best.get(det.vendor_id)
        if current is None or det.confidence > current.confidence:
            best[det.vendor_id] = det
    return sorted(best.values(), key=lambda d: d.confidence, reverse=True)


def probe_subdomains(
    domain: str,
    dns_signatures: dict[str, DNSSignature],
    web_signatures: dict[str, WebSignature],
    vendors: dict[str, Vendor],
    timeout: float = DEFAULT_TIMEOUT,
    max_probes_per_vendor: int = MAX_PROBES_PER_VENDOR,
    fetcher: Fetcher | None = None,
) -> list[Detection]:
    """Synchronous convenience wrapper around :func:`probe_subdomains_async`."""
    return asyncio.run(
        probe_subdomains_async(
            domain,
            dns_signatures,
            web_signatures,
            vendors,
            timeout=timeout,
            max_probes_per_vendor=max_probes_per_vendor,
            fetcher=fetcher,
        )
    )
