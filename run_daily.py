"""
VS Code / 로컬에서 바로 실행하는 일일 추천 진입점.

사용법:
  1. 이 파일을 연 뒤 Run Python File (▶) 또는 F5
  2. 또는 터미널:  python run_daily.py
  3. 결과: reports/daily/latest.md
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    # Optional: --no-news
    no_news = "--no-news" in sys.argv
    from tradingagents.recommend.engine import run_daily_recommendations

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
    print(f"리포트: {latest}")
    print(f"날짜별: {latest.parent / 'YYYY-MM-DD.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
