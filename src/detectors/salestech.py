"""Salestech detection. Thin wrapper around the shared `_run_detection` helper."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import DetectionHit, _run_detection

if TYPE_CHECKING:
    from ..site_fetcher import FetchResult


def detect(fetch_result: "FetchResult") -> list[DetectionHit]:
    return _run_detection("salestech", fetch_result)
