"""Auto-refresh KR watchlist from KRX rankings.

Uses FinanceDataReader StockListing (no KRX login required).
Each run rebuilds the universe as the union of:
  - top N by trading value (Amount)
  - top N by market cap (Marcap)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytz
import yaml

logger = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _universe_path(path: Path | None = None) -> Path:
    return path or (_project_root() / "config" / "kr_universe.yaml")


def _load_listings() -> pd.DataFrame:
    import FinanceDataReader as fdr

    frames: list[pd.DataFrame] = []
    for market in ("KOSPI", "KOSDAQ"):
        df = fdr.StockListing(market)
        if df is None or df.empty:
            continue
        df = df.copy()
        df["Market"] = market
        frames.append(df)
    if not frames:
        raise RuntimeError("FinanceDataReader returned empty KOSPI/KOSDAQ listings")

    combined = pd.concat(frames, ignore_index=True)
    colmap = {}
    for col in combined.columns:
        c = str(col)
        cl = c.lower()
        if c == "Code" or cl == "code":
            colmap[col] = "Code"
        elif c == "Name" or cl == "name":
            colmap[col] = "Name"
        elif c == "Market" or cl == "market":
            colmap[col] = "Market"
        elif c in {"Marcap", "MarCap", "시가총액"} or "marcap" in cl:
            colmap[col] = "Marcap"
        elif c in {"Amount", "거래대금"} or cl == "amount":
            colmap[col] = "Amount"
    combined = combined.rename(columns=colmap)

    required = {"Code", "Name", "Market", "Marcap", "Amount"}
    missing = required - set(combined.columns)
    if missing:
        raise RuntimeError(f"Listing missing columns: {sorted(missing)}")

    combined["Code"] = combined["Code"].astype(str).str.zfill(6)
    combined["Marcap"] = pd.to_numeric(combined["Marcap"], errors="coerce").fillna(0)
    combined["Amount"] = pd.to_numeric(combined["Amount"], errors="coerce").fillna(0)
    combined = combined[combined["Marcap"] > 0].copy()
    combined = combined.drop_duplicates(subset=["Code"], keep="first")
    return combined


def _yahoo_ticker(code: str, market: str) -> str:
    market_u = str(market).upper()
    if "KOSDAQ" in market_u:
        return f"{code}.KQ"
    return f"{code}.KS"


def refresh_and_save_watchlist(
    *,
    path: Path | None = None,
    top_n: int = 20,
) -> list[dict[str, str]]:
    """Rebuild watchlist as union of top-N trading value and top-N market cap."""
    path = _universe_path(path)
    df = _load_listings()
    as_of = datetime.now(KST).strftime("%Y-%m-%d")

    by_value = df.nlargest(top_n, "Amount")
    by_cap = df.nlargest(top_n, "Marcap")

    selected: dict[str, dict[str, str]] = {}
    for source_df in (by_value, by_cap):
        for _, row in source_df.iterrows():
            code = str(row["Code"]).zfill(6)
            if code in selected:
                continue
            market = str(row.get("Market", "KOSPI"))
            selected[code] = {
                "code": code,
                "name": str(row.get("Name") or code),
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
        code
        for code in selected
        if "KOSDAQ" in str(df.loc[df["Code"] == code, "Market"].iloc[0])
    )
    cap_order = {
        str(code).zfill(6): n
        for n, code in enumerate(df.nlargest(len(df), "Marcap")["Code"].tolist())
    }
    watchlist = sorted(
        selected.values(),
        key=lambda w: (cap_order.get(w["code"], 10**9), w["code"]),
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
            "source": "FinanceDataReader.StockListing",
            "top_n": top_n,
            "count": len(watchlist),
            "by_trading_value": [str(x).zfill(6) for x in by_value["Code"].tolist()],
            "by_market_cap": [str(x).zfill(6) for x in by_cap["Code"].tolist()],
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
        "Watchlist refreshed: %d names (top %d Amount U top %d Marcap)",
        len(watchlist),
        top_n,
        top_n,
    )
    return watchlist
