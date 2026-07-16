"""Korean investor flow (foreign / institution) via Naver mobile API."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

_TREND_URL = "https://m.stock.naver.com/api/stock/{code}/trend"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://m.stock.naver.com/",
}


def _parse_signed_int(raw: object) -> int:
    """Parse Naver quantities like '+1,799,843' / '-413,531'."""
    if raw is None:
        return 0
    text = str(raw).strip().replace(",", "").replace("%", "")
    if not text or text in {"-", "N/A", "null"}:
        return 0
    text = re.sub(r"[^\d\-+]", "", text)
    if not text or text in {"+", "-"}:
        return 0
    try:
        return int(text)
    except ValueError:
        return 0


@dataclass
class InvestorFlowSnapshot:
    code: str
    as_of: str  # YYYY-MM-DD
    foreign_net_1d: int
    organ_net_1d: int
    individual_net_1d: int
    foreign_net_5d: int
    organ_net_5d: int
    individual_net_5d: int
    foreign_hold_ratio: float | None
    days: int


def fetch_investor_flow(
    code: str,
    *,
    lookback: int = 5,
    timeout: float = 12.0,
) -> InvestorFlowSnapshot | None:
    """Fetch recent pure-buy quantities. Returns None on failure."""
    code6 = str(code).zfill(6)
    url = _TREND_URL.format(code=code6)
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        if resp.status_code != 200:
            logger.debug("investor flow HTTP %s for %s", resp.status_code, code6)
            return None
        rows = resp.json()
    except Exception as exc:
        logger.warning("investor flow failed for %s: %s", code6, exc)
        return None

    if not isinstance(rows, list) or not rows:
        return None

    parsed: list[dict[str, int | str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        biz = str(row.get("bizdate") or "")
        if len(biz) == 8 and biz.isdigit():
            as_of = f"{biz[:4]}-{biz[4:6]}-{biz[6:]}"
        else:
            as_of = biz
        parsed.append(
            {
                "as_of": as_of,
                "foreign": _parse_signed_int(row.get("foreignerPureBuyQuant")),
                "organ": _parse_signed_int(row.get("organPureBuyQuant")),
                "individual": _parse_signed_int(row.get("individualPureBuyQuant")),
                "hold": str(row.get("foreignerHoldRatio") or ""),
            }
        )

    if not parsed:
        return None

    window = parsed[: max(1, lookback)]
    hold_raw = str(parsed[0].get("hold") or "").replace("%", "").strip()
    try:
        hold = float(hold_raw) if hold_raw else None
    except ValueError:
        hold = None

    return InvestorFlowSnapshot(
        code=code6,
        as_of=str(parsed[0]["as_of"]),
        foreign_net_1d=int(parsed[0]["foreign"]),
        organ_net_1d=int(parsed[0]["organ"]),
        individual_net_1d=int(parsed[0]["individual"]),
        foreign_net_5d=sum(int(r["foreign"]) for r in window),
        organ_net_5d=sum(int(r["organ"]) for r in window),
        individual_net_5d=sum(int(r["individual"]) for r in window),
        foreign_hold_ratio=hold,
        days=len(window),
    )
