"""Collect rendered-page data with Playwright (headless Chromium).

Playwright is an optional dependency (``pip install 'technographics[web]'`` then
``playwright install chromium``). Import errors and navigation failures are
surfaced as a ``PageData`` with an ``error`` field rather than raising, so batch
scans never abort on a single bad site.
"""

from __future__ import annotations

from technographics.web_matcher import PageData

NAV_TIMEOUT_MS = 20_000

# JS evaluated in-page to enumerate likely-vendor window globals. We can't dump
# every key (huge + noisy), so we collect own-enumerable top-level keys plus a
# few known nested paths that signatures reference.
_GLOBALS_JS = r"""
() => {
  const keys = new Set();
  try {
    for (const k of Object.getOwnPropertyNames(window)) keys.add(k);
  } catch (e) {}
  const nested = [
    'analytics.SNIPPET_VERSION', 'analytics.VERSION',
  ];
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


def _normalize_url(domain: str) -> str:
    if domain.startswith(("http://", "https://")):
        return domain
    return f"https://{domain}"


async def collect_web_async(domain: str, timeout_ms: int = NAV_TIMEOUT_MS) -> PageData:
    url = _normalize_url(domain)
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return PageData(final_url=url, error="playwright not installed; pip install 'technographics[web]'")

    script_srcs: list[str] = []
    page_data = PageData(final_url=url)

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            page.on(
                "request",
                lambda req: script_srcs.append(req.url) if req.resource_type == "script" else None,
            )

            response = None
            try:
                response = await page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except Exception:
                # networkidle can time out on chatty pages; fall back to domcontentloaded
                try:
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                except Exception as exc:
                    await browser.close()
                    return PageData(final_url=url, error=f"navigation failed: {exc}")

            page_data.final_url = page.url
            page_data.html = await page.content()
            page_data.script_srcs = list(dict.fromkeys(script_srcs))
            try:
                page_data.js_globals = await page.evaluate(_GLOBALS_JS)
            except Exception:
                page_data.js_globals = []

            cookies = await context.cookies()
            page_data.cookies = {c["name"]: c.get("value", "") for c in cookies}

            if response is not None:
                page_data.headers = {k.lower(): v for k, v in response.headers.items()}

            try:
                metas = await page.eval_on_selector_all(
                    "meta[name], meta[property]",
                    "els => els.map(e => [e.getAttribute('name') || e.getAttribute('property'), e.getAttribute('content') || ''])",
                )
                page_data.meta_tags = {name.lower(): content for name, content in metas if name}
            except Exception:
                page_data.meta_tags = {}

            await browser.close()
    except Exception as exc:  # pragma: no cover - defensive
        return PageData(final_url=url, error=f"{type(exc).__name__}: {exc}")

    return page_data


def collect_web(domain: str, timeout_ms: int = NAV_TIMEOUT_MS) -> PageData:
    import asyncio

    return asyncio.run(collect_web_async(domain, timeout_ms))
