"""
Run score>60 buy / 주의 sell strategy backtest.

Uses signals.jsonl + Yahoo OHLCV.
Decision on day D uses previous session score only;
buy fill = Close[D], sell fill = Open[D].

Usage:
  python run_strategy_bt.py
  python run_strategy_bt.py --from 2025-01-01 --to 2026-07-16
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pytz

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

KST = pytz.timezone("Asia/Seoul")


def main() -> int:
    parser = argparse.ArgumentParser(description="score>60 / 주의 strategy backtest")
    parser.add_argument("--from", dest="start", default="2025-01-01")
    parser.add_argument(
        "--to", dest="end", default=datetime.now(KST).strftime("%Y-%m-%d")
    )
    parser.add_argument("--buy-score", type=float, default=60.0)
    parser.add_argument("--sell-score", type=float, default=-20.0)
    args = parser.parse_args()

    from tradingagents.dataflows.kr_symbols import normalize_kr_symbol
    from tradingagents.recommend.backtest import load_signals
    from tradingagents.recommend.engine import _fetch_history
    from tradingagents.recommend.strategy_bt import (
        run_score60_caution_strategy,
        write_strategy_report,
    )

    signals = [
        r
        for r in load_signals()
        if args.start <= str(r.get("as_of") or "") <= args.end
    ]
    if not signals:
        print("signals.jsonl 이 비어 있습니다. 먼저 run_backfill.py 를 실행하세요.")
        return 1

    tickers: dict[str, str] = {}
    for r in signals:
        t = str(r.get("ticker") or "")
        code = str(r.get("code") or "").zfill(6)
        if not t and code:
            t = normalize_kr_symbol(code)
        if t:
            tickers[t] = code

    print(f"시그널 {len(signals)}행 · 티커 {len(tickers)} · 시세 로딩…", flush=True)
    price_by_ticker: dict[str, object] = {}
    for i, (ticker, code) in enumerate(tickers.items(), 1):
        try:
            hist, sym = _fetch_history(ticker, period="5y")
            price_by_ticker[sym] = hist
            if sym != ticker:
                price_by_ticker[ticker] = hist
        except Exception as exc:
            print(f"  hist fail {ticker}: {exc}", flush=True)
        if i % 40 == 0:
            print(f"  {i}/{len(tickers)}", flush=True)

    summary, trades = run_score60_caution_strategy(
        signals,
        price_by_ticker,  # type: ignore[arg-type]
        buy_score=args.buy_score,
        sell_score=args.sell_score,
    )
    note = (
        f"기간 {args.start} ~ {args.end}. "
        f"D일 결정은 전 시그널일(D_prev) 점수만 사용. "
        f"매수: 점수>{args.buy_score:g} → D 종가 1주 / "
        f"매도: 점수≤{args.sell_score:g}(주의) → D 시가. "
        "이미 보유 중이면 추가 매수 없음."
    )
    path = write_strategy_report(
        summary, trades, as_of=args.end, note=note
    )
    wr = (
        f"{summary.win_rate * 100:.1f}%"
        if summary.win_rate is not None
        else "—"
    )
    print(
        f"청산 {summary.n_closed} · 미청산 {summary.n_open} · "
        f"승률 {wr} · 총손익 {summary.total_pnl:,.0f}원",
        flush=True,
    )
    print(f"리포트: {path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
