"""Korean stock fundamentals (PER/PBR/market value) via Naver mobile API."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

_URL = "https://m.stock.naver.com/api/stock/{code}/integration"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://m.stock.naver.com/",
}


@dataclass
class FundamentalSnapshot:
    per: float | None = None
    pbr: float | None = None
    eps: float | None = None
    bps: float | None = None
    market_cap_krw: float | None = None
    market_cap_label: str | None = None  # e.g. Naver display string


def _parse_multiple(raw: object) -> float | None:
    """Parse values like '20.77배', '12,372원'."""
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "")
    if not text or text in {"-", "N/A"}:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _parse_market_value_krw(raw: object) -> float | None:
    """Parse Naver marketValue text like '1,502조 4,936억' into KRW."""
    if raw is None:
        return None
    text = str(raw).replace(",", "").strip()
    if not text:
        return None
    total = 0.0
    matched = False
    m_jo = re.search(r"(\d+(?:\.\d+)?)\s*조", text)
    if m_jo:
        total += float(m_jo.group(1)) * 1e12
        matched = True
    m_uk = re.search(r"(\d+(?:\.\d+)?)\s*억", text)
    if m_uk:
        total += float(m_uk.group(1)) * 1e8
        matched = True
    if matched:
        return total
    return _parse_multiple(text)


def fetch_fundamentals(
    code: str,
    *,
    timeout: float = 12.0,
) -> FundamentalSnapshot | None:
    code6 = str(code).zfill(6)
    try:
        resp = requests.get(
            _URL.format(code=code6), headers=_HEADERS, timeout=timeout
        )
        if resp.status_code != 200:
            return None
        payload = resp.json()
    except Exception as exc:
        logger.warning("fundamentals failed for %s: %s", code6, exc)
        return None

    infos = {
        str(row.get("code")): row
        for row in (payload.get("totalInfos") or [])
        if isinstance(row, dict) and row.get("code")
    }
    market_label = None
    if "marketValue" in infos:
        market_label = str(infos["marketValue"].get("value") or "") or None

    return FundamentalSnapshot(
        per=_parse_multiple((infos.get("per") or {}).get("value")),
        pbr=_parse_multiple((infos.get("pbr") or {}).get("value")),
        eps=_parse_multiple((infos.get("eps") or {}).get("value")),
        bps=_parse_multiple((infos.get("bps") or {}).get("value")),
        market_cap_krw=_parse_market_value_krw(
            (infos.get("marketValue") or {}).get("value")
        ),
        market_cap_label=market_label,
    )
