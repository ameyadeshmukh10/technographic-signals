"""Dual-pipeline technographic vendor detection (DNS + JS/Web)."""

from __future__ import annotations

from technographics.schema import (
    Detection,
    DNSSignature,
    DomPattern,
    MatchType,
    Pattern,
    SignalStrength,
    Vendor,
    WebSignature,
)

__all__ = [
    "Detection",
    "DNSSignature",
    "DomPattern",
    "MatchType",
    "Pattern",
    "SignalStrength",
    "Vendor",
    "WebSignature",
]

__version__ = "0.1.0"
