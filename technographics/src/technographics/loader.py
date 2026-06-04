"""Load signature files from disk into typed objects.

On-disk layout::

    signatures/
      vendors.json                 # curated: {vendor_id: {...metadata...}}
      categories.json              # curated: {category_id: {name, description}}
      dns/<vendor_id>.json         # one curated DNSSignature per file
      web/<vendor_id>.json         # one curated WebSignature per file
      master/                      # imported from enthec/webappanalyzer
        _meta.json                 # {source, upstream_commit, ...}
        categories.json            # upstream taxonomy (108 cats)
        vendors.json               # {vendor_id: {...metadata...}}, ~7,500 entries
        dns/all.json               # {vendor_id: DNSSignature dict}, ~80 entries
        web/<letter>.json          # 27 sharded files, {vendor_id: WebSignature dict}

The loader reads both tiers when both exist, and **curated overrides master**
for any shared ``vendor_id``: the curated dict wins as a whole (not merged at
the pattern level), so hand-tuned ``paid_indicators`` always survive.

An optional ``selection`` set filters the library down to a chosen subset of
``vendor_id``s — the seam the future onboarding agent will plug into.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from technographics.schema import (
    DNSSignature,
    Vendor,
    WebSignature,
    dns_signature_from_dict,
    vendor_from_dict,
    web_signature_from_dict,
)


def default_signatures_dir() -> Path:
    """Locate the bundled ``signatures/`` directory.

    Resolves relative to this file: ``src/technographics/loader.py`` →
    ``<project>/signatures``. Falls back to a ``signatures`` dir in the cwd.
    """
    here = Path(__file__).resolve()
    candidate = here.parents[2] / "signatures"
    if candidate.is_dir():
        return candidate
    return Path.cwd() / "signatures"


@dataclass
class SignatureLibrary:
    vendors: dict[str, Vendor] = field(default_factory=dict)
    categories: dict[str, dict] = field(default_factory=dict)
    dns_signatures: dict[str, DNSSignature] = field(default_factory=dict)
    web_signatures: dict[str, WebSignature] = field(default_factory=dict)
    # vendor_id -> "curated" | "wappalyzer" — useful for the onboarding agent
    # to surface provenance without inspecting each Vendor's `source` field.
    sources: dict[str, str] = field(default_factory=dict)

    def vendor_name(self, vendor_id: str) -> str:
        vendor = self.vendors.get(vendor_id)
        return vendor.vendor_name if vendor else vendor_id

    def category(self, vendor_id: str) -> str:
        vendor = self.vendors.get(vendor_id)
        return vendor.category if vendor else ""

    def source(self, vendor_id: str) -> str:
        return self.sources.get(vendor_id, "unknown")

    def stats(self) -> dict:
        dns_ids = set(self.dns_signatures)
        web_ids = set(self.web_signatures)
        by_category: dict[str, int] = {}
        for vendor in self.vendors.values():
            by_category[vendor.category] = by_category.get(vendor.category, 0) + 1
        return {
            "total_vendors": len(self.vendors),
            "curated": sum(1 for s in self.sources.values() if s == "curated"),
            "master": sum(1 for s in self.sources.values() if s == "wappalyzer"),
            "with_dns": len(dns_ids),
            "with_web": len(web_ids),
            "with_both": len(dns_ids & web_ids),
            "by_category": by_category,
        }


def _read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _load_master(base: Path, library: SignatureLibrary) -> None:
    """Load the master tier (Wappalyzer import) into the library.

    Sharded layout: ``master/web/<letter>.json`` is ``{vendor_id: WebSignature
    dict}``; same for ``master/dns/all.json``.
    """
    master = base / "master"
    if not master.is_dir():
        return

    vendors_file = master / "vendors.json"
    if vendors_file.is_file():
        for vendor_id, data in _read_json(vendors_file).items():
            data.setdefault("vendor_id", vendor_id)
            data.setdefault("source", "wappalyzer")
            library.vendors[vendor_id] = vendor_from_dict(data)
            library.sources[vendor_id] = "wappalyzer"

    dns_file = master / "dns" / "all.json"
    if dns_file.is_file():
        for vendor_id, data in _read_json(dns_file).items():
            data.setdefault("vendor_id", vendor_id)
            library.dns_signatures[vendor_id] = dns_signature_from_dict(data)

    web_dir = master / "web"
    if web_dir.is_dir():
        for shard_path in sorted(web_dir.glob("*.json")):
            for vendor_id, data in _read_json(shard_path).items():
                data.setdefault("vendor_id", vendor_id)
                library.web_signatures[vendor_id] = web_signature_from_dict(data)


def _load_curated(base: Path, library: SignatureLibrary) -> None:
    """Load the curated tier. Curated entries overwrite master entries with
    the same ``vendor_id`` — the whole signature wins, not a per-pattern merge."""
    vendors_file = base / "vendors.json"
    if vendors_file.is_file():
        for vendor_id, data in _read_json(vendors_file).items():
            data.setdefault("vendor_id", vendor_id)
            data.setdefault("source", "curated")
            library.vendors[vendor_id] = vendor_from_dict(data)
            library.sources[vendor_id] = "curated"

    categories_file = base / "categories.json"
    if categories_file.is_file():
        library.categories = _read_json(categories_file)

    dns_dir = base / "dns"
    if dns_dir.is_dir():
        for path in sorted(dns_dir.glob("*.json")):
            sig = dns_signature_from_dict(_read_json(path))
            library.dns_signatures[sig.vendor_id] = sig

    web_dir = base / "web"
    if web_dir.is_dir():
        for path in sorted(web_dir.glob("*.json")):
            sig = web_signature_from_dict(_read_json(path))
            library.web_signatures[sig.vendor_id] = sig


def _filter(library: SignatureLibrary, selection: set[str]) -> None:
    library.vendors = {k: v for k, v in library.vendors.items() if k in selection}
    library.dns_signatures = {k: v for k, v in library.dns_signatures.items() if k in selection}
    library.web_signatures = {k: v for k, v in library.web_signatures.items() if k in selection}
    library.sources = {k: v for k, v in library.sources.items() if k in selection}


def load_selection(selection_path: str | Path) -> set[str]:
    """Read a ``selection.json`` file: ``{"selected": ["intercom", ...]}``."""
    data = _read_json(Path(selection_path))
    return set(data.get("selected", []))


def load_library(
    signatures_dir: str | Path | None = None,
    include_master: bool = True,
    selection: Iterable[str] | None = None,
) -> SignatureLibrary:
    """Load the signature library.

    Args:
        signatures_dir: path to the ``signatures/`` directory. Auto-detected by default.
        include_master: when False, skip the ``master/`` tier (curated-only).
        selection: optional iterable of ``vendor_id``s to restrict the result to.
            A future onboarding agent will populate this from ``selection.json``.
    """
    base = Path(signatures_dir) if signatures_dir else default_signatures_dir()
    if not base.is_dir():
        raise FileNotFoundError(f"signatures directory not found: {base}")

    library = SignatureLibrary()

    # Order matters: master first, curated second, so curated overrides.
    if include_master:
        _load_master(base, library)
    _load_curated(base, library)

    if selection is not None:
        _filter(library, set(selection))

    return library
