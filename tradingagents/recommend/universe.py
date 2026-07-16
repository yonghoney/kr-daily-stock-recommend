"""Auto-refresh KR watchlist from KRX rankings.

Each run rebuilds the universe as the union, per market (KOSPI / KOSDAQ), of:
  - common shares only (preferred shares excluded)
  - that market's current market-cap (Marcap) top-N
  - names that appeared in that market's daily trading-value (Amount) top-M
    on any session in the last calendar week, after removing the Marcap top-N set

Daily snapshots come from FinanceDataReader's KRX listing cache
(https://github.com/FinanceData/fdr_krx_data_cache) when available,
and otherwise from the FinanceData marcap dataset
(https://github.com/FinanceData/marcap) for historical PIT backfills.
"""

from __future__ import annotations

import io
import logging
import re
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
_MARCAP_BASE = (
    "https://github.com/FinanceData/marcap/raw/master/data"
)
_MARKET_ID = {"KOSPI": "STK", "KOSDAQ": "KSQ"}

# In-process memo for listing CSVs / marcap day slices
_LISTING_MEMO: dict[str, pd.DataFrame | None] = {}
_MARCAP_YEAR: dict[int, pd.DataFrame] = {}

# KRX preferred-share name suffixes (보통주만 남김)
_PREFERRED_NAME = re.compile(
    r"(우B|우C|우D|우E|1우|2우|3우|4우|5우|우선주?|우)$"
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _universe_path(path: Path | None = None) -> Path:
    return path or (_project_root() / "config" / "kr_universe.yaml")


def _is_preferred(name: object) -> bool:
    text = str(name or "").strip()
    if not text:
        return False
    # Drop parenthetical notes: "CJ4우(전환)" -> "CJ4우"
    base = re.sub(r"\(.*?\)", "", text).strip()
    return bool(_PREFERRED_NAME.search(base))


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


def _marcap_cache_dir() -> Path:
    d = _project_root() / "data" / "marcap"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ensure_marcap_year(year: int) -> pd.DataFrame:
    """Load (and download if needed) FinanceData/marcap yearly parquet."""
    if year in _MARCAP_YEAR:
        return _MARCAP_YEAR[year]
    path = _marcap_cache_dir() / f"marcap-{year}.parquet"
    if not path.exists():
        url = f"{_MARCAP_BASE}/marcap-{year}.parquet"
        logger.info("Downloading marcap %s …", year)
        resp = requests.get(url, timeout=300)
        if resp.status_code != 200:
            raise RuntimeError(f"marcap-{year}.parquet download failed: HTTP {resp.status_code}")
        path.write_bytes(resp.content)
    df = pd.read_parquet(path)
    if "Date" not in df.columns:
        raise RuntimeError(f"marcap-{year}.parquet missing Date column")
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"]).dt.normalize()
    _MARCAP_YEAR[year] = df
    return df


def _fetch_listing_from_marcap(day: str) -> pd.DataFrame | None:
    year = int(day[:4])
    try:
        df = _ensure_marcap_year(year)
    except Exception as exc:
        logger.debug("marcap year %s unavailable: %s", year, exc)
        return None
    day_ts = pd.Timestamp(day).normalize()
    slice_df = df[df["Date"] == day_ts]
    if slice_df.empty:
        return None
    return _normalize_listing(slice_df)


def _fetch_listing_for_date(day: str, timeout: float = 20.0) -> pd.DataFrame | None:
    """Load one day of listings. Prefer FDR daily CSV, else marcap parquet."""
    if day in _LISTING_MEMO:
        return _LISTING_MEMO[day]
    url = f"{_CACHE_BASE}/{day}.csv"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            df = pd.read_csv(
                io.BytesIO(resp.content),
                dtype={"Code": str, "MarketId": str, "Dept": str, "ChangeCode": str},
            )
            if df is not None and not df.empty:
                normalized = _normalize_listing(df)
                _LISTING_MEMO[day] = normalized
                return normalized
    except Exception as exc:
        logger.debug("No FDR listing cache for %s: %s", day, exc)

    marcap = _fetch_listing_from_marcap(day)
    _LISTING_MEMO[day] = marcap
    return marcap


def _filter_market(
    df: pd.DataFrame,
    market: str,
    *,
    exclude_preferred: bool = True,
) -> pd.DataFrame:
    mid = _MARKET_ID[market]
    if "MarketId" in df.columns:
        out = df[df["MarketId"].astype(str) == mid]
    else:
        out = df[df["Market"].astype(str).str.upper().str.contains(market)]
    out = out[out["Marcap"] > 0].drop_duplicates(subset=["Code"], keep="first")
    if exclude_preferred:
        out = out[~out["Name"].map(_is_preferred)]
    return out


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


def build_watchlist(
    *,
    as_of: str | None = None,
    path: Path | None = None,
    cap_top_n: int = 50,
    amount_top_n: int = 20,
    lookback_days: int = 7,
    save: bool = True,
    allow_live_fallback: bool = True,
) -> list[dict[str, str]]:
    """Build Marcap top-N ∪ (weekly Amount top-M outside Marcap) as of ``as_of``.

    When ``save`` is False (typical for historical backfill), the yaml file is
    not overwritten. Live StockListing fallback is disabled unless
    ``allow_live_fallback`` is True (daily runs only).
    """
    path = _universe_path(path)
    if as_of:
        as_of_dt = datetime.strptime(as_of, "%Y-%m-%d").replace(tzinfo=KST)
        as_of_str = as_of
    else:
        as_of_dt = datetime.now(KST)
        as_of_str = as_of_dt.strftime("%Y-%m-%d")

    daily_frames = _load_recent_daily_frames(
        as_of=as_of_dt, lookback_days=lookback_days
    )
    if not daily_frames:
        # Widen search for holidays / thin cache weeks
        daily_frames = _load_recent_daily_frames(as_of=as_of_dt, lookback_days=30)

    if not daily_frames:
        if not allow_live_fallback:
            raise RuntimeError(
                f"No KRX listing cache around {as_of_str}; cannot build PIT watchlist"
            )
        latest = _load_live_listings()
        session_dates = [as_of_str]
        daily_frames = {as_of_str: latest}
        logger.warning("KRX daily cache unavailable; using live StockListing only")
    else:
        session_dates = sorted(daily_frames)
        latest = daily_frames[max(session_dates)]

    selected: dict[str, dict[str, str]] = {}
    by_amount: dict[str, list[str]] = {"KOSPI": [], "KOSDAQ": []}
    by_cap: dict[str, list[str]] = {"KOSPI": [], "KOSDAQ": []}
    amount_hits_by_day: dict[str, dict[str, list[str]]] = {}

    for market in ("KOSPI", "KOSDAQ"):
        cap_df = _filter_market(latest, market)
        cap_top = cap_df.nlargest(cap_top_n, "Marcap")
        cap_codes = [str(c).zfill(6) for c in cap_top["Code"].tolist()]
        cap_set = set(cap_codes)
        by_cap[market] = cap_codes

        amount_codes: set[str] = set()
        for day, frame in daily_frames.items():
            mdf = _filter_market(frame, market)
            if mdf.empty:
                continue
            top = mdf.nlargest(amount_top_n, "Amount")
            day_codes = [
                str(c).zfill(6)
                for c in top["Code"].tolist()
                if str(c).zfill(6) not in cap_set
            ]
            amount_codes.update(day_codes)
            amount_hits_by_day.setdefault(day, {})[market] = day_codes

        by_amount[market] = sorted(amount_codes)

        name_lookup = {
            str(r["Code"]).zfill(6): str(r.get("Name") or r["Code"])
            for _, r in cap_df.iterrows()
        }
        for frame in daily_frames.values():
            mdf = _filter_market(frame, market)
            for _, r in mdf.iterrows():
                code = str(r["Code"]).zfill(6)
                name_lookup.setdefault(code, str(r.get("Name") or code))

        for code in set(cap_codes) | amount_codes:
            if code in selected:
                continue
            selected[code] = {
                "code": code,
                "name": name_lookup.get(code, code),
                "ticker": _yahoo_ticker(code, market),
            }

    common_latest = latest[~latest["Name"].map(_is_preferred)]
    cap_rank = {
        str(c).zfill(6): i
        for i, c in enumerate(
            common_latest.sort_values("Marcap", ascending=False)["Code"].tolist()
        )
    }
    watchlist = sorted(
        selected.values(),
        key=lambda w: (cap_rank.get(w["code"], 10**9), w["code"]),
    )

    if save:
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
                "as_of": as_of_str,
                "source": "FinanceDataReader fdr_krx_data_cache",
                "exclude_preferred": True,
                "cap_top_n": cap_top_n,
                "amount_top_n": amount_top_n,
                "lookback_days": lookback_days,
                "session_dates": session_dates,
                "count": len(watchlist),
                "by_market_cap": by_cap,
                "by_trading_value_ex_cap": by_amount,
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
        "Watchlist built as_of=%s: %d names "
        "(per-market Marcap top %d U Amount top %d outside cap, %d days, no preferred)",
        as_of_str,
        len(watchlist),
        cap_top_n,
        amount_top_n,
        len(session_dates),
    )
    return watchlist


def refresh_and_save_watchlist(
    *,
    path: Path | None = None,
    cap_top_n: int = 50,
    amount_top_n: int = 20,
    lookback_days: int = 7,
    as_of: str | None = None,
) -> list[dict[str, str]]:
    """Rebuild and save watchlist (daily entrypoint)."""
    return build_watchlist(
        as_of=as_of,
        path=path,
        cap_top_n=cap_top_n,
        amount_top_n=amount_top_n,
        lookback_days=lookback_days,
        save=True,
        allow_live_fallback=as_of is None,
    )
