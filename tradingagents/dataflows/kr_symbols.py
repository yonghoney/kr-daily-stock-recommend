"""Korean equity ticker normalization (KRX → Yahoo Finance).

Yahoo uses exchange suffixes:
  - KOSPI:   ``005930.KS``
  - KOSDAQ:  ``035720.KQ``

Users often type bare 6-digit codes (``005930``). This module maps those to
Yahoo symbols using an explicit KOSDAQ set plus optional universe overrides.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_BARE_CODE = re.compile(r"^\d{6}$")

# Common KOSDAQ names; extend via config/kr_universe.yaml ``kosdaq`` list.
_DEFAULT_KOSDAQ = frozenset(
    {
        "247540",  # EcoPro BM
        "086520",  # EcoPro
        "196170",  # Alteogen
        "068760",  # Celltrion Pharm
        "403870",  # HPSP
        "277810",  # Rainbow Robotics
        "141080",  # LegoChem
        "145020",  # Hugel
        "039030",  # Eo Technics
        "214450",  # PharmaResearch
        "293490",  # Kakao Games
        "357780",  # Soulbrain
        "095340",  # ISC
        "240810",  # Wonik IPS
        "058470",  # LEENO
        "067160",  # AfreecaTV / SOOP
        "112040",  # Wemade
        "263750",  # Pearl Abyss
        "041510",  # SM Entertainment
        "035900",  # JYP Entertainment
        "122870",  # YG Plus
        "253450",  # Studio Dragon
        "036570",  # NCsoft (KOSPI actually - remove)
    }
)

# NCsoft is KOSPI — keep default kosdaq clean
_DEFAULT_KOSDAQ = frozenset(c for c in _DEFAULT_KOSDAQ if c != "036570")


@lru_cache(maxsize=1)
def _load_universe() -> dict:
    """Load optional ``config/kr_universe.yaml`` from the project root."""
    root = Path(__file__).resolve().parents[2]
    path = root / "config" / "kr_universe.yaml"
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        logger.warning("Could not load kr_universe.yaml: %s", exc)
        return {}


def kosdaq_codes() -> frozenset[str]:
    universe = _load_universe()
    extra = {str(c).zfill(6) for c in universe.get("kosdaq", []) or []}
    return frozenset(_DEFAULT_KOSDAQ | extra)


def company_name_for(code: str) -> str | None:
    """Return display name from universe watchlist if present."""
    universe = _load_universe()
    raw = str(code).strip().upper()
    base = raw.split(".")[0]
    if base.isdigit():
        base = base.zfill(6)
    for item in universe.get("watchlist", []) or []:
        if not isinstance(item, dict):
            continue
        item_code = str(item.get("code", "")).strip()
        if item_code.isdigit() and item_code.zfill(6) == base:
            return item.get("name")
        ticker = str(item.get("ticker", "")).strip().upper()
        if ticker in {raw, f"{base}.KS", f"{base}.KQ", base}:
            return item.get("name")
    return None


def normalize_kr_symbol(raw: str) -> str:
    """Map a Korean bare code or mixed ticker to Yahoo ``.KS`` / ``.KQ``.

    Already-suffixed symbols (``.KS``, ``.KQ``, ``.KS.`` typos stripped) are
    returned upper-cased. Non-Korean symbols are returned unchanged.
    """
    if not isinstance(raw, str) or not raw.strip():
        return raw

    s = raw.strip().upper()
    # Already Yahoo KR
    if s.endswith(".KS") or s.endswith(".KQ"):
        return s

    # Strip accidental trailing dots
    s = s.rstrip(".")

    if _BARE_CODE.match(s):
        suffix = ".KQ" if s in kosdaq_codes() else ".KS"
        canonical = f"{s}{suffix}"
        logger.info("Resolved KR symbol %r to Yahoo symbol %r", raw, canonical)
        return canonical

    return s


def is_kr_equity(symbol: str) -> bool:
    if not isinstance(symbol, str):
        return False
    u = symbol.strip().upper()
    return u.endswith(".KS") or u.endswith(".KQ") or bool(_BARE_CODE.match(u))


def kr_base_code(symbol: str) -> str | None:
    """Return the 6-digit KRX code, or None if not a KR equity symbol."""
    if not isinstance(symbol, str):
        return None
    u = symbol.strip().upper()
    if u.endswith(".KS") or u.endswith(".KQ"):
        base = u.rsplit(".", 1)[0]
        return base if _BARE_CODE.match(base) else None
    if _BARE_CODE.match(u):
        return u
    return None
