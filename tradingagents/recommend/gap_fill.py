"""Fill missing daily reports since the last successful run_daily."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytz

from tradingagents.dataflows.kr_symbols import normalize_kr_symbol
from tradingagents.recommend.backtest import (
    score_history_index,
    signal_counts_for,
    signal_markers_for,
    trading_days,
)
from tradingagents.recommend.engine import _fetch_history, analyze_ticker, run_daily_recommendations
from tradingagents.recommend.paths import report_exists, run_state_path
from tradingagents.recommend.universe import build_watchlist

logger = logging.getLogger(__name__)

KST = pytz.timezone("Asia/Seoul")
MIN_REPORT_DATE = "2025-01-01"


def _next_trading_day_after(day: str) -> str:
    start = (pd.Timestamp(day) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    end = (pd.Timestamp(day) + pd.Timedelta(days=14)).strftime("%Y-%m-%d")
    days = trading_days(start, end)
    return days[0] if days else start


def load_run_state(*, output_dir: Path | None = None) -> dict[str, Any] | None:
    path = run_state_path(output_dir=output_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("run state read failed: %s", exc)
        return None


def save_run_state(
    *,
    last_cover_to: str,
    output_dir: Path | None = None,
) -> None:
    path = run_state_path(output_dir=output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_cover_to": last_cover_to,
        "updated_at": datetime.now(KST).isoformat(),
        "min_report_date": MIN_REPORT_DATE,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def gap_scan_start(*, output_dir: Path | None = None) -> str:
    """First trading day to check for missing reports (cheap window)."""
    state = load_run_state(output_dir=output_dir)
    if state and state.get("last_cover_to"):
        return max(_next_trading_day_after(str(state["last_cover_to"])), MIN_REPORT_DATE)
    return MIN_REPORT_DATE


def find_missing_report_days(
    target_as_of: str,
    *,
    output_dir: Path | None = None,
) -> list[str]:
    """Trading days in [scan_start, target_as_of] without report.json."""
    scan_start = gap_scan_start(output_dir=output_dir)
    if scan_start > target_as_of:
        return []
    days = trading_days(scan_start, target_as_of)
    return [d for d in days if d >= MIN_REPORT_DATE and not report_exists(d, output_dir=output_dir)]


def _ensure_hist(
    code: str,
    ticker: str,
    *,
    hist_cache: dict[str, object],
    ticker_by_code: dict[str, str],
) -> str | None:
    symbol = ticker_by_code.get(code) or normalize_kr_symbol(ticker or code)
    if symbol in hist_cache:
        ticker_by_code[code] = symbol
        return symbol
    try:
        hist, symbol = _fetch_history(symbol, period="5y")
        hist_cache[symbol] = hist
        ticker_by_code[code] = symbol
        return symbol
    except Exception as exc:
        logger.warning("hist fail %s: %s", code, exc)
        ticker_by_code[code] = symbol
        hist_cache[symbol] = None
        return symbol


def fill_pit_gap_day(
    day: str,
    *,
    output_dir: Path | None = None,
    hist_cache: dict[str, object],
    ticker_by_code: dict[str, str],
    include_chart: bool = True,
) -> bool:
    """Generate one missing day with PIT watchlist (no news, no latest.*)."""
    try:
        watchlist = build_watchlist(
            as_of=day,
            save=False,
            allow_live_fallback=False,
            cap_top_n=50,
            amount_top_n=20,
            lookback_days=7,
        )
    except Exception as exc:
        logger.warning("gap fill watchlist failed %s: %s", day, exc)
        print(f"  {day} 워치리스트 실패: {exc}", flush=True)
        return False

    chart_start = (pd.Timestamp(day) - pd.Timedelta(days=100)).strftime("%Y-%m-%d")
    score_start = (pd.Timestamp(day) - pd.Timedelta(days=183)).strftime("%Y-%m-%d")
    score_by_code = (
        score_history_index(start=score_start, end=day) if include_chart else {}
    )

    recs = []
    for w in watchlist:
        symbol = _ensure_hist(
            w["code"],
            w.get("ticker") or w["code"],
            hist_cache=hist_cache,
            ticker_by_code=ticker_by_code,
        )
        hist = hist_cache.get(symbol) if symbol else None
        buy_n, caution_n = signal_counts_for(w["code"], as_of=day)
        markers = (
            signal_markers_for(w["code"], start=chart_start, end=day)
            if include_chart
            else None
        )
        recs.append(
            analyze_ticker(
                w["code"],
                w["name"],
                symbol or normalize_kr_symbol(w.get("ticker") or w["code"]),
                include_news=False,
                as_of=day,
                hist=hist,
                include_chart=include_chart,
                include_fundamentals=True,
                chart_markers=markers,
                signal_buy_count=buy_n,
                signal_caution_count=caution_n,
                score_history=score_by_code.get(str(w["code"]).zfill(6)),
            )
        )

    run_daily_recommendations(
        output_dir=output_dir,
        include_news=False,
        as_of=day,
        update_latest=False,
        include_chart=include_chart,
        include_fundamentals=True,
        record_backtest=True,
        watchlist=watchlist,
        recommendations=recs,
    )
    return True


def fill_missing_reports(
    missing_days: list[str],
    *,
    output_dir: Path | None = None,
    include_chart: bool = True,
) -> int:
    """Fill historical gap days (excludes the current target day). Returns count filled."""
    if not missing_days:
        return 0

    hist_cache: dict[str, object] = {}
    ticker_by_code: dict[str, str] = {}
    filled = 0
    total = len(missing_days)

    for i, day in enumerate(missing_days, 1):
        print(f"[누락 보완 {i}/{total}] {day} · PIT 워치리스트", flush=True)
        if fill_pit_gap_day(
            day,
            output_dir=output_dir,
            hist_cache=hist_cache,
            ticker_by_code=ticker_by_code,
            include_chart=include_chart,
        ):
            filled += 1

    return filled


def fill_gaps_before_daily(
    target_as_of: str,
    *,
    output_dir: Path | None = None,
    include_chart: bool = True,
) -> list[str]:
    """Fill missing reports strictly before ``target_as_of``. Returns days filled."""
    missing = find_missing_report_days(target_as_of, output_dir=output_dir)
    gap_days = [d for d in missing if d < target_as_of]
    if not gap_days:
        return []

    scan_start = gap_scan_start(output_dir=output_dir)
    print(
        f"누락 리포트 {len(gap_days)}일 보완 ({scan_start}~{target_as_of} 구간 검사)",
        flush=True,
    )
    fill_missing_reports(gap_days, output_dir=output_dir, include_chart=include_chart)
    return gap_days
