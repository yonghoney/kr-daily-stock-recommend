"""
VS Code / 로컬에서 바로 실행하는 일일 추천 진입점.

기본: **마지막 확정 세션 종가까지**의 데이터만 사용합니다.
- 평일 장 종료(15:30 KST) 이후 → 당일 종가 기준 (폴더: 당일)
- 장중·주말 → 직전 거래일 종가 기준 (폴더: 직전 거래일)

누락 보완: 마지막 실행 이후 빠진 거래일 리포트(2025-01-01~)를 자동 생성합니다.
상태 파일: reports/daily/.run_state.json

사용법:
  1. 이 파일을 연 뒤 Run Python File (▶) 또는 F5
  2. 또는 터미널:  python run_daily.py
  3. 결과: reports/daily/latest.html  (및 .txt / .md / .json)
             + reports/daily/YYYY/MM/DD/report.*

옵션:
  python run_daily.py --no-news
  python run_daily.py --no-gap-fill
  python run_daily.py --as-of 2026-07-10 --no-news
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _arg_value(flag: str) -> str | None:
    if flag not in sys.argv:
        return None
    i = sys.argv.index(flag)
    if i + 1 >= len(sys.argv):
        return None
    return sys.argv[i + 1]


def main() -> int:
    no_news = "--no-news" in sys.argv
    no_gap_fill = "--no-gap-fill" in sys.argv
    explicit_as_of = _arg_value("--as-of")
    from tradingagents.recommend.engine import run_daily_recommendations
    from tradingagents.recommend.gap_fill import fill_gaps_before_daily, save_run_state
    from tradingagents.recommend.session import analysis_as_of_date
    from tradingagents.recommend.universe import refresh_and_save_watchlist

    if explicit_as_of:
        as_of = explicit_as_of
        update_latest = False
        include_news = False
        print(f"PIT 모드 as_of={as_of} · 워치리스트는 현재 yaml 사용 (갱신·누락 보완 생략)")
    else:
        as_of = analysis_as_of_date()
        update_latest = True
        include_news = not no_news
        print(f"기준일 as_of={as_of} (마지막 확정 세션 종가까지 · 폴더명=기준일)")

        if not no_gap_fill:
            filled = fill_gaps_before_daily(as_of)
            if filled:
                print(f"누락 보완 완료: {len(filled)}일 ({filled[0]} ~ {filled[-1]})", flush=True)
            else:
                print("누락 리포트 없음 (마지막 실행 이후)", flush=True)
        else:
            print("누락 보완 생략 (--no-gap-fill)", flush=True)

        print(
            "워치리스트 갱신 중… "
            "(코스피/코스닥 각각: 우선주 제외 · 시총50 ∪ (시총50 제외) 1주 거래대금 상위20 진입)"
        )
        watchlist = refresh_and_save_watchlist(
            cap_top_n=50, amount_top_n=20, lookback_days=7
        )
        print(f"워치리스트 {len(watchlist)}종목으로 갱신 완료")

    print("일일 추천 생성 중… (LLM / 증권사 API 불필요)")
    recs, latest = run_daily_recommendations(
        include_news=include_news,
        as_of=as_of,
        update_latest=update_latest,
    )

    if update_latest:
        save_run_state(last_cover_to=as_of)

    print()
    print(f"{'종목':<12} {'액션':<8} {'점수':>7} {'종가':>12} {'5일%':>8}")
    print("-" * 52)
    for r in sorted(recs, key=lambda x: -x.score):
        print(
            f"{r.name:<12} {r.action:<8} {r.score:>7.1f} "
            f"{r.price:>12,.0f} {r.ret_5d_pct:>+7.2f}"
        )
    print()
    print(f"리포트(html): {latest}")
    if update_latest:
        print("같은 폴더: latest.txt / latest.md / latest.json")
    from tradingagents.recommend.paths import dated_report_dir

    print(f"날짜별 보관: {dated_report_dir(as_of)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
