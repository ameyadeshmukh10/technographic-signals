"""Lint all signature JSON files against the schema.

Two tiers walked:

  * Curated — one file per vendor under ``signatures/dns/<vendor_id>.json``
    and ``signatures/web/<vendor_id>.json``. Filename must match vendor_id;
    vendor_id must be present in ``signatures/vendors.json``; paid/enterprise
    indicators must explain themselves in ``notes``.

  * Master — sharded files under ``signatures/master/{dns/all.json,web/<letter>.json}``
    keyed by vendor_id. Each key must exist in ``signatures/master/vendors.json``;
    regex patterns must compile.

Exit code 0 when clean, 1 when any error is found.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from technographics.schema import (
    MatchType,
    dns_signature_from_dict,
    web_signature_from_dict,
)

ROOT = Path(__file__).resolve().parents[1]
SIG = ROOT / "signatures"


def _iter_patterns(sig) -> list:
    pats = []
    for fld in vars(sig).values():
        if isinstance(fld, list):
            pats.extend(p for p in fld if hasattr(p, "match_type"))
        elif isinstance(fld, dict):
            for v in fld.values():
                if isinstance(v, list):
                    pats.extend(p for p in v if hasattr(p, "match_type"))
    return pats


def _validate_signature(sig, label: str, errors: list[str]) -> None:
    for pat in _iter_patterns(sig):
        if pat.match_type is MatchType.REGEX:
            try:
                re.compile(pat.value)
            except re.error as exc:
                errors.append(f"{label}: bad regex '{pat.value}': {exc}")
    for pat in (*getattr(sig, "paid_indicators", []), *getattr(sig, "enterprise_indicators", [])):
        if not pat.notes.strip():
            errors.append(f"{label}: indicator '{pat.value}' missing notes")


def _validate_curated(errors: list[str], warnings: list[str]) -> None:
    vendors_path = SIG / "vendors.json"
    known = set(json.loads(vendors_path.read_text())) if vendors_path.exists() else set()

    for kind, parser in (("dns", dns_signature_from_dict), ("web", web_signature_from_dict)):
        d = SIG / kind
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.json")):
            stem = path.stem
            try:
                data = json.loads(path.read_text())
            except json.JSONDecodeError as exc:
                errors.append(f"{path.name}: invalid JSON: {exc}")
                continue
            try:
                sig = parser(data)
            except (KeyError, ValueError) as exc:
                errors.append(f"{path.name}: schema error: {exc}")
                continue

            if sig.vendor_id != stem:
                errors.append(f"{path.name}: vendor_id '{sig.vendor_id}' != filename '{stem}'")
            if known and sig.vendor_id not in known:
                errors.append(f"{path.name}: vendor_id '{sig.vendor_id}' not in vendors.json")

            _validate_signature(sig, path.name, errors)

            if not _iter_patterns(sig) and "_notes" not in data:
                warnings.append(f"{path.name}: no patterns and no '_notes' explanation")


def _validate_master(errors: list[str], warnings: list[str]) -> None:
    master = SIG / "master"
    if not master.is_dir():
        return

    vendors_path = master / "vendors.json"
    if not vendors_path.is_file():
        errors.append("master/vendors.json: missing")
        return
    known = set(json.loads(vendors_path.read_text()))

    for kind, parser, shards in (
        ("dns", dns_signature_from_dict, [master / "dns" / "all.json"]),
        ("web", web_signature_from_dict, sorted((master / "web").glob("*.json"))),
    ):
        for shard in shards:
            if not shard.is_file():
                continue
            rel = shard.relative_to(SIG)
            try:
                shard_data = json.loads(shard.read_text())
            except json.JSONDecodeError as exc:
                errors.append(f"{rel}: invalid JSON: {exc}")
                continue
            if not isinstance(shard_data, dict):
                errors.append(f"{rel}: expected top-level object")
                continue
            for vendor_id, entry in shard_data.items():
                entry.setdefault("vendor_id", vendor_id)
                if entry["vendor_id"] != vendor_id:
                    errors.append(f"{rel}: key '{vendor_id}' != vendor_id '{entry['vendor_id']}'")
                    continue
                if vendor_id not in known:
                    errors.append(f"{rel}: vendor_id '{vendor_id}' not in master/vendors.json")
                    continue
                try:
                    sig = parser(entry)
                except (KeyError, ValueError) as exc:
                    errors.append(f"{rel}::{vendor_id}: schema error: {exc}")
                    continue
                _validate_signature(sig, f"{rel}::{vendor_id}", errors)


def run() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    _validate_curated(errors, warnings)
    _validate_master(errors, warnings)

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors[:50]:
        print(f"ERROR {e}")
    if len(errors) > 50:
        print(f"... and {len(errors) - 50} more errors")

    if errors:
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
        return 1
    print(f"OK: all signature files valid ({len(warnings)} warning(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
