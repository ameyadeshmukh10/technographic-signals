# ARCHITECTURE.md — Technographic Signals

A complete walkthrough of what this system does, how it does it, every
component, and the design decisions behind each one. Aimed at anyone who
needs to extend, debug, or audit the pipeline.

For higher-level orientation see [AGENTS.md](AGENTS.md). For "how do I
run X" see [SKILLS.md](SKILLS.md). This file is the deepest layer.

---

## Table of contents

1. [Mission and scope](#1-mission-and-scope)
2. [End-to-end data flow](#2-end-to-end-data-flow)
3. [Module map](#3-module-map)
4. [The signature library — the brain of the system](#4-the-signature-library--the-brain-of-the-system)
5. [The fetch path — static plus Playwright fallback](#5-the-fetch-path--static-plus-playwright-fallback)
6. [The detection engine](#6-the-detection-engine)
7. [The HubSpot facade](#7-the-hubspot-facade)
8. [The orchestrator — concurrency, gates, and the run report](#8-the-orchestrator--concurrency-gates-and-the-run-report)
9. [Configuration and secrets](#9-configuration-and-secrets)
10. [The CLI surface](#10-the-cli-surface)
11. [The skills / scripts layer — agent-friendly playbooks](#11-the-skills--scripts-layer--agent-friendly-playbooks)
12. [Persistence — what lives on disk](#12-persistence--what-lives-on-disk)
13. [Error handling and recovery taxonomy](#13-error-handling-and-recovery-taxonomy)
14. [Performance characteristics (observed)](#14-performance-characteristics-observed)
15. [Test coverage and what isn't tested](#15-test-coverage-and-what-isnt-tested)
16. [Known limitations and design trade-offs](#16-known-limitations-and-design-trade-offs)
17. [Extension points — how to safely change things](#17-extension-points--how-to-safely-change-things)

---

## 1. Mission and scope

**What it does.** Given a HubSpot company list, the pipeline visits each
company's website, signature-matches the raw HTML and JavaScript for
go-to-market technologies (CRM, ad pixels, marketing tools, sales tools),
formats the findings into a single string, and writes that string to a
custom HubSpot company property called `technographic_signals`.

**Detection style.** Signature-based, not third-party-enriched. No
BuiltWith, no Wappalyzer, no Datanyze. Every detection is a regex match
against a known fingerprint: a CDN URL, an inline JS init call, a
markup pattern (like `<form action="webto.salesforce.com">`), or a cookie
name. The signature library — `src/detectors/signatures.py` — is the
single most important file in the project. Everything else is plumbing.

**The user-visible output** is a string like:

```
CRM: HubSpot | Ad Pixels: Google Tag Manager, Meta Pixel | Martech: HubSpot Forms | Salestech: 6sense
```

**What it intentionally does not do:**

- It does not bypass anti-bot defenses. Some sites (Salesforce, UBS)
  block headless Chromium with HTTP 403. We accept that as a real-world
  limitation rather than escalate into a cat-and-mouse arms race.
- It does not infer technology presence from absence (e.g., "this site
  doesn't load anything, therefore it must use X"). Every detection is
  affirmative.
- It does not score, rank, or recommend. The output is a literal list of
  vendors. Interpretation is the user's job.

---

## 2. End-to-end data flow

```
┌────────────────────────────────────────────────────────────────────────┐
│                              HubSpot API                               │
│   list memberships  ──────►  batch company read  ◄────  property PATCH │
└──────────────────────┬─────────────────────┬───────────────────▲───────┘
                       │                     │                   │
                       │ pages of            │ id, name, domain, │ technographic_
                       │ {record_id}         │ website           │ signals="..."
                       ▼                     ▼                   │
              ┌──────────────────────────────────────┐            │
              │    HubSpotClient (src/hubspot_       │            │
              │    client.py)                        │            │
              │  - extract_list_id(url|id)           │            │
              │  - get_companies_in_list (generator) │            │
              │  - update_company                    │            │
              │  - ensure_property_exists            │            │
              └──────────────────┬───────────────────┘            │
                                 │                                │
                                 │ stream of dicts                │
                                 │ {id, name, domain, website}    │
                                 ▼                                │
              ┌──────────────────────────────────────┐            │
              │       Orchestrator                   │            │
              │   (src/orchestrator.py)              │            │
              │  - run(list_id, dry_run, limit)      │            │
              │  - run_companies(companies, ...)     │            │
              │  - thread pool: fetch + detect       │            │
              │  - main thread: HubSpot writes       │            │
              └─────┬───────────────────┬────────────┘            │
                    │                   │                         │
        per-company │                   │ signals_string          │
            URL     │                   │ "CRM: ... | Salestech: …│
                    ▼                   └─────────────────────────┘
        ┌──────────────────────┐
        │ SiteFetcher (src/    │
        │ site_fetcher.py)     │
        │  - fetch_static      │  ◄── requests, tenacity retry
        │  - fetch_rendered    │  ◄── playwright chromium (lazy)
        │  - fetch (orchestr.) │
        └──────────┬───────────┘
                   │ FetchResult{url, status, html, script_srcs,
                   │             cookies, rendered, error}
                   ▼
        ┌──────────────────────┐
        │ Detectors (src/      │
        │ detectors/)          │     ┌─────────────────────────────┐
        │  crm.detect()        │ ──► │ signatures.py               │
        │  ad_pixels.detect()  │ ──► │  SIGNATURES: list[Signature]│
        │  martech.detect()    │ ──► │  - patterns, script_src,    │
        │  salestech.detect()  │ ──► │    dom, cookie patterns     │
        │  _run_detection()    │     │  - confidence: high/med/low │
        └──────────┬───────────┘     └─────────────────────────────┘
                   │
                   │ list[DetectionHit{name, category,
                   │                   confidence, evidence}]
                   ▼
        ┌──────────────────────────────────┐
        │ filter_low_confidence            │   drop low unless
        │ (orchestrator.py)                │   corroborated
        └──────────┬───────────────────────┘
                   ▼
        ┌──────────────────────────────────┐
        │ format_signals                   │   alphabetize per
        │ (orchestrator.py)                │   category, fixed
        └──────────┬───────────────────────┘   order, " | " join
                   ▼
              signals_string  →  back to Orchestrator  →  HubSpotClient.update_company
                                                          ↑ unless dry_run
```

Three concurrency contexts:

- **HubSpot reads**: synchronous, sequential, retried by tenacity on
  429/5xx. Throughput is limited by HubSpot's daily quota and 19 req/s
  burst.
- **Fetch + detect**: parallelized in a `ThreadPoolExecutor` sized to
  `MAX_CONCURRENT_FETCHES` (default 5). Each worker is independent.
- **HubSpot writes**: back on the main thread, sequential, as
  `as_completed` yields. Keeps rate-limit handling trivial.

---

## 3. Module map

| File | Responsibility | Public surface |
|---|---|---|
| `src/config.py` | Load `.env`, validate `HUBSPOT_ACCESS_TOKEN` at import time, expose typed constants. | `HUBSPOT_ACCESS_TOKEN`, `HUBSPOT_LIST_ID`, `LOG_LEVEL`, `REQUEST_TIMEOUT_SECONDS`, `USE_PLAYWRIGHT_FALLBACK`, `MAX_CONCURRENT_FETCHES`, `LOGS_DIR`, `FIXTURES_DIR` |
| `src/hubspot_client.py` | Facade over `hubspot-api-client`. Every HubSpot interaction goes through here. | `HubSpotClient(access_token)`, `.extract_list_id` (static), `.get_companies_in_list`, `.update_company`, `.ensure_property_exists` |
| `src/site_fetcher.py` | Pulls a URL via `requests` (static) with a Playwright fallback. Defensive — never raises to the caller. | `SiteFetcher()`, `.fetch`, `.fetch_static`, `.fetch_rendered`; `FetchResult` dataclass |
| `src/detectors/signatures.py` | The signature library. Pure data — no IO, no I/O. | `Signature` dataclass, `SIGNATURES`, `load_signatures()`, `get_signatures_by_category(cat)` |
| `src/detectors/__init__.py` | Shared detection logic — compiles regex patterns once, runs them against a `FetchResult`. | `DetectionHit` dataclass, `_run_detection(category, fetch_result)` |
| `src/detectors/{crm,ad_pixels,martech,salestech}.py` | Thin wrappers — each calls `_run_detection` with its category. | `detect(fetch_result)` |
| `src/orchestrator.py` | Wires HubSpot + fetcher + detectors. Owns the thread pool, run report, summary tables. | `Orchestrator(client, fetcher)`, `.run`, `.run_companies`, `.ensure_property`; `RunReport`; `filter_low_confidence`, `format_signals` |
| `src/cli.py` | `click` entry point. Three subcommands. | `check-list`, `detect-one`, `run` |
| `scripts/run_chunked.py` | Materialize-once, chunked-batch execution with a JSON checkpoint. | — |
| `scripts/run_from_report.py` | Write `technographic_signals` from a saved dry-run JSON. No refetch. | — |
| `scripts/retry_errors.py` | Refetch the rows that errored last time, with a longer timeout. | — |
| `scripts/verify_writes.py` | Read N companies from HubSpot and diff against a report. | — |
| `tests/test_signatures.py` | Detector tests against 4 saved HTML fixtures. | — |
| `tests/conftest.py` | Stub `HUBSPOT_ACCESS_TOKEN` before importing `src.config`; expose `make_fetch_result` fixture. | — |

Eight files in `src/`, four in `scripts/`, two in `tests/`. Roughly
1800 lines of Python total.

---

## 4. The signature library — the brain of the system

**File:** `src/detectors/signatures.py`

### The `Signature` dataclass

```python
@dataclass
class Signature:
    name: str
    category: Category                          # "crm" | "ad_pixel" | "martech" | "salestech"
    confidence: Confidence                       # "high" | "medium" | "low"
    patterns: list[str] = field(default_factory=list)              # regex vs raw HTML body
    script_src_patterns: list[str] = field(default_factory=list)   # regex vs <script src="...">
    dom_patterns: list[str] = field(default_factory=list)          # regex vs raw HTML (markup)
    cookie_patterns: list[str] = field(default_factory=list)       # regex vs cookie names
```

### The four pattern types

A signature can match through any of four channels — only one needs to
fire for the signature to register as a hit:

| Field | Matched against | Typical fingerprint |
|---|---|---|
| `script_src_patterns` | `FetchResult.script_srcs` (URLs from `<script src=...>` and Playwright-observed network requests) | `connect\.facebook\.net/en_US/fbevents\.js` |
| `patterns` | `FetchResult.html` (whole body) | `fbq\(\s*['"]init['"]` — an inline JS call |
| `dom_patterns` | `FetchResult.html` (whole body) — semantically the same as `patterns` but conventionally used for markup-shaped fingerprints | `<form[^>]*action=['"][^'"]*webto\.salesforce\.com` |
| `cookie_patterns` | `FetchResult.cookies` (cookie names only, never values) | `^hubspotutk$` |

**All regexes are compiled once at module import** with
`re.IGNORECASE`. The compiled forms live in `_COMPILED: dict[name, dict]`
in [src/detectors/__init__.py](src/detectors/__init__.py). Do NOT embed
`(?i)` inside pattern strings — it's redundant and would mask the
case-insensitivity invariant.

### Confidence semantics

| Level | Meaning | Used for |
|---|---|---|
| `high` | Unique fingerprint that essentially never collides. | `js.hs-scripts.com` (only HubSpot), `connect.facebook.net/en_US/fbevents.js` (only Meta Pixel). |
| `medium` | Probable but could collide, OR widespread enough that the signal is real but not differentiating. | GA4, GTM, Google Optimize — almost every site has them. |
| `low` | Weak signal — only worth reporting if something else corroborates it. | Outreach iframe references (`outreach.io` often appears on tracked outbound landing pages, not the corporate site). |

`low`-confidence hits are filtered out by
`filter_low_confidence()` in the orchestrator unless the same vendor
name has a `high`/`medium` hit elsewhere in the same result set.

### Same-name signatures across categories

Some vendors legitimately belong to multiple categories — Drift is both
a chat tool (martech) and a sales-acceleration tool (salestech). The
library carries one `Signature` entry per (vendor, category) pair with
identical patterns. Detection then produces one `DetectionHit` per
category, and the formatted output shows the vendor under each bucket:

```
Martech: Drift | Salestech: Drift
```

That's intentional. If you don't want the duplication in some downstream
consumer, dedupe at the consumer layer; don't change the signature
library.

### Current size

38 signature entries as of this writing (was 32 in the initial library,
plus 6 added/fixed during session experience — HubSpot Ad Pixels, Reo,
G2, Factors.ai, AISDR, and an Apollo.io path fix).

### Adding a new signature

Follow [`skills/add-signature/SKILL.md`](skills/add-signature/SKILL.md).
Short version: use `detect-one` to identify the unique fingerprint, add
a `Signature(...)` to the appropriate `_CRM`/`_AD_PIXELS`/`_MARTECH`/
`_SALESTECH` list, and optionally add an HTML fixture under
`tests/fixtures/` with an assertion in `tests/test_signatures.py`.

---

## 5. The fetch path — static plus Playwright fallback

**File:** `src/site_fetcher.py`

### The `FetchResult` dataclass

```python
@dataclass
class FetchResult:
    url: str                                       # final URL after redirects
    status: int = 0
    html: str = ""
    script_srcs: list[str] = field(default_factory=list)
    cookies: list[str] = field(default_factory=list)            # NAMES only — never values
    rendered: bool = False                                       # was Playwright used?
    error: str | None = None
```

Every public entry point returns one of these. **Errors never propagate
to callers** — they're caught, logged, and packed into the `error` field.
That invariant is critical to the "one bad URL must never abort the
run" rule.

### `fetch_static`

A single `GET` through a session that carries:

- A realistic Chrome-on-Mac `User-Agent` (currently Chrome 135).
- `Accept` and `Accept-Language` headers.
- `max_redirects = 5` (raises `TooManyRedirects` if exceeded).
- A 15-second connect/read timeout (from `REQUEST_TIMEOUT_SECONDS`).

Wrapped in `tenacity` retry: up to 3 attempts (1 initial + 2 retries) on
`requests.ConnectionError` and `requests.Timeout` only, with exponential
backoff capped at 2 seconds. 4xx and 5xx are NOT retried at the
`requests` layer — they're returned as the FetchResult `status` and
the orchestrator decides what to do.

Script sources are parsed out of the response body with BeautifulSoup
(`lxml` parser) — every `<script src="...">` value, verbatim, whether
absolute or relative.

### `fetch_rendered`

Triggered as a fallback (see below), or directly when the caller
requests it. Lazy imports `playwright.sync_api` so that users with
`USE_PLAYWRIGHT_FALLBACK=false` don't need Playwright installed at all.

Flow:

1. Launch headless Chromium via `sync_playwright()`.
2. Create a new context with the same Chrome UA.
3. Attach a `request` event listener that captures every URL where
   `request.resource_type == "script"`. This is the magic — it sees
   scripts that the static parser couldn't, because they're loaded by
   other scripts after the initial DOM.
4. `page.goto(url, timeout=15000ms, wait_until="domcontentloaded")`.
5. Best-effort `page.wait_for_load_state("networkidle", timeout=8000ms)`
   — wrapped in a `try` for the inevitable timeout.
6. Read `page.content()`, `context.cookies()`.
7. Close the browser.

The returned `script_srcs` is the union of network-observed scripts AND
`<script src=...>` parsed from the final HTML, deduped (preserving first-
seen order via `dict.fromkeys`).

### The `fetch` orchestrator — static-first with conditional fallback

```python
def fetch(self, url: str) -> FetchResult:
    normalized = _normalize_url(url)               # prepend https://, strip trailing /
    static_result = self.fetch_static(normalized)

    should_fallback = config.USE_PLAYWRIGHT_FALLBACK and (
        static_result.error is not None
        or static_result.status >= 400
        or len(static_result.html.encode("utf-8", "ignore")) < 50_000   # bytes
        or _looks_like_spa_shell(static_result.html)
    )

    if not should_fallback:
        return static_result

    rendered_result = self.fetch_rendered(normalized)
    if len(rendered_result.script_srcs) >= len(static_result.script_srcs):
        return rendered_result
    return static_result
```

The four fallback conditions, in order of how often they fire:

| Condition | What it catches |
|---|---|
| static.status >= 400 | Sites that 403 on requests but render OK in Chromium (Salesforce-style soft bot detection). |
| body < 50,000 bytes | SPAs and thin marketing pages that defer everything to JS. |
| `_looks_like_spa_shell()` | Body with ≤2 non-script children and < 200 chars of text. Common React/Next shells. |
| static had an exception | Network failures, DNS, TLS — Playwright sometimes succeeds where requests' SSL stack fails. |

**Why the "more scripts wins" rule?** If a rendered fallback fails
(returns a 403 with 0 scripts), the static result (which had real
scripts) wins. If rendered succeeds with more, it wins. Ties go to
rendered (more authoritative — JS has actually executed). The "0 ≥ N
is false" arithmetic does the right thing here.

### Defensive behavior, restated

- `fetch_static` catches every exception and returns `FetchResult(url, error=str(exc))`.
- `fetch_rendered` does the same.
- `fetch` catches `ValueError` from URL normalization and returns the
  same.

Net effect: no exception originating in the fetcher can ever reach the
orchestrator's worker loop. The orchestrator still wraps its worker in a
`try/except` for belt-and-suspenders defense.

---

## 6. The detection engine

**File:** `src/detectors/__init__.py` (the shared engine) plus four
thin wrappers `crm.py`, `ad_pixels.py`, `martech.py`, `salestech.py`.

### The `DetectionHit` dataclass

```python
@dataclass
class DetectionHit:
    name: str                       # canonical vendor name from Signature
    category: str
    confidence: str                 # carried over from Signature
    evidence: list[str] = field(default_factory=list)
```

`evidence` is the diagnostic field. Up to 3 strings, each ≤200 chars.
For script-src hits the evidence is the matched URL itself; for body
pattern hits it's a ~40-char snippet centered on the match, with
whitespace collapsed. Useful for `detect-one`'s console output and for
post-hoc auditing of "why did Y detect on X".

### `_run_detection(category, fetch_result)`

The shared entry point. Each per-category module is two lines:

```python
def detect(fetch_result):
    return _run_detection("crm", fetch_result)
```

The work happens in `_detect_one(signature, fetch_result)` which:

1. Looks up the compiled regexes for this signature's name (`_COMPILED[sig.name]`).
2. Walks the four channels in this order — script srcs, body patterns,
   dom patterns, cookies — collecting evidence as it goes.
3. Stops as soon as 3 unique evidence strings have been collected
   (`_EVIDENCE_LIMIT = 3`).
4. Returns a single `DetectionHit` (or `None` if nothing matched).

The order matters for evidence: script srcs are the most actionable
piece of evidence (a URL you can paste back into a browser), so we
collect those first.

### Why static methods get compiled once

`_compile_all()` runs at module import time and produces:

```python
_COMPILED: dict[str, dict[str, list[re.Pattern]]] = {
    "HubSpot": {
        "patterns":              [<compiled regex>, ...],
        "script_src_patterns":   [...],
        "dom_patterns":          [...],
        "cookie_patterns":       [...],
    },
    "Salesforce / Pardot": {...},
    ...
}
```

This dict is the hot path for every fetched page. Re-compiling regexes
per page is wasteful when you're processing thousands. Compilation is
fast in absolute terms (microseconds), but at 38 signatures × ~5 patterns
each × 1700 pages = ~325,000 regex compilations saved per big-list run.

Keyed by name. Same-name entries across categories (Drift, Intercom)
have identical patterns today, so the dict collapses them — they share
one compiled set. If patterns ever diverge between Drift-martech and
Drift-salestech, change the key to `(name, category)` here.

---

## 7. The HubSpot facade

**File:** `src/hubspot_client.py`

This module is the only place that touches `hubspot-api-client`. The
rest of the codebase never imports HubSpot SDK types. That isolation
turned out to be load-bearing — we already had to swap the membership
API method name once during the session (the SDK exposes
`get_page(...)` in the installed version, not the `get_page_order_by_id`
older docs suggest).

### Methods

| Method | What it does |
|---|---|
| `extract_list_id(url_or_id)` (static) | Parses either a raw digit string or a HubSpot UI URL of the form `/objectLists/<id>` or `/lists/<portal>/list/<id>`. Raises `ValueError` if neither shape matches. |
| `get_companies_in_list(list_id)` (generator) | Pages through the v3 list memberships endpoint (250 IDs per page), then batch-reads companies 100 IDs at a time with `name`, `domain`, `website` hydrated. Yields one dict per company. |
| `update_company(company_id, properties)` | PATCH a company. Logs and swallows non-retryable exceptions per row — one bad row never aborts a batch. |
| `ensure_property_exists(object_type, property_name, label, group_name, field_type)` | Idempotently create a custom property. GET first; if 404, create. Anything else propagates. Called once at the top of every real run. |

### Retry policy

Every SDK call is decorated with `_retry`:

```python
_retry = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)
```

Where `_is_retryable(exc)` returns `True` only for 429 or 5xx
(`getattr(exc, "status", None)`). Other errors fail fast.

This handles HubSpot's burst-rate limits (10 req/sec, 19 req/sec
secondly) implicitly — the per-second remaining count is included in
response headers we don't currently parse, but the 429s themselves
trigger exponential backoff. In practice we never hit the limit because
batch reads use 100 IDs per call.

### Pagination

The `get_companies_in_list` loop is:

```
while True:
    page = _fetch_membership_page(list_id, after=after)
    ids = [r.record_id for r in page.results]
    for chunk in chunked(ids, 100):
        for company in _batch_read_companies(chunk):
            yield to_dict(company)
    after = page.paging.next.after  # None when done
    if not after: return
```

Generators throughout, so a caller (the orchestrator) could in principle
stream. We materialize in the orchestrator because the progress bar
needs a known total. For very large lists (>500), the chunked runner
materializes once into a checkpoint file and streams from there.

---

## 8. The orchestrator — concurrency, gates, and the run report

**File:** `src/orchestrator.py`

### Public surface

```python
class Orchestrator:
    def ensure_property(self) -> None
    def run(self, list_id, dry_run=False, limit=None) -> RunReport
    def run_companies(self, companies, dry_run=False, ...) -> RunReport
```

`run()` is the standard entry: ensure property, materialize HubSpot
list, delegate to `run_companies`. `run_companies()` is the lower-level
entry that the chunked runner uses with a pre-materialized list.

### The concurrency model

Two distinct contexts:

```
┌──────────────────────────────────────────────────────────────────┐
│ ThreadPoolExecutor(max_workers=MAX_CONCURRENT_FETCHES)           │
│                                                                  │
│   Worker 1: site_fetcher.fetch(url) → detectors → format         │
│   Worker 2: site_fetcher.fetch(url) → detectors → format         │
│   ...                                                            │
│   Worker N: site_fetcher.fetch(url) → detectors → format         │
└─────────────────────┬────────────────────────────────────────────┘
                      │ as_completed yields results
                      ▼
       ┌──────────────────────────────────┐
       │ Main thread (sequential)         │
       │  - read result                   │
       │  - log per-company line          │
       │  - hubspot.update_company(...)   │
       │  - advance progress bar          │
       │  - append to report.results      │
       └──────────────────────────────────┘
```

Why writes are sequential:

1. HubSpot's rate limit is easier to respect in a single thread.
2. Per-company logging stays in order from the main thread.
3. Threading the writes would save maybe 20% on small lists and
   complicate retry/backoff. Not worth it.

Why fetches are parallel:

1. Most fetch time is network I/O; threads parallelize that well even in
   Python.
2. With 5 workers, a list of 234 companies takes ~77 seconds instead of
   ~6 minutes sequential.

### The per-company budget

```python
outcome = fut.result(timeout=_PER_COMPANY_TIMEOUT_S)   # 60 seconds
```

If a worker doesn't finish in 60 seconds, we count it as a failure and
move on. Python can't actually kill the thread — it keeps running in the
pool until it finishes naturally — but the main thread isn't blocked.
At max_workers=5, a few stuck threads can degrade throughput; in
practice we've never seen this matter because the fetcher's internal
timeouts (15s requests + 8s networkidle, plus retries) keep total fetch
time well under 60s.

### The dry-run gate

`run_companies(companies, dry_run=True, ...)` does everything except
the `hubspot.update_company(...)` call. Same fetch, same detection,
same report writing. The report's `signals_string` for each row reflects
what *would* have been written. The skills layer treats this as the
safety gate — every write skill requires explicit user approval after
a dry-run.

### The run report

```python
@dataclass
class RunReport:
    started_at: str                               # ISO
    finished_at: str = ""
    duration_seconds: float = 0.0
    total_companies: int = 0
    succeeded: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[dict] = field(default_factory=list)
```

Each `result` dict contains:

```python
{
    "company_id": str,
    "name": str | None,
    "domain": str | None,
    "signals_string": str | None,        # "CRM: ... | ..." or "No signals detected" or None for skipped
    "error": str | None,                  # populated for fetch errors and no-URL skips
    "status": "succeeded" | "skipped" | "failed",
}
```

`status` semantics:

- `succeeded` — orchestrator processed the row. May have signals,
  may say "No signals detected", may have a fetch error (in which case
  `error` is set but we still wrote "No signals detected" to HubSpot).
- `skipped` — the company had neither `website` nor `domain` in HubSpot.
  Never touched in HubSpot. Counted separately so the user can see the
  HubSpot-side data-quality problem.
- `failed` — the worker raised an exception, or the per-company timeout
  fired. Counted separately because these are rare and worth flagging.

Reports are written to `logs/run_YYYYMMDD_HHMMSS.json` at the end of
every invocation (dry-run too). This is the authoritative source for
`run-from-report` and `retry-fetch-errors`.

### The console summary

Printed at the end of every run:

1. A counters table (started, finished, duration, total, succeeded,
   skipped, failed).
2. A top-vendors table (parsed back from the `signals_string`s) — top
   10 by hit count.

### The low-confidence filter

```python
def filter_low_confidence(hits):
    strong = {h.name for h in hits if h.confidence in ("high", "medium")}
    return [h for h in hits if h.confidence != "low" or h.name in strong]
```

A `low`-confidence hit survives only if a `high`/`medium` hit with the
same vendor name also exists somewhere in the result set (typically in
a different category). The only `low` signature today is Outreach. If
we ever see Outreach corroborated by, say, an Outreach-CRM signature,
both will be reported; otherwise the Outreach iframe reference gets
dropped.

### The output formatter

```python
def format_signals(hits):
    if not hits:
        return "No signals detected"
    by_cat = defaultdict(set)
    for h in hits:
        by_cat[h.category].add(h.name)
    parts = []
    for key, label in [("crm", "CRM"), ("ad_pixel", "Ad Pixels"),
                       ("martech", "Martech"), ("salestech", "Salestech")]:
        vendors = sorted(by_cat.get(key, set()))
        if vendors:
            parts.append(f"{label}: {', '.join(vendors)}")
    return " | ".join(parts) if parts else "No signals detected"
```

The format is **deterministic given the input**:

- Categories appear in a fixed order: CRM, Ad Pixels, Martech, Salestech.
- Vendors within each category are sorted alphabetically.
- Empty categories are omitted entirely (no `Martech: none`).
- If everything is empty, the literal string `"No signals detected"`.

Determinism matters because users grep HubSpot for these strings.
`"Salesforce / Pardot"` always appears in that exact form, with that
exact slash spacing, in the CRM bucket.

---

## 9. Configuration and secrets

**File:** `src/config.py`

Reads `.env` from the project root via `python-dotenv`. **Validates
`HUBSPOT_ACCESS_TOKEN` at module import time** — anything that imports
`src.config` (which is most of the codebase) will fail loudly if the
token isn't set. This is a deliberate choice: better to fail at
startup than 30 minutes into a run.

The tests' `conftest.py` sets a stub `HUBSPOT_ACCESS_TOKEN` via
`os.environ.setdefault` *before* importing `src.site_fetcher`, so the
test suite doesn't need a real `.env`.

### Variables

| Var | Default | Purpose |
|---|---|---|
| `HUBSPOT_ACCESS_TOKEN` | (required) | HubSpot Private App token. |
| `HUBSPOT_LIST_ID` | (optional) | A default list ID, so `python -m src.hubspot_client` (smoke test) works without args. |
| `LOG_LEVEL` | `INFO` | Standard Python logging level. |
| `REQUEST_TIMEOUT_SECONDS` | `15` | Both `requests.get(timeout=)` and Playwright's `goto` timeout (ms = ×1000). |
| `USE_PLAYWRIGHT_FALLBACK` | `true` | If false, the fetcher never invokes Playwright (Playwright doesn't even need to be installed). |
| `MAX_CONCURRENT_FETCHES` | `5` | Size of the orchestrator's thread pool. |

### Secret-management practice

- `.env` is gitignored. Never committed.
- `.env.example` is committed; it has the variable names with empty
  values.
- A token pasted in chat is considered compromised. The user is
  expected to rotate via HubSpot's Private App UI.
- The repo's `gh repo create … --private` default avoids accidental
  public exposure even if a future commit leaked something.

---

## 10. The CLI surface

**File:** `src/cli.py`, built with `click`.

Three commands:

### `check-list URL_OR_ID`

Read-only. Resolves the list ID, streams memberships, prints a Rich
table of the first 5 records plus a total count. No HubSpot writes.

### `detect-one URL`

Read-only. Fetches one URL, runs all four detectors, prints fetch
metadata, per-vendor evidence, and the formatted string. No HubSpot
calls.

### `run URL_OR_ID [--dry-run] [--limit N]`

The main path. Resolves the list, runs the orchestrator, writes the
report. With `--dry-run`, skips the HubSpot PATCH calls. With `--limit
N`, processes only the first N companies after materialization.

### Shared behavior

- Every command prints a Rich panel/table for human readability.
- Every command exits 0 on success, 1 on input error (e.g., unparseable
  URL).
- All three honor the `.env` config — no CLI flags duplicate env vars.

### How the CLI relates to the skills layer

The skills layer is *higher-level* than the CLI. A skill says "for
this user intent, run this command and report the output this way."
The CLI is the underlying mechanism; the skills are the documented
procedures.

---

## 11. The skills / scripts layer — agent-friendly playbooks

This layer didn't exist in the original build. It was added after
session experience showed that:

1. The same workflows kept recurring (check-list → dry-run → approval →
   write).
2. Some workflows needed coordination beyond a single CLI command
   (chunked runs, retry-fetch-errors).
3. An agent (Claude, or any future LLM) needs predictable behavior:
   when the user says X, the agent should always run Y.

### Skills (`skills/<name>/SKILL.md`)

9 markdown playbooks, each with frontmatter (`name`, `description`,
`argument-hint`) and standardized sections: `When to use`, `When NOT
to use`, `Inputs`, `Procedure`, `Outputs`, `Examples`. The agent
reading these is meant to follow them step-for-step.

Routing rules live in [SKILLS.md](SKILLS.md). The most important ones:

| Trigger | Skill |
|---|---|
| Bare HubSpot list URL | `check-list` → ask via numbered menu |
| Bare single-site URL | `detect-one` |
| List size > 500 | Lead with `run-chunked` |
| User says "approved" after a dry-run | `run-from-report` (NOT a fresh `run`) |

The "approved → `run-from-report`" rule is non-obvious but
load-bearing: it preserves the exact data the user reviewed and avoids
Playwright non-determinism between the dry-run and the real-run.

### Scripts (`scripts/*.py`)

Four executable Python files, each ~50-150 lines, each importing
from `src.*` after a sys.path shim:

| Script | What it does |
|---|---|
| `run_chunked.py` | Materializes the full list to `logs/checkpoints/list_<id>.json`. Processes pending IDs in batches of `--chunk` (default 250). After each batch, marks IDs `done` in the checkpoint atomically. Resumable across kills. |
| `run_from_report.py` | Reads a saved `logs/run_*.json`. For each row with `error is None` and `status == "succeeded"`, calls `hubspot.update_company(company_id, {"technographic_signals": signals_string})`. No refetch. |
| `retry_errors.py` | Reads a saved report, selects rows where `status == "succeeded"` AND `error` is set, batch-reads them fresh from HubSpot (in case `website` changed), refetches with `REQUEST_TIMEOUT_SECONDS=30`, writes successful retries to HubSpot. |
| `verify_writes.py` | Reads a report, samples N rows (or specific names), reads each company's live `technographic_signals` from HubSpot, diffs against the report. |

All four:

- Use the `Orchestrator`, `HubSpotClient`, `SiteFetcher`, and detectors
  directly via their public API. No duplicated logic.
- Accept `--dry-run` (where meaningful) for a safe preview.
- Print Rich-formatted output.
- Are documented by their corresponding SKILL.md file.

### Why scripts and not more CLI subcommands?

Two reasons:

1. **Surface area**. The CLI is for the three core operations.
   Productizing every skill into a CLI command would bloat `src/cli.py`
   and force every operational decision through `click`.
2. **Separation of stable vs evolving**. The CLI is the stable surface
   that `src.*` consumers depend on. Scripts are the evolving
   operational layer where you can prototype, replace, or delete things
   without thinking about the `src.*` contract.

---

## 12. Persistence — what lives on disk

| Path | Format | Lifetime | Producer |
|---|---|---|---|
| `.env` | KEY=VALUE | persistent | manual |
| `logs/run_YYYYMMDD_HHMMSS.json` | JSON | persistent | `Orchestrator._finalize` |
| `logs/checkpoints/list_<id>.json` | JSON | persistent until the run completes (deletable for a fresh start) | `scripts/run_chunked.py` |
| `tests/fixtures/*.html` | HTML | persistent (committed) | manual + Prompt 5 |

### Run-report schema

```json
{
  "started_at": "2026-05-19T14:13:38",
  "finished_at": "2026-05-19T14:20:32",
  "duration_seconds": 414.0,
  "total_companies": 545,
  "succeeded": 541,
  "skipped": 4,
  "failed": 0,
  "results": [
    {
      "company_id": "225635825866",
      "name": "New Relic",
      "domain": "newrelic.com",
      "signals_string": "No signals detected",
      "error": null,
      "status": "succeeded"
    },
    ...
  ]
}
```

### Checkpoint schema

```json
{
  "list_id": "2076",
  "created_at": "2026-05-28T09:47:46",
  "companies": [
    {
      "id": "199126588651",
      "name": "Poppulo",
      "domain": "poppulo.com",
      "website": "poppulo.com",
      "status": "pending"      // or "done"
    },
    ...
  ]
}
```

Checkpoint writes are atomic — the script writes to `*.json.tmp` then
`os.replace`s. So a kill during a checkpoint write can never produce a
half-written checkpoint.

---

## 13. Error handling and recovery taxonomy

### Where failures can originate

1. **Fetcher** — DNS, TLS, HTTP, Playwright. Always packed into the
   `FetchResult.error` field. Never propagated.
2. **Detectors** — should never raise (they iterate compiled regexes).
   The orchestrator's worker still wraps them defensively.
3. **HubSpot writes** — `update_company` catches exceptions, logs
   `update_failed company_id=...`, swallows. The row is recorded as
   `succeeded` (because the orchestrator's worker did succeed) with no
   `error` field set in the result — the failure is in the log line
   only. (Edge case worth knowing about.)
4. **HubSpot reads** — `_fetch_membership_page` and
   `_batch_read_companies` catch failures and log; the generator stops
   yielding gracefully.
5. **HubSpot property bootstrap** — `ensure_property_exists` re-raises
   on any non-404 error. This aborts the run before any company is
   touched. By design.
6. **CLI argument errors** — `extract_list_id` raises `ValueError`,
   caught by the CLI, printed in red, exit 1.

### Categorization of "fetch error" failures

From the session, the realistic breakdown for a 1700-company list:

| Cause | Frequency | Recoverable? |
|---|---|---|
| Playwright `goto` Timeout (15s exceeded) | ~30% of errors | Yes, with `retry-fetch-errors --timeout 30` |
| DNS unresolvable | ~30% | No — dead domain |
| TLS cert error | ~22% | No — cert is broken on their end |
| Connection refused / reset | ~8% | Usually no |
| HTTP/2 protocol error | ~4% | No |
| Other | ~6% | Mixed |

### What gets written to HubSpot for a fetch-error row

By default: `"No signals detected"`. Same as a clean fetch with no
detections. The downstream consumer can't tell the difference from the
property alone — they'd have to consult the run report's `error` field.

Users who care about that distinction can opt into
`run-from-report --skip-errors=true` (the default in that script),
which leaves the live HubSpot value untouched for fetch-error rows.

### What happens on a mid-run kill

Without checkpointing (`cli run` direct invocation):

- Some companies may have had their HubSpot property updated.
- No `logs/run_*.json` was written (that's the last step).
- The state of "which rows landed" is opaque.
- Recovery: re-run the whole list — successful writes get overwritten
  with the same value, no harm.

With checkpointing (`scripts/run_chunked.py`):

- The checkpoint reflects all completed chunks.
- A mid-chunk kill loses at most that one chunk.
- Re-invocation auto-resumes from the first pending ID.
- Per-chunk run reports are written incrementally.

This is why `run-chunked` is the recommended path for lists > 500.

---

## 14. Performance characteristics (observed)

| Operation | Cost |
|---|---|
| `check-list` (5,336 rows) | ~5 seconds |
| Static fetch | 200-1500 ms per URL |
| Playwright fetch | 3-9 seconds per URL |
| Detection + filter + format (per page) | ~1-10 ms |
| HubSpot `update_company` | ~50-100 ms (serial) |
| `dry-run` (234 rows) | 77 s end-to-end |
| `dry-run` (1700 rows) | 927 s end-to-end |
| `run` (5 rows) | ~5 s |
| `run` (1650 rows, write-from-report) | 791 s (~13 min) |
| `run` (1700 rows, full pipeline) | ~16-20 min (estimated) |
| `run-chunked` 250-row chunks | ~2-3 min per chunk |
| `retry-fetch-errors` (~49 rows, 30s timeout) | ~5-10 min |

Bottlenecks at scale:

1. **Sequential HubSpot writes** at ~10 writes/sec become the wall for
   lists > 500. With the burst limit at 19/sec, there's ~2× headroom
   if you wanted to parallelize writes (not currently done).
2. **Playwright launch** is ~1-2 seconds. Each `fetch_rendered` call
   spins up a fresh browser. Long-lived browser contexts would amortize
   this, at the cost of complexity.

Neither is a blocker today. If they become one, the orchestrator is the
right place to address them.

---

## 15. Test coverage and what isn't tested

**File:** `tests/test_signatures.py`

5 tests, all centered on the signature library:

| Test | Asserts |
|---|---|
| `test_hubspot_fixture` | The `site_hubspot_meta_li.html` fixture produces exactly `{HubSpot}` in CRM and `{Meta Pixel, LinkedIn Insight Tag, Google Tag Manager}` in ad_pixel, with no martech/salestech detections. |
| `test_salesforce_fixture` | `{Salesforce / Pardot, Marketo}` CRM, `{Drift}` martech, `{Drift}` salestech. |
| `test_segment_fixture` | `{Segment, Mixpanel, Intercom}` martech, `{Intercom, Calendly}` salestech. |
| `test_minimal_fixture` | Empty in every category. |
| `test_no_false_positives_on_minimal` | Across all four detectors, no hits on the minimal fixture. |

What's NOT tested:

- The site fetcher (would need live HTTP or extensive mocking).
- The HubSpot client (would need a live token or `responses`-style mocks).
- The orchestrator's concurrency model (deterministic enough that
  manual testing has been sufficient).
- The chunked runner (smoke-tested during this session, not regression-
  tested).
- The CLI surface (smoke-tested via `--help`).

The signature tests are the right place to grow coverage. When you add
a new signature, add a fixture and an assertion. The other layers are
better validated by `detect-one` against real sites.

---

## 16. Known limitations and design trade-offs

| Limitation | Why |
|---|---|
| **Headless Chromium 403s** on Salesforce, UBS, etc. | Anti-bot defenses. Bypassing would require stealth libraries, fingerprint randomization, possibly proxies — all of which add complexity and break tests. |
| **Playwright non-determinism** between dry-run and real-run. | `wait_for_load_state("networkidle")` is a real-time race. We mitigate this for the common case by recommending `run-from-report` after a dry-run — that writes exactly what the user reviewed. |
| **No retry on individual HubSpot writes within a run.** | `update_company` swallows errors. A 429 mid-batch is retried by tenacity inside the SDK call, but a 500 that exhausts retries silently logs and moves on. Could be tracked in the report's `error` field — currently isn't. |
| **`tests/fixtures/*.html` is gitignored** but committed selectively with `git add -f`. | The original intent was "don't accumulate hundreds of fixtures in git." The downside is that the test suite's required fixtures need explicit force-add — easy to miss. |
| **`HUBSPOT_ACCESS_TOKEN` is required at import time** in `src.config`. | Tests need a stub set via `conftest.py` before any `src.*` import. Friction, but the loud-failure-at-startup trade-off is worth it. |
| **No CLI offset flag.** | The chunked runner achieves the same outcome with checkpoint resumability. Adding `--offset` to `cli run` would create two ways to do the same thing. |
| **Sequential HubSpot writes.** | At 1700 rows / 13 min, the wall is ~10 writes/sec. We could parallelize for ~2× throughput but rate-limit handling gets messy. Not worth it until someone has a list of 50k. |
| **No write retry after a fetch error.** | The default is "write `No signals detected` once". `retry-fetch-errors` is a separate, explicit pass. |
| **Cookie names only, never values.** | Privacy/safety. Cookie names are signal enough (`hubspotutk` is unique to HubSpot). Values would be PII for tracking IDs. |
| **No detection of `<noscript>` fallbacks.** | We parse `<script src=...>` and the body text. `<noscript><img src=facebook.com/tr?id=...>` is caught by the body-text dom pattern. Other noscript shapes aren't specifically handled. |

---

## 17. Extension points — how to safely change things

### Adding a vendor signature

→ [`skills/add-signature/SKILL.md`](skills/add-signature/SKILL.md).
The signature library is designed to be extended; the rest of the
pipeline is signature-agnostic. New entries take effect on the next
detection.

### Adding a new pattern type

Hypothetical example: matching DNS CNAME records. The `Signature`
dataclass would gain a new field; `_compile_all` would compile it;
`_detect_one` would add a new channel to the search order. Two files
to touch: `signatures.py` and `detectors/__init__.py`. Tests would
need new fixtures.

### Adding a new HubSpot property

The orchestrator writes one property name (`technographic_signals`)
defined as `_PROPERTY_NAME` in `orchestrator.py`. Adding a second
property (e.g., `technographic_signals_high_confidence`) is a
multi-line change to `_handle_result` and a new `ensure_property`
call. The HubSpot client is general enough that it'd take this in
stride.

### Replacing the LLM-free signature matching with an LLM call

This is a meaningful design pivot, not an extension. Today the system
is deterministic and fully offline-explainable. An LLM-augmented version
would lose those properties. The right place to add LLM is at the
*evidence-to-narrative* layer — e.g., a script that takes a saved
report and produces a one-paragraph summary per company. Not in the
detection path.

### Adding a CLI command

→ Add a `@cli.command(...)` decorator in `src/cli.py`. Use the
existing three as templates. For complex multi-step operations, prefer
the scripts/ layer.

### Adding a skill

→ Write `skills/<name>/SKILL.md` following the existing format.
Reference any new script under `scripts/`. Add a row to the routing
table in [SKILLS.md](SKILLS.md). The skill is "live" the moment an
agent reads SKILLS.md.

### Replacing the fetcher

The fetcher's public contract is the `FetchResult` dataclass. Any
implementation that returns `FetchResult` objects with the same field
semantics is a drop-in replacement. The detectors don't know about
`requests` or `playwright`.

### Replacing the HubSpot client

`HubSpotClient` is the only file with HubSpot SDK imports. Replacing
with a different CRM (Salesforce, Pipedrive) means rewriting that one
file and renaming the property in `_PROPERTY_NAME`. The rest of the
codebase is CRM-agnostic in everything but variable naming.

---

## Closing notes

The project's center of mass is the signature library plus the
formatting contract. Everything else is plumbing chosen for the
specific shape of "HubSpot → web → property write." Swap the plumbing
freely; preserve the contract.

For changes that span multiple layers (e.g., "add a new pattern type"),
follow the existing conventions: defensive at boundaries, fail fast at
config, predictable at output. The single most important property of
the system is determinism — given the same input HTML, the same string
goes to HubSpot every time. Don't compromise that without a very good
reason.
