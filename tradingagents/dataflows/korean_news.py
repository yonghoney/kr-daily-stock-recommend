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


def _parse_rss_date(raw: str | None) -> str | None:
    """Convert RSS pubDate to YYYY-MM-DD (KST-ish display uses calendar day of pubDate)."""
    if not raw:
        return None
    text = raw.strip()
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%d",
    ):
        try:
            # %Z often fails for 'GMT'; try replace
            candidate = text.replace("GMT", "+0000").replace("UTC", "+0000")
            if fmt.endswith("%Z"):
                dt = datetime.strptime(text[:25].strip(), "%a, %d %b %Y %H:%M:%S")
            elif "%z" in fmt:
                dt = datetime.strptime(candidate, "%a, %d %b %Y %H:%M:%S %z")
            else:
                dt = datetime.strptime(text[:10], fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    # Fallback: pull YYYY later in string is rare; try day mon year tokens
    m = re.search(
        r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})",
        text,
        re.I,
    )
    if m:
        try:
            dt = datetime.strptime(
                f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %b %Y"
            )
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def _google_news_rss(query: str, limit: int) -> list[dict[str, str]]:
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"
    )
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in root.findall(".//item"):
        title = _strip_html(item.findtext("title") or "")
        if not title or title in seen:
            continue
        seen.add(title)
        date = _parse_rss_date(item.findtext("pubDate"))
        row: dict[str, str] = {"title": title}
        if date:
            row["date"] = date
        items.append(row)
        if len(items) >= limit:
            break
    return items


def _naver_search_titles(query: str, limit: int) -> list[dict[str, str]]:
    url = "https://search.naver.com/search.naver?where=news&query=" + quote(query)
    resp = requests.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    # Each news card: title + nearby info date when present
    for m in re.finditer(
        r'<a[^>]+class="news_tit"[^>]*title="([^"]+)"[\s\S]{0,800}?'
        r'(?:data-date(?:time)?="([^"]+)"|(\d{4}\.\d{2}\.\d{2})\.?)',
        resp.text,
        re.IGNORECASE,
    ):
        title = unescape(m.group(1)).strip()
        if not title or title in seen:
            continue
        seen.add(title)
        raw_date = (m.group(2) or m.group(3) or "").strip()
        date = None
        if raw_date:
            raw_date = raw_date.replace(".", "-")[:10]
            date = _parse_rss_date(raw_date) or (
                raw_date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_date) else None
            )
        row: dict[str, str] = {"title": title}
        if date:
            row["date"] = date
        items.append(row)
        if len(items) >= limit:
            break
    if items:
        return items
    # Title-only fallback
    for m in re.finditer(
        r'<a[^>]+class="news_tit"[^>]*title="([^"]+)"',
        resp.text,
        re.IGNORECASE,
    ):
        title = unescape(m.group(1)).strip()
        if title and title not in seen:
            seen.add(title)
            items.append({"title": title})
        if len(items) >= limit:
            break
    return items


def _sort_headline_items(items: list[dict[str, str]]) -> list[dict[str, str]]:
    """Newest date first; undated items go last (stable by title)."""
    return sorted(
        items,
        key=lambda it: (it.get("date") or "0000-00-00", it.get("title") or ""),
        reverse=True,
    )


def fetch_korean_headline_items(
    ticker: str,
    *,
    limit: int = 3,
) -> list[dict[str, str]]:
    """Return ``[{title, date?}, ...]`` for a KRX ticker (newest first)."""
    symbol = normalize_kr_symbol(ticker)
    code = kr_base_code(symbol)
    if not code:
        return []
    query = _query_for_ticker(symbol)
    # Pull a wider pool, then sort and keep the newest ``limit`` items.
    pool = max(limit * 5, 15)
    for fetcher, label in (
        (lambda: _google_news_rss(query, pool), "google_rss"),
        (lambda: _naver_search_titles(query, pool), "naver_search"),
    ):
        try:
            items = fetcher()
            if items:
                return _sort_headline_items(items)[:limit]
        except Exception as exc:
            logger.warning("korean_news %s failed for %s: %s", label, symbol, exc)
    return []


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
    items = fetch_korean_headline_items(symbol, limit=limit)
    if not items:
        return (
            f"NO_DATA_AVAILABLE: No Korean headlines found for {symbol} "
            f"(query={query!r})."
        )

    end = end_date or datetime.now().strftime("%Y-%m-%d")
    start = start_date or (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    lines = [
        f"# Korean news for {symbol} ({query})",
        f"Window: {start} → {end}",
        "",
    ]
    for i, item in enumerate(items[:limit], 1):
        date = item.get("date")
        title = item.get("title", "")
        if date:
            lines.append(f"{i}. [{date}] {title}")
        else:
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
            for item in _google_news_rss(q, per_q):
                title = item.get("title", "")
                date = item.get("date")
                tagged = f"[{q}] {title}" if not date else f"[{q}] [{date}] {title}"
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
