"""Site fetcher — pulls a company's website and extracts the surface
features (script src URLs, cookies, raw HTML) we feed to the detectors.

Two strategies are available:

- `fetch_static`: a single GET via `requests`. Fast, cheap, and enough for
  any site that renders content server-side.
- `fetch_rendered`: a Chromium page via Playwright. Necessary for SPAs and
  for catching pixels/scripts that only load after JS executes.

The public `fetch` method tries static first and falls back to rendered when
the static response looks thin (small HTML, SPA shell, error, or 4xx/5xx)
*and* `USE_PLAYWRIGHT_FALLBACK` is on. Whichever attempt produced more
script src evidence wins.

Playwright is imported lazily inside `_rendered_request` so users with
`USE_PLAYWRIGHT_FALLBACK=false` don't need it installed.

Defensive by design: every public entry point catches exceptions and
returns a `FetchResult` with `error` set, so a single bad URL can never
abort a batch run.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from rich.logging import RichHandler
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from . import config


_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)

_SMALL_HTML_THRESHOLD_BYTES = 50_000
_NETWORKIDLE_TIMEOUT_MS = 8_000
_MAX_REDIRECTS = 5


_logger = logging.getLogger("technographic.fetcher")
if not _logger.handlers:
    _handler = RichHandler(show_path=False, rich_tracebacks=False, markup=False)
    _logger.addHandler(_handler)
    _logger.setLevel(config.LOG_LEVEL)
    _logger.propagate = False


@dataclass
class FetchResult:
    """The output of a single site fetch.

    `script_srcs` holds the union of `<script src=...>` values parsed from
    HTML and (for rendered fetches) every script-resource URL observed on
    the network. `cookies` holds cookie *names only* — never values.

    `headers` are the (lowercased-key) HTTP response headers; `meta_tags`
    are `<meta name|property=… content=…>` pairs keyed by lowercased name;
    `js_globals` are `window` property names — only populated on rendered
    fetches, since enumerating them requires executing JS. These three feed
    the technographics matcher's header/meta/js-global signal channels.
    """

    url: str
    status: int = 0
    html: str = ""
    script_srcs: list[str] = field(default_factory=list)
    cookies: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    meta_tags: dict[str, str] = field(default_factory=dict)
    js_globals: list[str] = field(default_factory=list)
    rendered: bool = False
    error: str | None = None


def _normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("empty URL")
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    if not parsed.netloc:
        raise ValueError(f"invalid URL: {raw!r}")
    return raw.rstrip("/")


def _extract_script_srcs(html: str) -> list[str]:
    if not html:
        return []
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return []
    out: list[str] = []
    for tag in soup.find_all("script", src=True):
        src = (tag.get("src") or "").strip()
        if src:
            out.append(src)
    return out


def _extract_meta_tags(html: str) -> dict[str, str]:
    """Parse `<meta name|property=… content=…>` into {name.lower(): content}.

    When a name repeats, the first occurrence wins. Mirrors how the
    technographics web collector builds `meta_tags`."""
    if not html:
        return {}
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return {}
    out: dict[str, str] = {}
    for tag in soup.find_all("meta"):
        name = tag.get("name") or tag.get("property")
        if not name:
            continue
        key = name.strip().lower()
        if key in out:
            continue
        out[key] = (tag.get("content") or "").strip()
    return out


# Evaluated in-page (rendered fetch) to enumerate likely-vendor window globals.
# Mirrors technographics/src/technographics/web_collector.py::_GLOBALS_JS.
_GLOBALS_JS = r"""
() => {
  const keys = new Set();
  try {
    for (const k of Object.getOwnPropertyNames(window)) keys.add(k);
  } catch (e) {}
  const nested = ['analytics.SNIPPET_VERSION', 'analytics.VERSION'];
  for (const path of nested) {
    try {
      let cur = window;
      for (const part of path.split('.')) cur = cur[part];
      if (cur !== undefined) keys.add(path);
    } catch (e) {}
  }
  return Array.from(keys);
}
"""


def _looks_like_spa_shell(html: str) -> bool:
    """Heuristic: a body with at most two real children and almost no
    visible text — typical of `<div id="root"></div>`-style SPA shells
    that need JS to render."""
    if not html:
        return False
    try:
        soup = BeautifulSoup(html, "lxml")
    except Exception:
        return False
    body = soup.body
    if body is None:
        return False
    real_children = [
        c for c in body.find_all(recursive=False)
        if c.name not in ("script", "noscript", "style")
    ]
    text = body.get_text(strip=True)
    return len(real_children) <= 2 and len(text) < 200


class SiteFetcher:
    """Fetches a website and extracts surface features for detection."""

    def __init__(self) -> None:
        self._session: requests.Session | None = None

    def _get_session(self) -> requests.Session:
        if self._session is None:
            s = requests.Session()
            s.headers.update({
                "User-Agent": _USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            })
            s.max_redirects = _MAX_REDIRECTS
            self._session = s
        return self._session

    def fetch_static(self, url: str) -> FetchResult:
        """Fetch via `requests`. Always returns a `FetchResult` — failures
        come back with `error` set rather than raising."""
        start = time.monotonic()
        try:
            result = self._static_request(url)
        except Exception as exc:
            dur_ms = int((time.monotonic() - start) * 1000)
            _logger.warning(
                "static fetch failed url=%s error=%s duration_ms=%d",
                url, exc, dur_ms,
            )
            return FetchResult(url=url, error=str(exc))

        dur_ms = int((time.monotonic() - start) * 1000)
        _logger.info(
            "static fetch url=%s status=%s scripts=%d duration_ms=%d",
            result.url, result.status, len(result.script_srcs), dur_ms,
        )
        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=2),
        retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
        reraise=True,
    )
    def _static_request(self, url: str) -> FetchResult:
        session = self._get_session()
        resp = session.get(
            url,
            timeout=config.REQUEST_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        html = resp.text or ""
        return FetchResult(
            url=resp.url,
            status=resp.status_code,
            html=html,
            script_srcs=_extract_script_srcs(html),
            cookies=[c.name for c in resp.cookies],
            headers={k.lower(): v for k, v in resp.headers.items()},
            meta_tags=_extract_meta_tags(html),
            js_globals=[],  # requires a JS engine — see fetch_rendered
            rendered=False,
        )

    def fetch_rendered(self, url: str) -> FetchResult:
        """Fetch via headless Chromium. Playwright is imported lazily so
        the dependency is only needed when fallback is enabled."""
        start = time.monotonic()
        try:
            result = self._rendered_request(url)
        except Exception as exc:
            dur_ms = int((time.monotonic() - start) * 1000)
            _logger.warning(
                "rendered fetch failed url=%s error=%s duration_ms=%d",
                url, exc, dur_ms,
            )
            return FetchResult(url=url, rendered=True, error=str(exc))

        dur_ms = int((time.monotonic() - start) * 1000)
        _logger.info(
            "rendered fetch url=%s status=%s scripts=%d duration_ms=%d",
            result.url, result.status, len(result.script_srcs), dur_ms,
        )
        return result

    def _rendered_request(self, url: str) -> FetchResult:
        from playwright.sync_api import (
            TimeoutError as PlaywrightTimeoutError,
            sync_playwright,
        )

        observed_scripts: list[str] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(user_agent=_USER_AGENT)
                page = context.new_page()

                def on_request(request) -> None:
                    if request.resource_type == "script":
                        observed_scripts.append(request.url)

                page.on("request", on_request)

                response = page.goto(
                    url,
                    timeout=config.REQUEST_TIMEOUT_SECONDS * 1000,
                    wait_until="domcontentloaded",
                )
                try:
                    page.wait_for_load_state("networkidle", timeout=_NETWORKIDLE_TIMEOUT_MS)
                except PlaywrightTimeoutError:
                    pass

                final_url = page.url
                status = response.status if response is not None else 0
                html = page.content()
                cookie_names = [c["name"] for c in context.cookies()]

                try:
                    js_globals = page.evaluate(_GLOBALS_JS) or []
                except Exception:
                    js_globals = []

                headers = {}
                if response is not None:
                    try:
                        headers = {k.lower(): v for k, v in response.headers.items()}
                    except Exception:
                        headers = {}

                try:
                    pairs = page.eval_on_selector_all(
                        "meta[name], meta[property]",
                        "els => els.map(e => [e.getAttribute('name') || e.getAttribute('property'), e.getAttribute('content') || ''])",
                    )
                    meta_tags = {}
                    for name, content in pairs:
                        if name and name.lower() not in meta_tags:
                            meta_tags[name.lower()] = content
                except Exception:
                    meta_tags = {}
            finally:
                browser.close()

        merged = list(dict.fromkeys(observed_scripts + _extract_script_srcs(html)))
        return FetchResult(
            url=final_url,
            status=status,
            html=html,
            script_srcs=merged,
            cookies=cookie_names,
            headers=headers,
            meta_tags=meta_tags,
            js_globals=js_globals,
            rendered=True,
        )

    def fetch(self, url: str) -> FetchResult:
        """Top-level fetch. Normalizes the URL, tries static, falls back
        to rendered when configured and the static result looks thin or
        failed. Returns whichever attempt yielded more script_srcs."""
        try:
            normalized = _normalize_url(url)
        except Exception as exc:
            _logger.warning("invalid url=%s error=%s", url, exc)
            return FetchResult(url=url, error=str(exc))

        # Max-recall mode: render every page (JS globals require a JS engine).
        # Fall back to static only if the render errored or returned no HTML.
        if config.ALWAYS_RENDER:
            rendered_first = self.fetch_rendered(normalized)
            if rendered_first.error is None and rendered_first.html:
                return rendered_first
            _logger.info("always_render fell back to static url=%s", normalized)
            return self.fetch_static(normalized)

        static_result = self.fetch_static(normalized)

        should_fallback = config.USE_PLAYWRIGHT_FALLBACK and (
            static_result.error is not None
            or static_result.status >= 400
            or len(static_result.html.encode("utf-8", "ignore")) < _SMALL_HTML_THRESHOLD_BYTES
            or _looks_like_spa_shell(static_result.html)
        )

        if not should_fallback:
            return static_result

        _logger.info("falling back to rendered fetch url=%s", normalized)
        rendered_result = self.fetch_rendered(normalized)

        if len(rendered_result.script_srcs) >= len(static_result.script_srcs):
            return rendered_result
        return static_result


def _print_summary(result: FetchResult) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="FetchResult", show_header=False)
    table.add_row("url", result.url)
    table.add_row("status", str(result.status))
    table.add_row("rendered", str(result.rendered))
    table.add_row("html length", f"{len(result.html):,} chars")
    table.add_row("script_srcs", str(len(result.script_srcs)))
    table.add_row("cookies", str(len(result.cookies)))
    table.add_row("headers", str(len(result.headers)))
    table.add_row("meta_tags", str(len(result.meta_tags)))
    table.add_row("js_globals", str(len(result.js_globals)))
    table.add_row("error", result.error or "-")
    console.print(table)
    if result.script_srcs:
        console.print("[bold]first 10 script srcs:[/bold]")
        for src in result.script_srcs[:10]:
            console.print(f"  {src}")
    if result.cookies:
        console.print(f"[bold]cookies:[/bold] {', '.join(result.cookies)}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.site_fetcher <url>")
        sys.exit(1)

    fetcher = SiteFetcher()
    result = fetcher.fetch(sys.argv[1])
    _print_summary(result)
