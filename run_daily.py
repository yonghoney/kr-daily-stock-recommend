"""
VS Code / 로컬에서 바로 실행하는 일일 추천 진입점.

사용법:
  1. 이 파일을 연 뒤 Run Python File (▶) 또는 F5
  2. 또는 터미널:  python run_daily.py
  3. 결과: reports/daily/latest.html  (및 .txt / .md / .json)
             + reports/daily/YYYY-MM-DD/report.*
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytz

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

KST = pytz.timezone("Asia/Seoul")


def main() -> int:
    # Optional: --no-news
    no_news = "--no-news" in sys.argv
    from tradingagents.recommend.engine import run_daily_recommendations
    from tradingagents.recommend.universe import refresh_and_save_watchlist

    print(
        "워치리스트 갱신 중… "
        "(코스피/코스닥 각각: 우선주 제외 · 시총50 ∪ (시총50 제외) 1주 거래대금 상위20 진입)"
    )
    watchlist = refresh_and_save_watchlist(
        cap_top_n=50, amount_top_n=20, lookback_days=7
    )
    print(f"워치리스트 {len(watchlist)}종목으로 갱신 완료")

    print("일일 추천 생성 중… (LLM / 증권사 API 불필요)")
    recs, latest = run_daily_recommendations(include_news=not no_news)

    print()
    print(f"{'종목':<12} {'액션':<8} {'점수':>7} {'종가':>12} {'5일%':>8}")
    print("-" * 52)
    for r in sorted(recs, key=lambda x: -x.score):
        print(
            f"{r.name:<12} {r.action:<8} {r.score:>7.1f} "
            f"{r.price:>12,.0f} {r.ret_5d_pct:>+7.2f}"
        )
    print()
    as_of = datetime.now(KST).strftime("%Y-%m-%d")
    print(f"리포트(html): {latest}")
    print("같은 폴더: latest.txt / latest.md / latest.json")
    print(f"날짜별 보관: {latest.parent / as_of} (report.html / .txt / .md / .json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
