"""Slug machinery for the master Wappalyzer importer.

Goals:
  1. Convert an upstream display name (``"Microsoft 365"``) into a stable
     ``vendor_id`` (``"microsoft_365"``).
  2. Reuse the existing curated ``vendor_id`` whenever upstream names a vendor
     we've already hand-authored — so the loader's curated-override logic
     fires on the same key.
  3. Detect collisions across the 7,518 upstream entries deterministically.
"""

from __future__ import annotations

import hashlib
import re

# Upstream display name -> curated vendor_id. Add an entry whenever an
# upstream technology name doesn't naturally slugify to one of our curated
# vendor_ids. Keep this list small: only collisions / non-obvious renames.
CURATED_OVERRIDES: dict[str, str] = {
    "Microsoft 365": "microsoft_365",
    "Office 365": "microsoft_365",
    "Customer.io": "customer_io",
    "Apollo.io": "apollo",
    "Apollo": "apollo",
    "FullStory": "fullstory",
    "Fullstory": "fullstory",
    "Google Workspace": "google_workspace",
    "Google Analytics": "google_analytics",
    "Adobe Marketo Engage": "marketo",
    "Twilio Segment": "segment",
    "Front Chat": "front",
    "SalesLoft": "salesloft",
    "Zendesk Chat": "zendesk",
}

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Lowercase, replace non-alphanumeric runs with ``_``, strip edges."""
    s = _NON_ALNUM.sub("_", name.lower()).strip("_")
    return s or "unknown"


def vendor_id_for(name: str) -> str:
    """Resolve an upstream Wappalyzer name to its canonical ``vendor_id``."""
    if name in CURATED_OVERRIDES:
        return CURATED_OVERRIDES[name]
    return slugify(name)


def assign_unique(names: list[str]) -> dict[str, str]:
    """Return a name -> vendor_id map with deterministic collision suffixes.

    When two distinct upstream names slugify to the same id, the SECOND one
    (in sort order) gets a short hash suffix. First-come keeps the bare slug
    so the override table stays predictable.
    """
    result: dict[str, str] = {}
    taken: set[str] = set()
    for name in sorted(names):
        base = vendor_id_for(name)
        if base not in taken:
            result[name] = base
            taken.add(base)
            continue
        suffix = hashlib.sha1(name.encode("utf-8")).hexdigest()[:6]
        candidate = f"{base}__{suffix}"
        result[name] = candidate
        taken.add(candidate)
    return result
