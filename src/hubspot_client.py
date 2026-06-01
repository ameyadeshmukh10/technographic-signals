"""HubSpot client wrapper.

Thin facade over `hubspot-api-client` so the rest of the codebase never
imports HubSpot SDK types directly. Handles:

- Parsing list IDs out of HubSpot UI URLs.
- Streaming company records from a v3 list (paginated memberships +
  batched property reads).
- Idempotent custom property creation, so the `technographic_signals`
  field is created on first run if it doesn't already exist.
- Updating a single company's properties.

Retries are applied to every SDK call: 429 (rate-limit) and 5xx errors
back off exponentially via tenacity. Non-retryable errors are logged
with the offending company ID and swallowed — one bad row never aborts
the batch.
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Iterator

from rich.logging import RichHandler
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from hubspot import HubSpot
from hubspot.crm.companies import (
    BatchReadInputSimplePublicObjectId,
    SimplePublicObjectInput,
)
from hubspot.crm.properties import PropertyCreate

from . import config


_logger = logging.getLogger("technographic.hubspot")
if not _logger.handlers:
    _logger.addHandler(RichHandler(show_path=False, rich_tracebacks=False, markup=False))
    _logger.setLevel(config.LOG_LEVEL)
    _logger.propagate = False


_BATCH_READ_CHUNK = 100
_MEMBERSHIPS_PAGE_SIZE = 250
_COMPANY_PROPERTIES = ["name", "domain", "website"]


def _is_retryable(exc: BaseException) -> bool:
    """Tenacity predicate: retry on 429 (rate-limit) or 5xx HubSpot
    responses. Every HubSpot SDK exception carries a `.status` int, so a
    duck-typed check works regardless of which sub-package raised it."""
    status = getattr(exc, "status", None)
    if status == 429:
        return True
    if isinstance(status, int) and 500 <= status < 600:
        return True
    return False


_retry = retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)


class HubSpotClient:
    """Facade for the slice of HubSpot we actually use."""

    def __init__(self, access_token: str) -> None:
        self._client = HubSpot(access_token=access_token)

    @staticmethod
    def extract_list_id(url_or_id: str) -> str:
        """Parse a numeric list ID out of either a raw ID or a HubSpot
        list URL. Recognized URL shapes:

        - `https://app.hubspot.com/contacts/<portal>/objectLists/<id>/...`
        - `https://app.hubspot.com/lists/<portal>/list/<id>`

        Raises `ValueError` if the input is neither a digit string nor a
        URL we can match.
        """
        s = (url_or_id or "").strip()
        if not s:
            raise ValueError("empty list identifier")
        if s.isdigit():
            return s
        m = re.search(r"/objectLists/(\d+)", s)
        if m:
            return m.group(1)
        m = re.search(r"/lists/\d+/list/(\d+)", s)
        if m:
            return m.group(1)
        raise ValueError(f"could not extract list ID from: {url_or_id!r}")

    def get_companies_in_list(self, list_id: str) -> Iterator[dict]:
        """Yield companies from a v3 list as dicts with `id`, `name`,
        `domain`, `website`. Pages through every membership; never
        truncates. A failure mid-stream logs and stops gracefully so the
        caller's loop terminates cleanly."""
        after: str | None = None
        while True:
            try:
                page = self._fetch_membership_page(list_id, after=after)
            except Exception as exc:
                _logger.error(
                    "membership_page_failed list_id=%s after=%s error=%s",
                    list_id, after, exc,
                )
                return

            results = getattr(page, "results", None) or []
            ids = [getattr(r, "record_id", None) for r in results]
            ids = [i for i in ids if i is not None]

            for chunk_start in range(0, len(ids), _BATCH_READ_CHUNK):
                chunk = ids[chunk_start:chunk_start + _BATCH_READ_CHUNK]
                try:
                    companies = self._batch_read_companies(chunk)
                except Exception as exc:
                    _logger.error(
                        "batch_read_failed first_ids=%s error=%s",
                        chunk[:5], exc,
                    )
                    continue
                for c in companies:
                    props = getattr(c, "properties", None) or {}
                    yield {
                        "id": getattr(c, "id", None),
                        "name": props.get("name"),
                        "domain": props.get("domain"),
                        "website": props.get("website"),
                    }

            paging = getattr(page, "paging", None)
            next_page = getattr(paging, "next", None) if paging else None
            after = getattr(next_page, "after", None) if next_page else None
            if not after:
                return

    @_retry
    def _fetch_membership_page(self, list_id: str, after: str | None):
        kwargs: dict = {"list_id": list_id, "limit": _MEMBERSHIPS_PAGE_SIZE}
        if after is not None:
            kwargs["after"] = after
        return self._client.crm.lists.memberships_api.get_page(**kwargs)

    @_retry
    def _batch_read_companies(self, ids: list[str]) -> list:
        body = BatchReadInputSimplePublicObjectId(
            inputs=[{"id": i} for i in ids],
            properties=_COMPANY_PROPERTIES,
            properties_with_history=[],
        )
        resp = self._client.crm.companies.batch_api.read(
            batch_read_input_simple_public_object_id=body,
        )
        return getattr(resp, "results", None) or []

    def update_company(self, company_id: str, properties: dict) -> None:
        """Patch a single company. Logs and swallows non-retryable
        errors so one bad row can't stop a batch run."""
        try:
            self._update(company_id, properties)
        except Exception as exc:
            _logger.error(
                "update_failed company_id=%s error=%s",
                company_id, exc,
            )

    @_retry
    def _update(self, company_id: str, properties: dict) -> None:
        body = SimplePublicObjectInput(properties=properties)
        self._client.crm.companies.basic_api.update(
            company_id=company_id,
            simple_public_object_input=body,
        )

    def ensure_property_exists(
        self,
        object_type: str,
        property_name: str,
        label: str,
        group_name: str = "companyinformation",
        field_type: str = "textarea",
    ) -> None:
        """Idempotently create a custom property on the given object
        type. No-op if the property already exists. Re-raises on any
        non-404 lookup or creation failure — this is bootstrap, not a
        per-row operation, so the caller should know if it broke."""
        if self._property_exists(object_type, property_name):
            _logger.info(
                "property_exists object=%s name=%s",
                object_type, property_name,
            )
            return
        try:
            self._create_property(
                object_type=object_type,
                property_name=property_name,
                label=label,
                group_name=group_name,
                field_type=field_type,
            )
        except Exception as exc:
            _logger.error(
                "property_create_failed object=%s name=%s error=%s",
                object_type, property_name, exc,
            )
            raise
        _logger.info(
            "property_created object=%s name=%s",
            object_type, property_name,
        )

    def _property_exists(self, object_type: str, property_name: str) -> bool:
        try:
            self._get_property(object_type, property_name)
            return True
        except Exception as exc:
            if getattr(exc, "status", None) == 404:
                return False
            _logger.error(
                "property_lookup_failed object=%s name=%s error=%s",
                object_type, property_name, exc,
            )
            raise

    @_retry
    def _get_property(self, object_type: str, property_name: str):
        return self._client.crm.properties.core_api.get_by_name(
            object_type=object_type,
            property_name=property_name,
        )

    @_retry
    def _create_property(
        self,
        object_type: str,
        property_name: str,
        label: str,
        group_name: str,
        field_type: str,
    ) -> None:
        body = PropertyCreate(
            name=property_name,
            label=label,
            type="string",
            field_type=field_type,
            group_name=group_name,
            description="Detected go-to-market technologies on the company's website.",
        )
        self._client.crm.properties.core_api.create(
            object_type=object_type,
            property_create=body,
        )


def _main() -> None:
    from rich.console import Console

    console = Console()

    raw_list = config.HUBSPOT_LIST_ID
    if not raw_list:
        console.print("[red]HUBSPOT_LIST_ID is not set in .env[/red]")
        sys.exit(1)

    try:
        list_id = HubSpotClient.extract_list_id(raw_list)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        sys.exit(1)

    console.print(f"[bold]List ID:[/bold] {list_id}")
    console.print("[dim]Streaming companies (read-only — no updates)…[/dim]")

    client = HubSpotClient(config.HUBSPOT_ACCESS_TOKEN)
    count = 0
    first_three: list[dict] = []
    for company in client.get_companies_in_list(list_id):
        count += 1
        if len(first_three) < 3:
            first_three.append(company)

    console.print(f"[bold]Total companies in list:[/bold] {count}")
    if first_three:
        console.print("[bold]First 3:[/bold]")
        for c in first_three:
            console.print(
                f"  • id={c.get('id')}  "
                f"name={c.get('name') or '(unnamed)'!r}  "
                f"domain={c.get('domain') or '-'}  "
                f"website={c.get('website') or '-'}"
            )


if __name__ == "__main__":
    _main()
