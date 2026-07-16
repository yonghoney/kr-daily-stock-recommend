"""Market-level daily score aggregates vs KOSPI/KOSDAQ indices."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytz
import yfinance as yf

from tradingagents.recommend.backtest import backtest_dir, load_signals
from tradingagents.recommend.chart_svg import append_svg_legend

logger = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")

INDEX_TICKER = {"코스피": "^KS11", "코스닥": "^KQ11"}
ACTION_POINTS = {"매수관심": 1, "관망": 0, "주의": -1}


def _market_of(row: dict[str, Any]) -> str | None:
    m = str(row.get("market") or "").strip()
    if m in ("코스피", "코스닥"):
        return m
    t = str(row.get("ticker") or "").upper()
    if t.endswith(".KQ"):
        return "코스닥"
    if t.endswith(".KS"):
        return "코스피"
    return None


def aggregate_daily_market_metrics(
    signals: list[dict[str, Any]] | None = None,
    *,
    start: str = "2025-01-01",
    end: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return {market: [{as_of, score_sum, action_sum, n}, ...]} sorted by date."""
    end = end or datetime.now(KST).strftime("%Y-%m-%d")
    rows = signals if signals is not None else load_signals()
    buckets: dict[str, dict[str, dict[str, float]]] = {
        "코스피": defaultdict(lambda: {"score_sum": 0.0, "action_sum": 0.0, "n": 0.0}),
        "코스닥": defaultdict(lambda: {"score_sum": 0.0, "action_sum": 0.0, "n": 0.0}),
    }
    for r in rows:
        day = str(r.get("as_of") or "")
        if day < start or day > end:
            continue
        market = _market_of(r)
        if market is None:
            continue
        try:
            score = float(r.get("score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        action = str(r.get("action") or "관망")
        points = ACTION_POINTS.get(action, 0)
        b = buckets[market][day]
        b["score_sum"] += score
        b["action_sum"] += points
        b["n"] += 1

    out: dict[str, list[dict[str, Any]]] = {}
    for market, by_day in buckets.items():
        series = [
            {
                "as_of": day,
                "score_sum": round(vals["score_sum"], 1),
                "action_sum": int(vals["action_sum"]),
                "n": int(vals["n"]),
            }
            for day, vals in sorted(by_day.items())
        ]
        out[market] = series
    return out


def fetch_index_series(
    market: str,
    *,
    start: str,
    end: str,
) -> dict[str, float]:
    """Daily close for KOSPI/KOSDAQ index keyed by YYYY-MM-DD."""
    ticker = INDEX_TICKER.get(market)
    if not ticker:
        return {}
    try:
        # yfinance end is exclusive-ish; pad one day
        end_excl = (pd.Timestamp(end) + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
        hist = yf.Ticker(ticker).history(start=start, end=end_excl, auto_adjust=True)
    except Exception as exc:
        logger.warning("index fetch failed %s: %s", ticker, exc)
        return {}
    if hist is None or hist.empty or "Close" not in hist.columns:
        return {}
    out: dict[str, float] = {}
    for idx, row in hist.iterrows():
        ts = pd.Timestamp(idx)
        if ts.tzinfo is not None:
            ts = ts.tz_convert(None)
        day = ts.strftime("%Y-%m-%d")
        val = float(row["Close"])
        if val == val and val > 0:
            out[day] = val
    return out


def build_market_pulse(
    *,
    start: str = "2025-01-01",
    end: str | None = None,
    signals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    end = end or datetime.now(KST).strftime("%Y-%m-%d")
    metrics = aggregate_daily_market_metrics(signals, start=start, end=end)
    indices = {
        market: fetch_index_series(market, start=start, end=end)
        for market in ("코스피", "코스닥")
    }
    return {
        "as_of": end,
        "start": start,
        "end": end,
        "metrics": metrics,
        "indices": indices,
    }


def render_dual_axis_svg(
    dates: list[str],
    primary: list[float | None],
    index_vals: list[float | None],
    *,
    title: str,
    primary_label: str,
    width: int = 640,
    height: int = 168,
    primary_color: str = "#0f766e",
    index_color: str = "#64748b",
    index_label: str = "지수",
    zero_line: bool = True,
) -> str:
    """Line chart: primary (left axis) + index (right axis)."""
    if len(dates) < 2:
        return ""
    n = len(dates)
    pad_l, pad_r, pad_t, pad_b = 44, 44, 22, 30
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    p_vals = [v for v in primary if v is not None and v == v]
    i_vals = [v for v in index_vals if v is not None and v == v]
    if not p_vals or not i_vals:
        return ""

    p_min, p_max = min(p_vals), max(p_vals)
    if zero_line:
        p_min = min(p_min, 0.0)
        p_max = max(p_max, 0.0)
    if p_max <= p_min:
        p_max = p_min + 1
    p_pad = (p_max - p_min) * 0.08
    p_min -= p_pad
    p_max += p_pad

    i_min, i_max = min(i_vals), max(i_vals)
    if i_max <= i_min:
        i_max = i_min + 1
    i_pad = (i_max - i_min) * 0.08
    i_min -= i_pad
    i_max += i_pad

    def x_at(i: int) -> float:
        return pad_l + i * plot_w / max(n - 1, 1)

    def y_primary(v: float) -> float:
        return pad_t + (p_max - v) / (p_max - p_min) * plot_h

    def y_index(v: float) -> float:
        return pad_t + (i_max - v) / (i_max - i_min) * plot_h

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" height="{height}" role="img" aria-label="{title}">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#f7fafb" rx="10"/>'
    ]

    # grid
    for g in range(1, 4):
        gy = pad_t + plot_h * g / 4
        parts.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" '
            f'stroke="#e2e8f0" stroke-width="1"/>'
        )

    if zero_line and p_min < 0 < p_max:
        zy = y_primary(0.0)
        parts.append(
            f'<line x1="{pad_l}" y1="{zy:.1f}" x2="{width - pad_r}" y2="{zy:.1f}" '
            f'stroke="#94a3b8" stroke-width="1.2"/>'
        )

    def polyline(vals: list[float | None], y_fn, color: str, width_px: float) -> None:
        pts: list[str] = []
        for i, v in enumerate(vals):
            if v is None or not (v == v):
                if len(pts) >= 2:
                    parts.append(
                        f'<polyline fill="none" stroke="{color}" stroke-width="{width_px}" '
                        f'points="{" ".join(pts)}"/>'
                    )
                pts = []
                continue
            pts.append(f"{x_at(i):.1f},{y_fn(v):.1f}")
        if len(pts) >= 2:
            parts.append(
                f'<polyline fill="none" stroke="{color}" stroke-width="{width_px}" '
                f'points="{" ".join(pts)}"/>'
            )

    polyline(index_vals, y_index, index_color, 1.5)
    polyline(primary, y_primary, primary_color, 1.8)

    d0 = dates[0][5:] if len(dates[0]) >= 10 else dates[0]
    d1 = dates[-1][5:] if len(dates[-1]) >= 10 else dates[-1]
    parts.append(
        '<g font-size="10" font-family="IBM Plex Sans KR, sans-serif">'
        f'<text x="{pad_l}" y="14" fill="#334155">{title}</text>'
        f'<text x="{width - pad_r}" y="14" text-anchor="end" fill="#64748b">'
        f"{d0} ~ {d1}</text>"
        f'<text x="{pad_l - 4}" y="{pad_t + 8}" text-anchor="end" fill="{primary_color}">'
        f"{p_max:,.0f}</text>"
        f'<text x="{pad_l - 4}" y="{height - pad_b + 4}" text-anchor="end" fill="{primary_color}">'
        f"{p_min:,.0f}</text>"
        f'<text x="{width - pad_r + 4}" y="{pad_t + 8}" fill="{index_color}">'
        f"{i_max:,.0f}</text>"
        f'<text x="{width - pad_r + 4}" y="{height - pad_b + 4}" fill="{index_color}">'
        f"{i_min:,.0f}</text>"
        "</g>"
    )
    append_svg_legend(
        parts,
        [
            (primary_label, primary_color, 1.8),
            (index_label, index_color, 1.5),
        ],
        width=width,
        y=height - 10,
    )
    parts.append("</svg>")
    return "".join(parts)


def render_market_pulse_html(payload: dict[str, Any]) -> str:
    """Build HTML block with 4 charts (2 metrics × 2 markets)."""
    metrics = payload.get("metrics") or {}
    indices = payload.get("indices") or {}
    cards: list[str] = []

    for market in ("코스피", "코스닥"):
        series = metrics.get(market) or []
        idx_map = indices.get(market) or {}
        if len(series) < 2:
            cards.append(
                f'<div class="pulse-card"><h3>{market}</h3>'
                f'<p class="muted">집계 데이터 부족</p></div>'
            )
            continue
        dates = [r["as_of"] for r in series]
        score_sum = [float(r["score_sum"]) for r in series]
        action_sum = [float(r["action_sum"]) for r in series]
        index_vals: list[float | None] = []
        for d in dates:
            v = idx_map.get(d)
            if v is None:
                # nearest prior
                prior = [k for k in idx_map if k <= d]
                v = idx_map[prior[-1]] if prior else None
            index_vals.append(v)

        svg_score = render_dual_axis_svg(
            dates,
            score_sum,
            index_vals,
            title=f"{market} · 종목 점수 합계 vs 지수",
            primary_label="점수합",
            primary_color="#0f766e",
            index_label=f"{market} 지수",
        )
        svg_action = render_dual_axis_svg(
            dates,
            action_sum,
            index_vals,
            title=f"{market} · 액션점수 합계 vs 지수",
            primary_label="액션합 (+1/0/−1)",
            primary_color="#c2410c",
            index_label=f"{market} 지수",
        )
        cards.append(
            f'<div class="pulse-card" data-market="{market}">'
            f"<h3>{market}</h3>"
            f'<div class="pulse-charts">'
            f'<div class="block chart pulse">{svg_score}</div>'
            f'<div class="block chart pulse">{svg_action}</div>'
            f"</div></div>"
        )

    start = payload.get("start", "")
    end = payload.get("end", "")
    return f"""
    <section class="market-pulse" aria-label="시장 점수 vs 지수">
      <div class="pulse-head">
        <div>
          <h2>시장 점수 vs 지수</h2>
          <p>워치리스트 종목의 일별 점수·액션을 시장별로 합산해 코스피/코스닥 지수와 비교합니다.<br>
            액션점수: 매수관심 +1 · 관망 0 · 주의 −1.<br>
            최근 구간: {start} ~ {end}</p>
        </div>
      </div>
      <div class="pulse-grid">
        {"".join(cards)}
      </div>
    </section>
    """


def write_market_pulse(
    *,
    start: str = "2025-01-01",
    end: str | None = None,
) -> Path:
    payload = build_market_pulse(start=start, end=end)
    out = backtest_dir() / "market_pulse.json"
    # indices dict values are plain floats — JSON ok; drop huge redundancy
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def load_or_build_market_pulse(
    *,
    start: str = "2025-01-01",
    end: str | None = None,
    rebuild: bool = False,
) -> dict[str, Any]:
    end = end or datetime.now(KST).strftime("%Y-%m-%d")
    path = backtest_dir() / "market_pulse.json"
    if not rebuild and path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("end") == end and payload.get("start") == start:
                return payload
        except (OSError, json.JSONDecodeError):
            pass
    payload = build_market_pulse(start=start, end=end)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
