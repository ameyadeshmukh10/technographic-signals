"""Environment loading and typed configuration constants."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(dotenv_path=ENV_PATH)


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


HUBSPOT_ACCESS_TOKEN: str = _require("HUBSPOT_ACCESS_TOKEN")
HUBSPOT_LIST_ID: str | None = os.getenv("HUBSPOT_LIST_ID") or None

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
REQUEST_TIMEOUT_SECONDS: int = _int("REQUEST_TIMEOUT_SECONDS", 15)
USE_PLAYWRIGHT_FALLBACK: bool = _bool("USE_PLAYWRIGHT_FALLBACK", True)
MAX_CONCURRENT_FETCHES: int = _int("MAX_CONCURRENT_FETCHES", 5)

LOGS_DIR: Path = PROJECT_ROOT / "logs"
FIXTURES_DIR: Path = PROJECT_ROOT / "tests" / "fixtures"
