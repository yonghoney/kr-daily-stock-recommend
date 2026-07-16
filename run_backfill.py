"""
Backfill daily PIT recommendations (tech + flow only) from a start date.

Each trading day rebuilds the watchlist from that day's KRX listing cache
(Marcap top-50 ∪ weekly Amount top-20 outside cap, per market) — same rule as
run_daily.py — without overwriting config/kr_universe.yaml.

Usage:
  python run_backfill.py --from 2025-01-01
  python run_backfill.py --from 2026-06-01 --to 2026-07-16
  python run_backfill.py --from 2025-01-01 --force   # recompute even if report.json exists
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pytz

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

KST = pytz.timezone("Asia/Seoul")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="PIT daily backfill with per-day watchlist refresh (no news)"
    )
    parser.add_argument("--from", dest="start", default="2026-06-01")
    parser.add_argument(
        "--to",
        dest="end",
        default=datetime.now(KST).strftime("%Y-%m-%d"),
    )
    parser.add_argument(
        "--limit-days",
        type=int,
        default=0,
        help="If >0, only process first N trading days (smoke test)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute days that already have report.json",
    )
    args = parser.parse_args()

    from tradingagents.dataflows.kr_symbols import normalize_kr_symbol
    from tradingagents.recommend.backtest import (
        compute_bucket_stats,
        rebuild_signals_from_daily_reports,
        signals_path,
        trading_days,
        write_stats,
    )
    from tradingagents.recommend.engine import _fetch_history, analyze_ticker
    from tradingagents.recommend.paths import dated_report_dir
    from tradingagents.recommend.universe import build_watchlist

    days = trading_days(args.start, args.end)
    if args.limit_days > 0:
        days = days[: args.limit_days]
    if not days:
        print("처리할 거래일이 없습니다.")
        return 1

    print(
        f"백필 {days[0]} ~ {days[-1]} ({len(days)}일) · "
        "거래일마다 PIT 워치리스트 갱신",
        flush=True,
    )

    hist_cache: dict[str, object] = {}
    ticker_by_code: dict[str, str] = {}
    out = ROOT / "reports" / "daily"
    out.mkdir(parents=True, exist_ok=True)

    done = skip = fail_wl = 0

    def ensure_hist(code: str, ticker: str) -> str | None:
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
            print(f"  hist fail {code}: {exc}", flush=True)
            ticker_by_code[code] = symbol
            hist_cache[symbol] = None
            return symbol

    for di, day in enumerate(days, 1):
        dated = dated_report_dir(day, output_dir=out)
        report_path = dated / "report.json"
        legacy_report = out / day / "report.json"
        if (
            (report_path.exists() or legacy_report.exists())
            and not args.force
        ):
            skip += 1
            if di % 20 == 0 or di == 1:
                print(f"[{di}/{len(days)}] {day} skip (exists)", flush=True)
            continue

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
            fail_wl += 1
            print(f"[{di}/{len(days)}] {day} watchlist fail: {exc}", flush=True)
            continue

        print(f"[{di}/{len(days)}] {day} · 워치리스트 {len(watchlist)}종목", flush=True)
        recs = []
        for w in watchlist:
            symbol = ensure_hist(w["code"], w.get("ticker") or w["code"])
            hist = hist_cache.get(symbol) if symbol else None
            recs.append(
                analyze_ticker(
                    w["code"],
                    w["name"],
                    symbol or normalize_kr_symbol(w.get("ticker") or w["code"]),
                    include_news=False,
                    as_of=day,
                    hist=hist,
                    include_chart=False,
                    include_fundamentals=False,
                )
            )

        dated.mkdir(parents=True, exist_ok=True)
        payload = {
            "as_of": day,
            "mode": "backfill_pit_watchlist",
            "watchlist_count": len(watchlist),
            "recommendations": [
                r.to_dict() for r in sorted(recs, key=lambda x: -x.score)
            ],
        }
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        buys = sum(1 for r in recs if r.action == "매수관심")
        cautions = sum(1 for r in recs if r.action == "주의")
        print(f"  매수관심 {buys} · 주의 {cautions}", flush=True)
        done += 1

    print(
        f"완료 {done}일 계산 · 기존 skip {skip}일 · 워치리스트 실패 {fail_wl}일",
        flush=True,
    )
    print("signals.jsonl 재구축 중…", flush=True)
    sp = signals_path()
    if sp.exists():
        sp.unlink()
    n_sig = rebuild_signals_from_daily_reports(start=args.start, end=args.end)
    print(f"시그널 행 {n_sig}건", flush=True)

    print("점수대별 선수익 통계 계산 중…", flush=True)
    from tradingagents.recommend.backtest import load_signals

    signals = load_signals()
    # Fetch any tickers that appeared in signals but not yet cached
    for row in signals:
        code = str(row.get("code") or "").zfill(6)
        ticker = str(row.get("ticker") or code)
        if code and code not in ticker_by_code:
            ensure_hist(code, ticker)

    price_by_ticker = {t: h for t, h in hist_cache.items() if h is not None}
    for row in signals:
        t = str(row.get("ticker") or "")
        if t and t not in price_by_ticker:
            for k, h in hist_cache.items():
                if h is not None and k.startswith(str(row.get("code", "")).zfill(6)):
                    price_by_ticker[t] = h
                    break

    stats = compute_bucket_stats(signals, price_by_ticker)
    stats_path = write_stats(
        stats,
        as_of=days[-1],
        note=(
            f"백필 기간 {days[0]} ~ {days[-1]} · "
            "거래일마다 PIT 워치리스트 · 시세·기술·수급(가능 시)"
        ),
    )
    print(f"통계: {stats_path}", flush=True)
    print(f"시그널 로그: {sp}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
