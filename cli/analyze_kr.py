"""Non-interactive Korean equity analysis + optional paper/KIS execution."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from tradingagents.dataflows.kr_symbols import normalize_kr_symbol
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.kr_config import apply_kr_defaults
from tradingagents.reporting import write_report_tree

console = Console()


def run_analyze_kr(
    ticker: str,
    trade_date: str | None = None,
    mode: str = "paper",
    broker: str = "paper",
    execute: bool = False,
    debug: bool = False,
) -> int:
    """Run KR LLM analysis; return process exit code.

    Default is recommend-only (no broker orders). Requires an LLM API key.
    For API-free daily lists use ``tradingagents daily-recommend`` instead.
    """
    load_dotenv()

    if trade_date in (None, "", "today"):
        trade_date = datetime.now().strftime("%Y-%m-%d")

    symbol = normalize_kr_symbol(ticker)
    config = apply_kr_defaults()
    config["trading_mode"] = mode.lower()
    config["broker"] = broker.lower()
    # Recommend-first product: execution off unless explicitly requested.
    config["execution_enabled"] = bool(execute)

    if mode.lower() == "live":
        if not config.get("i_accept_live_trading"):
            console.print(
                "[red]TRADING_MODE=live requires I_ACCEPT_LIVE_TRADING=true in .env[/red]"
            )
            return 2
        if broker.lower() != "kis":
            console.print("[red]Live mode currently requires --broker kis[/red]")
            return 2

    console.print(
        Panel.fit(
            f"[bold]KR analyze[/bold]\n"
            f"ticker={symbol}\n"
            f"date={trade_date}\n"
            f"mode={config['trading_mode']} broker={config['broker']}\n"
            f"execute={execute} language={config.get('output_language')}",
            title="TradingAgents-KR",
        )
    )

    ta = TradingAgentsGraph(debug=debug, config=config)
    final_state, decision = ta.propagate(symbol, trade_date)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = (
        Path(config["results_dir"]) / "reports" / f"kr_{symbol.replace('.', '_')}_{stamp}"
    )
    write_report_tree(final_state, symbol, report_dir)

    console.print(f"\n[bold green]Decision:[/bold green] {decision}")
    exec_info = final_state.get("execution_result")
    if exec_info:
        console.print(
            f"[bold]Execution:[/bold] executed={exec_info.get('executed')} "
            f"skipped={exec_info.get('skipped')} "
            f"msg={exec_info.get('message')} "
            f"order_id={exec_info.get('order_id')}"
        )
    console.print(f"Reports → {report_dir}")
    return 0


def register(app: typer.Typer) -> None:
    @app.command("analyze-kr")
    def analyze_kr(
        ticker: str = typer.Argument(..., help="KRX code e.g. 005930 or 005930.KS"),
        date: str = typer.Option(
            "today",
            "--date",
            "-d",
            help="Analysis date YYYY-MM-DD or 'today'",
        ),
        mode: str = typer.Option(
            None,
            "--mode",
            "-m",
            help="paper | live (default: TRADING_MODE or paper)",
        ),
        broker: str = typer.Option(
            None,
            "--broker",
            "-b",
            help="paper | kis | mirae (default: BROKER or paper)",
        ),
        execute: bool = typer.Option(
            False,
            "--execute/--no-execute",
            help="(비권장) 브로커 주문 — 기본은 추천만. 일상 사용은 daily-recommend",
        ),
        debug: bool = typer.Option(False, "--debug", help="Stream agent messages"),
    ):
        """Analyze a Korean stock and optionally place a paper/KIS order."""
        resolved_mode = mode or os.environ.get("TRADING_MODE", "paper")
        resolved_broker = broker or os.environ.get("BROKER", "paper")
        code = run_analyze_kr(
            ticker=ticker,
            trade_date=date,
            mode=resolved_mode,
            broker=resolved_broker,
            execute=execute,
            debug=debug,
        )
        raise typer.Exit(code)
