"""CLI: rule-based daily KR recommendations (no LLM API)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from tradingagents.recommend.engine import run_daily_recommendations

console = Console()


def run_daily(
    *,
    no_news: bool = False,
    output_dir: Path | None = None,
) -> int:
    from tradingagents.recommend.universe import refresh_and_save_watchlist

    console.print(
        "[bold]워치리스트 갱신 중…[/bold] (거래대금 상위 20 + 시가총액 상위 20)"
    )
    watchlist = refresh_and_save_watchlist(top_n=20)
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
    console.print(f"\n리포트: [green]{latest}[/green]")
    console.print("같은 폴더: latest.md / latest.json / latest.txt / YYYY-MM-DD.*")
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
