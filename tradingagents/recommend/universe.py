"""Auto-refresh KR watchlist from KRX rankings.

Each run rebuilds the universe as the union, per market (KOSPI / KOSDAQ), of:
  - names that appeared in that market's daily trading-value (Amount) top-N
    on any session in the last calendar week
  - that market's current market-cap (Marcap) top-N

Daily snapshots come from FinanceDataReader's KRX listing cache
(https://github.com/FinanceData/fdr_krx_data_cache).
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytz
import requests
import yaml

logger = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")

_CACHE_BASE = (
    "https://raw.githubusercontent.com/FinanceData/fdr_krx_data_cache/"
    "refs/heads/master/data/listing/krx"
)
_MARKET_ID = {"KOSPI": "STK", "KOSDAQ": "KSQ"}


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _universe_path(path: Path | None = None) -> Path:
    return path or (_project_root() / "config" / "kr_universe.yaml")


def _normalize_listing(df: pd.DataFrame) -> pd.DataFrame:
    colmap: dict[Any, str] = {}
    for col in df.columns:
        c = str(col)
        cl = c.lower()
        if c == "Code" or cl == "code":
            colmap[col] = "Code"
        elif c == "Name" or cl == "name":
            colmap[col] = "Name"
        elif c == "Market" or cl == "market":
            colmap[col] = "Market"
        elif c == "MarketId" or cl == "marketid":
            colmap[col] = "MarketId"
        elif c in {"Marcap", "MarCap", "시가총액"} or "marcap" in cl:
            colmap[col] = "Marcap"
        elif c in {"Amount", "거래대금"} or cl == "amount":
            colmap[col] = "Amount"
    out = df.rename(columns=colmap)
    required = {"Code", "Name", "Marcap", "Amount"}
    missing = required - set(out.columns)
    if missing:
        raise RuntimeError(f"Listing missing columns: {sorted(missing)}")

    out = out.copy()
    out["Code"] = out["Code"].astype(str).str.zfill(6)
    out["Marcap"] = pd.to_numeric(out["Marcap"], errors="coerce").fillna(0)
    out["Amount"] = pd.to_numeric(out["Amount"], errors="coerce").fillna(0)
    if "MarketId" not in out.columns and "Market" in out.columns:
        out["MarketId"] = out["Market"].map(
            {"KOSPI": "STK", "KOSDAQ": "KSQ", "KONEX": "KNX"}
        )
    return out


def _fetch_listing_for_date(day: str, timeout: float = 20.0) -> pd.DataFrame | None:
    """Load one day of KRX listing cache. ``day`` is YYYY-MM-DD."""
    url = f"{_CACHE_BASE}/{day}.csv"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code != 200:
            return None
        df = pd.read_csv(
            io.BytesIO(resp.content),
            dtype={"Code": str, "MarketId": str, "Dept": str, "ChangeCode": str},
        )
    except Exception as exc:
        logger.debug("No listing cache for %s: %s", day, exc)
        return None
    if df is None or df.empty:
        return None
    return _normalize_listing(df)


def _filter_market(df: pd.DataFrame, market: str) -> pd.DataFrame:
    mid = _MARKET_ID[market]
    if "MarketId" in df.columns:
        out = df[df["MarketId"].astype(str) == mid]
    else:
        out = df[df["Market"].astype(str).str.upper().str.contains(market)]
    return out[out["Marcap"] > 0].drop_duplicates(subset=["Code"], keep="first")


def _yahoo_ticker(code: str, market: str) -> str:
    if market == "KOSDAQ":
        return f"{code}.KQ"
    return f"{code}.KS"


def _load_recent_daily_frames(
    *,
    as_of: datetime | None = None,
    lookback_days: int = 7,
) -> dict[str, pd.DataFrame]:
    """Load KRX listing cache for each available day in the lookback window."""
    now = as_of or datetime.now(KST)
    frames: dict[str, pd.DataFrame] = {}
    for i in range(lookback_days):
        day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        frame = _fetch_listing_for_date(day)
        if frame is not None:
            frames[day] = frame
    return frames


def _load_live_listings() -> pd.DataFrame:
    import FinanceDataReader as fdr

    frames = []
    for market in ("KOSPI", "KOSDAQ"):
        live = fdr.StockListing(market)
        if live is None or live.empty:
            continue
        live = _normalize_listing(live.copy())
        live["MarketId"] = _MARKET_ID[market]
        frames.append(live)
    if not frames:
        raise RuntimeError("Could not load KRX listings (cache and live both empty)")
    return pd.concat(frames, ignore_index=True)


def refresh_and_save_watchlist(
    *,
    path: Path | None = None,
    top_n: int = 50,
    lookback_days: int = 7,
) -> list[dict[str, str]]:
    """Rebuild watchlist per-market: weekly Amount top-N union + Marcap top-N."""
    path = _universe_path(path)
    as_of_dt = datetime.now(KST)
    as_of = as_of_dt.strftime("%Y-%m-%d")

    daily_frames = _load_recent_daily_frames(
        as_of=as_of_dt, lookback_days=lookback_days
    )
    if not daily_frames:
        latest = _load_live_listings()
        session_dates = [as_of]
        daily_frames = {as_of: latest}
        logger.warning("KRX daily cache unavailable; using live StockListing only")
    else:
        session_dates = sorted(daily_frames)
        latest = daily_frames[max(session_dates)]

    selected: dict[str, dict[str, str]] = {}
    by_amount: dict[str, list[str]] = {"KOSPI": [], "KOSDAQ": []}
    by_cap: dict[str, list[str]] = {"KOSPI": [], "KOSDAQ": []}
    amount_hits_by_day: dict[str, dict[str, list[str]]] = {}

    for market in ("KOSPI", "KOSDAQ"):
        amount_codes: set[str] = set()
        for day, frame in daily_frames.items():
            mdf = _filter_market(frame, market)
            if mdf.empty:
                continue
            top = mdf.nlargest(top_n, "Amount")
            day_codes = [str(c).zfill(6) for c in top["Code"].tolist()]
            amount_codes.update(day_codes)
            amount_hits_by_day.setdefault(day, {})[market] = day_codes

        cap_df = _filter_market(latest, market)
        cap_top = cap_df.nlargest(top_n, "Marcap")
        cap_codes = [str(c).zfill(6) for c in cap_top["Code"].tolist()]
        by_amount[market] = sorted(amount_codes)
        by_cap[market] = cap_codes

        name_lookup = {
            str(r["Code"]).zfill(6): str(r.get("Name") or r["Code"])
            for _, r in cap_df.iterrows()
        }
        # Enrich names from any session if missing on latest
        for frame in daily_frames.values():
            mdf = _filter_market(frame, market)
            for _, r in mdf.iterrows():
                code = str(r["Code"]).zfill(6)
                name_lookup.setdefault(code, str(r.get("Name") or code))

        for code in amount_codes | set(cap_codes):
            if code in selected:
                continue
            selected[code] = {
                "code": code,
                "name": name_lookup.get(code, code),
                "ticker": _yahoo_ticker(code, market),
            }

    existing: dict[str, Any] = {}
    if path.is_file():
        try:
            with open(path, encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
        except Exception:
            existing = {}

    kosdaq_codes = sorted(
        code for code, item in selected.items() if item["ticker"].endswith(".KQ")
    )
    cap_rank = {
        str(c).zfill(6): i
        for i, c in enumerate(
            latest.sort_values("Marcap", ascending=False)["Code"].tolist()
        )
    }
    watchlist = sorted(
        selected.values(),
        key=lambda w: (cap_rank.get(w["code"], 10**9), w["code"]),
    )

    universe: dict[str, Any] = {
        "watchlist": watchlist,
        "kosdaq": kosdaq_codes,
        "risk": (existing.get("risk") if isinstance(existing, dict) else None)
        or {
            "max_order_notional_krw": 1_000_000,
            "max_daily_notional_krw": 5_000_000,
            "max_positions": 5,
            "order_cooldown_seconds": 60,
        },
        "universe_meta": {
            "as_of": as_of,
            "source": "FinanceDataReader fdr_krx_data_cache",
            "top_n": top_n,
            "lookback_days": lookback_days,
            "session_dates": session_dates,
            "count": len(watchlist),
            "by_trading_value": by_amount,
            "by_market_cap": by_cap,
            "amount_hits_by_day": amount_hits_by_day,
        },
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            universe,
            f,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )

    try:
        from tradingagents.dataflows.kr_symbols import _load_universe

        _load_universe.cache_clear()
    except Exception:
        pass

    logger.info(
        "Watchlist refreshed: %d names "
        "(per-market Amount top %d over %d days U Marcap top %d)",
        len(watchlist),
        top_n,
        len(session_dates),
        top_n,
    )
    return watchlist
