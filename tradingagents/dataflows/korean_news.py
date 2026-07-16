"""Korean news / headlines for KRX equities.

Primary source: Google News RSS (hl=ko). Optional Naver Finance page scrape
as a secondary attempt. Returns a clear sentinel when nothing is available.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from html import unescape
from urllib.parse import quote

import requests

from tradingagents.dataflows.kr_symbols import company_name_for, kr_base_code, normalize_kr_symbol

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; TradingAgents-KR/0.3; +https://github.com/TauricResearch/TradingAgents)"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return unescape(_TAG_RE.sub("", text or "")).strip()


def _query_for_ticker(ticker: str) -> str:
    code = kr_base_code(ticker) or ticker
    name = company_name_for(code)
    if name:
        return f"{name} 주식"
    return f"{code} 주식"


def _google_news_rss(query: str, limit: int) -> list[str]:
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    )
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    titles: list[str] = []
    for item in root.findall(".//item"):
        title = _strip_html(item.findtext("title") or "")
        if title and title not in titles:
            titles.append(title)
        if len(titles) >= limit:
            break
    return titles


def _naver_search_titles(query: str, limit: int) -> list[str]:
    url = "https://search.naver.com/search.naver?where=news&query=" + quote(query)
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    titles: list[str] = []
    for m in re.finditer(
        r'<a[^>]+class="news_tit"[^>]*title="([^"]+)"',
        resp.text,
        re.IGNORECASE,
    ):
        title = unescape(m.group(1)).strip()
        if title and title not in titles:
            titles.append(title)
        if len(titles) >= limit:
            break
    return titles


def get_news_korean(
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
) -> str:
    """Fetch recent Korean headlines for ``ticker``."""
    symbol = normalize_kr_symbol(ticker)
    code = kr_base_code(symbol)
    if not code:
        return (
            f"NO_DATA_AVAILABLE: '{ticker}' is not a recognized KRX equity symbol "
            f"for the korean_news vendor."
        )

    query = _query_for_ticker(symbol)
    titles: list[str] = []
    errors: list[str] = []

    for fetcher, label in (
        (lambda: _google_news_rss(query, limit), "google_rss"),
        (lambda: _naver_search_titles(query, limit), "naver_search"),
    ):
        try:
            titles = fetcher()
            if titles:
                break
        except Exception as exc:
            logger.warning("korean_news %s failed for %s: %s", label, symbol, exc)
            errors.append(f"{label}: {exc}")

    if not titles:
        detail = "; ".join(errors) if errors else "empty result"
        return (
            f"NO_DATA_AVAILABLE: No Korean headlines found for {symbol} "
            f"(query={query!r}; {detail})."
        )

    end = end_date or datetime.now().strftime("%Y-%m-%d")
    start = start_date or (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    lines = [
        f"# Korean news for {symbol} ({query})",
        f"Window: {start} → {end}",
        "",
    ]
    for i, title in enumerate(titles[:limit], 1):
        lines.append(f"{i}. {title}")
    return "\n".join(lines)


def get_global_news_korean(
    curr_date: str | None = None,
    look_back_days: int | None = None,
    limit: int | None = None,
) -> str:
    """Fetch Korea macro / market headlines."""
    from tradingagents.dataflows.config import get_config

    config = get_config()
    if look_back_days is None:
        look_back_days = config.get("global_news_lookback_days", 7)
    if limit is None:
        limit = config.get("global_news_article_limit", 10)

    queries = config.get("global_news_queries") or [
        "코스피 증시",
        "한국은행 기준금리",
        "반도체 수출 한국",
    ]

    headlines: list[str] = []
    per_q = max(2, int(limit) // max(len(queries), 1))
    for q in queries:
        try:
            for title in _google_news_rss(q, per_q):
                tagged = f"[{q}] {title}"
                if tagged not in headlines:
                    headlines.append(tagged)
                if len(headlines) >= int(limit):
                    break
        except Exception as exc:
            logger.warning("korean global news failed for %r: %s", q, exc)
        if len(headlines) >= int(limit):
            break

    if not headlines:
        return (
            "DATA_UNAVAILABLE: korean_news could not retrieve Korea macro headlines."
        )

    as_of = curr_date or datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# Korea macro / market news (as of {as_of}, lookback≈{look_back_days}d)",
        "",
    ]
    for i, h in enumerate(headlines[: int(limit)], 1):
        lines.append(f"{i}. {h}")
    return "\n".join(lines)
