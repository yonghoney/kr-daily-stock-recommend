"""CLI: rule-based daily KR recommendations (no LLM API)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytz
import typer
from rich.console import Console
from rich.table import Table

from tradingagents.recommend.engine import run_daily_recommendations

console = Console()
KST = pytz.timezone("Asia/Seoul")


def run_daily(
    *,
    no_news: bool = False,
    output_dir: Path | None = None,
) -> int:
    from tradingagents.recommend.universe import refresh_and_save_watchlist

    console.print(
        "[bold]워치리스트 갱신 중…[/bold] "
        "(코스피/코스닥 각각: 우선주 제외 · 시총50 ∪ (시총50 제외) 1주 거래대금 상위20 진입)"
    )
    watchlist = refresh_and_save_watchlist(
        cap_top_n=50, amount_top_n=20, lookback_days=7
    )
    console.print(f"워치리스트 [cyan]{len(watchlist)}[/cyan]종목으로 갱신 완료")

    console.print("[bold]일일 추천 생성 중…[/bold] (LLM API 불필요)")
    recs, latest = run_daily_recommendations(
        include_news=not no_news,
        output_dir=output_dir,
    )
    table = Table(title="일일 추천 요약")
    table.add_column("종목")
    table.add_column("액션")
    table.add_column("점수", justify="right")
    table.add_column("종가", justify="right")
    table.add_column("5일%", justify="right")
    for r in sorted(recs, key=lambda x: -x.score):
        table.add_row(
            r.name,
            r.action,
            f"{r.score}",
            f"{r.price:,.0f}",
            f"{r.ret_5d_pct:+.2f}",
        )
    console.print(table)
    as_of = datetime.now(KST).strftime("%Y-%m-%d")
    console.print(f"\n리포트: [green]{latest}[/green]")
    console.print("같은 폴더: latest.html / latest.txt / latest.md / latest.json")
    console.print(
        f"날짜별 보관: [cyan]{latest.parent / as_of}[/cyan] "
        "(report.html / .txt / .md / .json)"
    )
    return 0


def register(app: typer.Typer) -> None:
    @app.command("daily-recommend")
    def daily_recommend(
        no_news: bool = typer.Option(
            False,
            "--no-news",
            help="뉴스 헤드라인 생략 (더 빠름)",
        ),
        output_dir: Path | None = typer.Option(
            None,
            "--output-dir",
            "-o",
            help="리포트 출력 폴더 (기본: reports/daily)",
        ),
    ):
        """워치리스트 기준 일일 추천·이유 갱신 (API 키 불필요)."""
        code = run_daily(no_news=no_news, output_dir=output_dir)
        raise typer.Exit(code)
