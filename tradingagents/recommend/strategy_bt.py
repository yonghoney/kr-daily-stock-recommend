"""Strategy backtest: buy score>60 (1 share @ close), sell on 주의 (@ next open).

Decision on calendar day D uses only the previous scored session's score
(as_of = D_prev), so there is no same-day lookahead for the open/close fills.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytz

from tradingagents.recommend.backtest import backtest_dir, load_signals

logger = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")

BUY_SCORE = 60.0  # buy when previous score > this
SELL_SCORE = -20.0  # sell when previous score <= this (주의)


@dataclass
class Trade:
    code: str
    name: str
    ticker: str
    entry_as_of: str  # score day used for entry decision (D_prev)
    entry_day: str  # fill day (close)
    entry_price: float
    entry_score: float
    exit_as_of: str | None
    exit_day: str | None
    exit_price: float | None
    exit_score: float | None
    pnl: float | None  # KRW for 1 share
    pnl_pct: float | None
    status: str  # closed | open


@dataclass
class StrategySummary:
    buy_threshold: float
    sell_threshold: float
    n_trades: int
    n_closed: int
    n_open: int
    n_wins: int
    n_losses: int
    win_rate: float | None
    total_pnl: float
    avg_pnl: float | None
    avg_pnl_pct: float | None
    median_hold_days: float | None


def _norm_ohlc(hist: pd.DataFrame) -> pd.DataFrame | None:
    if hist is None or getattr(hist, "empty", True):
        return None
    df = hist.copy()
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert(None)
    df.index = pd.DatetimeIndex(idx).normalize()
    df = df[~df.index.duplicated(keep="last")].sort_index()
    for col in ("Open", "Close"):
        if col not in df.columns:
            return None
    return df


def _px(hist: pd.DataFrame, day: str, col: str) -> float | None:
    ts = pd.Timestamp(day).normalize()
    if ts not in hist.index:
        return None
    val = float(hist.at[ts, col])
    if val != val or val <= 0:
        return None
    return val


def _hold_calendar_days(entry_day: str, exit_day: str) -> int:
    return (pd.Timestamp(exit_day) - pd.Timestamp(entry_day)).days


def run_score60_caution_strategy(
    signals: list[dict[str, Any]] | None = None,
    price_by_ticker: dict[str, pd.DataFrame] | None = None,
    *,
    buy_score: float = BUY_SCORE,
    sell_score: float = SELL_SCORE,
) -> tuple[StrategySummary, list[Trade]]:
    """Simulate 1-share positions: buy if prev score > buy_score, sell if prev ≤ sell_score."""
    rows = signals if signals is not None else load_signals()
    by_code: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        code = str(r.get("code") or "").zfill(6)
        day = str(r.get("as_of") or "")
        if not code or not day:
            continue
        by_code[code].append(r)

    prices = price_by_ticker or {}
    trades: list[Trade] = []

    for code, items in sorted(by_code.items()):
        items = sorted(items, key=lambda x: str(x.get("as_of") or ""))
        # Deduplicate as_of (keep last)
        day_map: dict[str, dict[str, Any]] = {}
        for r in items:
            day_map[str(r["as_of"])] = r
        days = sorted(day_map)
        if len(days) < 2:
            continue

        ticker = str(day_map[days[0]].get("ticker") or f"{code}.KS")
        name = str(day_map[days[0]].get("name") or code)
        hist = _norm_ohlc(prices.get(ticker))
        if hist is None:
            # try alternate suffix
            alt = (
                ticker[:-3] + (".KS" if ticker.endswith(".KQ") else ".KQ")
                if ticker.endswith((".KS", ".KQ"))
                else None
            )
            if alt:
                hist = _norm_ohlc(prices.get(alt))
                if hist is not None:
                    ticker = alt
        if hist is None:
            continue

        holding: Trade | None = None
        for i in range(1, len(days)):
            day = days[i]
            prev = days[i - 1]
            prev_row = day_map[prev]
            try:
                score_prev = float(prev_row.get("score") or 0)
            except (TypeError, ValueError):
                continue
            name = str(prev_row.get("name") or name)
            ticker = str(prev_row.get("ticker") or ticker)

            if holding is not None and score_prev <= sell_score:
                open_px = _px(hist, day, "Open")
                if open_px is None:
                    continue
                holding.exit_as_of = prev
                holding.exit_day = day
                holding.exit_price = open_px
                holding.exit_score = score_prev
                holding.pnl = open_px - holding.entry_price
                holding.pnl_pct = holding.pnl / holding.entry_price if holding.entry_price else None
                holding.status = "closed"
                trades.append(holding)
                holding = None
                continue

            if holding is None and score_prev > buy_score:
                close_px = _px(hist, day, "Close")
                if close_px is None:
                    continue
                holding = Trade(
                    code=code,
                    name=name,
                    ticker=ticker,
                    entry_as_of=prev,
                    entry_day=day,
                    entry_price=close_px,
                    entry_score=score_prev,
                    exit_as_of=None,
                    exit_day=None,
                    exit_price=None,
                    exit_score=None,
                    pnl=None,
                    pnl_pct=None,
                    status="open",
                )

        if holding is not None:
            # Mark open at last available close
            last_day = days[-1]
            mark = _px(hist, last_day, "Close")
            if mark is not None:
                holding.exit_as_of = last_day
                holding.exit_day = last_day
                holding.exit_price = mark
                holding.exit_score = float(day_map[last_day].get("score") or 0)
                holding.pnl = mark - holding.entry_price
                holding.pnl_pct = (
                    holding.pnl / holding.entry_price if holding.entry_price else None
                )
            trades.append(holding)

    closed = [t for t in trades if t.status == "closed"]
    open_tr = [t for t in trades if t.status == "open"]
    pnls = [float(t.pnl) for t in closed if t.pnl is not None]
    pcts = [float(t.pnl_pct) for t in closed if t.pnl_pct is not None]
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    hold_days = [
        _hold_calendar_days(t.entry_day, t.exit_day)
        for t in closed
        if t.exit_day
    ]
    summary = StrategySummary(
        buy_threshold=buy_score,
        sell_threshold=sell_score,
        n_trades=len(trades),
        n_closed=len(closed),
        n_open=len(open_tr),
        n_wins=wins,
        n_losses=losses,
        win_rate=(wins / len(pnls)) if pnls else None,
        total_pnl=sum(pnls) if pnls else 0.0,
        avg_pnl=(sum(pnls) / len(pnls)) if pnls else None,
        avg_pnl_pct=(sum(pcts) / len(pcts)) if pcts else None,
        median_hold_days=(
            float(pd.Series(hold_days).median()) if hold_days else None
        ),
    )
    return summary, trades


def render_strategy_html(
    summary: StrategySummary,
    trades: list[Trade],
    *,
    as_of: str,
    note: str = "",
) -> str:
    def _pct(v: float | None) -> str:
        if v is None:
            return "—"
        return f"{v * 100:+.2f}%"

    def _won(v: float | None) -> str:
        if v is None:
            return "—"
        return f"{v:,.0f}"

    wr = "—" if summary.win_rate is None else f"{summary.win_rate * 100:.1f}%"
    rows = []
    for t in sorted(
        trades,
        key=lambda x: (x.entry_day, x.code),
        reverse=True,
    )[:500]:
        cls = ""
        if t.pnl is not None:
            cls = "pos" if t.pnl > 0 else "neg" if t.pnl < 0 else ""
        rows.append(
            "<tr>"
            f"<td>{t.code}</td><td>{t.name}</td>"
            f"<td>{t.entry_day}</td><td>{t.entry_score:+.1f}</td><td>{t.entry_price:,.0f}</td>"
            f"<td>{t.exit_day or '—'}</td>"
            f"<td>{('+' if (t.exit_score or 0) > 0 else '') + (f'{t.exit_score:.1f}' if t.exit_score is not None else '—')}</td>"
            f"<td>{_won(t.exit_price)}</td>"
            f"<td class='{cls}'>{_won(t.pnl)}</td>"
            f"<td class='{cls}'>{_pct(t.pnl_pct)}</td>"
            f"<td>{t.status}</td>"
            "</tr>"
        )
    note_html = f"<p class='note'>{note}</p>" if note else ""
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <title>전략 백테스트 score&gt;{summary.buy_threshold:.0f} → 주의 매도</title>
  <style>
    body {{ font-family: "Segoe UI", sans-serif; margin: 2rem; color: #14201c; background: #f7f4ec; }}
    h1 {{ font-size: 1.4rem; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 0.75rem; margin: 1rem 0 1.5rem; }}
    .card {{ background: #fff; border-radius: 12px; padding: 0.85rem 1rem; border: 1px solid #ddd; }}
    .card b {{ display: block; font-size: 1.2rem; margin-top: 0.25rem; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; font-size: 0.88rem; }}
    th, td {{ border: 1px solid #e2e8f0; padding: 0.4rem 0.5rem; text-align: right; }}
    th:nth-child(1), td:nth-child(1), th:nth-child(2), td:nth-child(2), th:nth-child(11), td:nth-child(11)
      {{ text-align: left; }}
    th {{ background: #eef2f0; }}
    .pos {{ color: #0b7a63; }} .neg {{ color: #c2410c; }}
    .note {{ color: #5c6f67; font-size: 0.92rem; max-width: 52rem; }}
  </style>
</head>
<body>
  <h1>전략: 전일 점수 &gt; {summary.buy_threshold:.0f} 매수(1주·종가)<br>
  → 전일 주의(≤{summary.sell_threshold:.0f}) 매도(시가)</h1>
  <p>집계 기준일: {as_of}</p>
  {note_html}
  <div class="cards">
    <div class="card">거래 수<b>{summary.n_trades}</b></div>
    <div class="card">청산<b>{summary.n_closed}</b></div>
    <div class="card">미청산<b>{summary.n_open}</b></div>
    <div class="card">승률<b>{wr}</b></div>
    <div class="card">총손익(원)<b>{summary.total_pnl:,.0f}</b></div>
    <div class="card">평균손익(원)<b>{_won(summary.avg_pnl)}</b></div>
    <div class="card">평균수익률<b>{_pct(summary.avg_pnl_pct)}</b></div>
    <div class="card">보유일(중앙)<b>{summary.median_hold_days if summary.median_hold_days is not None else '—'}</b></div>
  </div>
  <table>
    <thead>
      <tr>
        <th>코드</th><th>종목</th>
        <th>매수일</th><th>진입점수</th><th>매수가(종가)</th>
        <th>매도일</th><th>청산점수</th><th>매도가(시가)</th>
        <th>손익</th><th>수익률</th><th>상태</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows) or '<tr><td colspan="11">거래 없음</td></tr>'}
    </tbody>
  </table>
  <p class="note">수수료·세금·슬리피지는 반영하지 않았습니다.<br>
  미청산은 마지막 시그널일 종가로 평가합니다.</p>
</body>
</html>
"""


def write_strategy_report(
    summary: StrategySummary,
    trades: list[Trade],
    *,
    as_of: str | None = None,
    note: str = "",
) -> Path:
    as_of = as_of or datetime.now(KST).strftime("%Y-%m-%d")
    out_dir = backtest_dir()
    payload = {
        "as_of": as_of,
        "note": note,
        "summary": asdict(summary),
        "trades": [asdict(t) for t in trades],
    }
    json_path = out_dir / "strategy_score60.json"
    html_path = out_dir / "strategy_score60.html"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(
        render_strategy_html(summary, trades, as_of=as_of, note=note),
        encoding="utf-8",
    )
    return html_path
