"""Shared pytest fixtures.

Sets a placeholder `HUBSPOT_ACCESS_TOKEN` *before* importing anything from
`src`, so `src/config.py`'s import-time validation passes during tests
without requiring a real `.env`. A real value in the user's environment
takes precedence (we use `setdefault`).
"""

from __future__ import annotations

import os

os.environ.setdefault("HUBSPOT_ACCESS_TOKEN", "test-token-not-real")

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from src.site_fetcher import FetchResult


FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _extract_script_srcs(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    out: list[str] = []
    for tag in soup.find_all("script", src=True):
        src = (tag.get("src") or "").strip()
        if src:
            out.append(src)
    return out


@pytest.fixture
def make_fetch_result():
    """Build a FetchResult from a saved HTML fixture.

    The helper parses `<script src=...>` tags out of the HTML to populate
    `script_srcs` exactly as the production fetcher would on a static
    request. `cookies` defaults to empty (most tracking cookies are only
    set on the rendered path); pass an explicit list to simulate them.
    """
    def _make(filename: str, *, cookies: list[str] | None = None) -> FetchResult:
        path = FIXTURES_DIR / filename
        html = path.read_text(encoding="utf-8")
        return FetchResult(
            url=f"https://example.test/{filename}",
            status=200,
            html=html,
            script_srcs=_extract_script_srcs(html),
            cookies=cookies or [],
            rendered=False,
        )

    return _make
