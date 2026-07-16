"""DART OpenAPI disclosures for Korean equities (optional enrichment).

Requires ``DART_API_KEY`` from https://opendart.fss.or.kr/
When the key is missing, returns a clear unavailable sentinel.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

import requests

from tradingagents.dataflows.errors import VendorNotConfiguredError
from tradingagents.dataflows.kr_symbols import company_name_for, kr_base_code, normalize_kr_symbol

logger = logging.getLogger(__name__)

_DART_LIST = "https://opendart.fss.or.kr/api/list.json"


def _require_key() -> str:
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        raise VendorNotConfiguredError("DART_API_KEY is not set")
    return key


def get_disclosures_dart(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 10,
) -> str:
    """Return recent DART disclosure titles for a KRX ticker."""
    try:
        api_key = _require_key()
    except VendorNotConfiguredError:
        return (
            "DATA_UNAVAILABLE: DART_API_KEY not set. "
            "Skip disclosures; do not fabricate filings."
        )

    symbol = normalize_kr_symbol(ticker)
    code = kr_base_code(symbol)
    if not code:
        return f"NO_DATA_AVAILABLE: '{ticker}' is not a KRX equity for DART."

    end = end_date or datetime.now().strftime("%Y%m%d")
    if start_date:
        start = start_date.replace("-", "")
    else:
        start = (datetime.now() - timedelta(days=90)).strftime("%Y%m%d")
    end = end.replace("-", "")

    # DART uses corp codes, not stock codes. ``corp_code`` lookup needs the
    # bulk corpCode.zip; as a pragmatic MVP we search by stock_code filter
    # when the API accepts it via ``corp_cls`` list endpoints. OpenDART list
    # supports ``corp_code`` only — so we use the stock code in the query
    # text fallback via company name search is not available without corp map.
    #
    # Workaround: call list with bgn_de/end_de and filter client-side is not
    # possible without corp_code. Instead document that users can set
    # DART_CORP_CODE_<stock> env, e.g. DART_CORP_CODE_005930=00126380.
    corp_env = f"DART_CORP_CODE_{code}"
    corp_code = os.environ.get(corp_env, "").strip()
    if not corp_code:
        name = company_name_for(code) or code
        return (
            f"DATA_UNAVAILABLE: Set {corp_env} to the OpenDART corp_code for "
            f"{name} ({symbol}) to enable disclosure fetch. "
            f"Download corpCode.xml from opendart.fss.or.kr."
        )

    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bgn_de": start,
        "end_de": end,
        "page_count": min(limit, 100),
    }
    try:
        resp = requests.get(_DART_LIST, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logger.warning("DART list failed for %s: %s", symbol, exc)
        return f"DATA_UNAVAILABLE: DART request failed ({exc})."

    if str(payload.get("status")) not in {"000", "013"}:
        return (
            f"DATA_UNAVAILABLE: DART status={payload.get('status')} "
            f"message={payload.get('message')}"
        )

    rows = payload.get("list") or []
    if not rows:
        return f"NO_DATA_AVAILABLE: No DART disclosures for {symbol} in window."

    lines = [f"# DART disclosures for {symbol}", ""]
    for i, row in enumerate(rows[:limit], 1):
        report = row.get("report_nm", "")
        rcept = row.get("rcept_dt", "")
        lines.append(f"{i}. [{rcept}] {report}")
    return "\n".join(lines)
