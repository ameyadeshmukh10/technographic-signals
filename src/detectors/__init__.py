"""Detector package.

A `FetchResult` from `site_fetcher` is run against the signature library
to produce a list of `DetectionHit`s per category. The shared logic lives
in `_run_detection`; each per-category module (`crm`, `ad_pixels`,
`martech`, `salestech`) is a thin wrapper that pins the category.

All regex patterns are compiled once at module load (`_COMPILED`) and
reused on every call. Patterns are matched case-insensitively via
`re.IGNORECASE`; signature strings should not embed `(?i)` themselves.

Confidence filtering (dropping `"low"`-confidence hits unless another
category corroborates the same vendor) is the orchestrator's job —
detectors return everything they find.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .signatures import Signature, get_signatures_by_category, load_signatures

if TYPE_CHECKING:
    from ..site_fetcher import FetchResult


@dataclass
class DetectionHit:
    """A single technology detected on a page.

    `evidence` holds up to 3 short snippets (each ≤200 chars) showing
    *what* matched — the script src URL, a slice of HTML around the
    matched regex, or a cookie name. Used by the orchestrator for
    logging and for CSV/debug output.
    """

    name: str
    category: str
    confidence: str
    evidence: list[str] = field(default_factory=list)


_EVIDENCE_MAX_CHARS = 200
_EVIDENCE_CONTEXT_CHARS = 20  # ~20 each side of a match → ~40 chars total
_EVIDENCE_LIMIT = 3


_CompiledForSignature = dict[str, list[re.Pattern[str]]]


def _compile_all() -> dict[str, _CompiledForSignature]:
    """Compile every signature's regex patterns. Keyed by signature name;
    same-name signatures across categories (Drift, Intercom) share
    identical patterns today, so a name key is sufficient."""
    out: dict[str, _CompiledForSignature] = {}
    for sig in load_signatures():
        out[sig.name] = {
            "patterns": [re.compile(p, re.IGNORECASE) for p in sig.patterns],
            "script_src_patterns": [re.compile(p, re.IGNORECASE) for p in sig.script_src_patterns],
            "dom_patterns": [re.compile(p, re.IGNORECASE) for p in sig.dom_patterns],
            "cookie_patterns": [re.compile(p, re.IGNORECASE) for p in sig.cookie_patterns],
        }
    return out


_COMPILED: dict[str, _CompiledForSignature] = _compile_all()


def _evidence_from_match(text: str, match: re.Match[str]) -> str:
    start = max(match.start() - _EVIDENCE_CONTEXT_CHARS, 0)
    end = min(match.end() + _EVIDENCE_CONTEXT_CHARS, len(text))
    snippet = text[start:end]
    snippet = " ".join(snippet.split())  # collapse whitespace for readability
    return snippet[:_EVIDENCE_MAX_CHARS]


def _truncate(s: str) -> str:
    return s[:_EVIDENCE_MAX_CHARS]


def _detect_one(sig: Signature, fetch_result: "FetchResult") -> DetectionHit | None:
    """Run one signature against a FetchResult. Returns a single hit
    (with deduped, capped evidence) or None if nothing matched."""
    compiled = _COMPILED.get(sig.name)
    if compiled is None:
        return None

    evidence: list[str] = []
    seen: set[str] = set()

    def add(snippet: str) -> None:
        snippet = _truncate(snippet)
        if snippet and snippet not in seen:
            seen.add(snippet)
            evidence.append(snippet)

    def full() -> bool:
        return len(evidence) >= _EVIDENCE_LIMIT

    # 1. script src URLs
    for src in fetch_result.script_srcs:
        if full():
            break
        if any(pat.search(src) for pat in compiled["script_src_patterns"]):
            add(src)

    # 2. inline JS / body patterns
    if not full():
        for pat in compiled["patterns"]:
            for m in pat.finditer(fetch_result.html):
                add(_evidence_from_match(fetch_result.html, m))
                if full():
                    break
            if full():
                break

    # 3. raw HTML / DOM patterns
    if not full():
        for pat in compiled["dom_patterns"]:
            for m in pat.finditer(fetch_result.html):
                add(_evidence_from_match(fetch_result.html, m))
                if full():
                    break
            if full():
                break

    # 4. cookie names
    if not full():
        for cookie in fetch_result.cookies:
            if full():
                break
            if any(pat.search(cookie) for pat in compiled["cookie_patterns"]):
                add(cookie)

    if not evidence:
        return None

    return DetectionHit(
        name=sig.name,
        category=sig.category,
        confidence=sig.confidence,
        evidence=evidence,
    )


def _run_detection(category: str, fetch_result: "FetchResult") -> list[DetectionHit]:
    """Shared implementation. Each per-category module calls this with
    its own category name."""
    hits: list[DetectionHit] = []
    for sig in get_signatures_by_category(category):
        hit = _detect_one(sig, fetch_result)
        if hit is not None:
            hits.append(hit)
    return hits
