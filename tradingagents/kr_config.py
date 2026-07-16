"""Korea-market defaults layered on top of DEFAULT_CONFIG."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

from tradingagents.default_config import DEFAULT_CONFIG

KR_GLOBAL_NEWS_QUERIES = [
    "코스피 증시 전망",
    "한국은행 기준금리 물가",
    "반도체 수출 한국 경제",
    "원달러 환율 외국인 수급",
    "금융위원회 공매도 증시 규제",
]


def load_kr_universe() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    path = root / "config" / "kr_universe.yaml"
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def apply_kr_defaults(config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a config copy tuned for KRX analysis + paper execution."""
    cfg = copy.deepcopy(config or DEFAULT_CONFIG)

    cfg["output_language"] = os.environ.get(
        "TRADINGAGENTS_OUTPUT_LANGUAGE", "Korean"
    )
    cfg["market"] = "kr"
    cfg.setdefault("benchmark_map", {})
    cfg["benchmark_map"][".KS"] = "^KS11"
    cfg["benchmark_map"][".KQ"] = "^KQ11"
    if not cfg.get("benchmark_ticker"):
        cfg["benchmark_ticker"] = os.environ.get(
            "TRADINGAGENTS_BENCHMARK_TICKER", "^KS11"
        )

    vendors = dict(cfg.get("data_vendors") or {})
    vendors["news_data"] = os.environ.get(
        "TRADINGAGENTS_NEWS_VENDOR", "korean_news,yfinance"
    )
    cfg["data_vendors"] = vendors

    cfg["global_news_queries"] = list(KR_GLOBAL_NEWS_QUERIES)

    # Recommend-first: broker execution off by default
    universe = load_kr_universe()
    risk = universe.get("risk") or {}
    cfg["execution_enabled"] = _env_bool("EXECUTION_ENABLED", False)
    cfg["trading_mode"] = os.environ.get("TRADING_MODE", "paper").lower()
    cfg["broker"] = os.environ.get("BROKER", "paper").lower()
    cfg["max_order_notional_krw"] = int(
        os.environ.get(
            "MAX_ORDER_NOTIONAL_KRW",
            risk.get("max_order_notional_krw", 1_000_000),
        )
    )
    cfg["max_daily_notional_krw"] = int(
        os.environ.get(
            "MAX_DAILY_NOTIONAL_KRW",
            risk.get("max_daily_notional_krw", 5_000_000),
        )
    )
    cfg["max_positions"] = int(
        os.environ.get("MAX_POSITIONS", risk.get("max_positions", 5))
    )
    cfg["order_cooldown_seconds"] = int(
        os.environ.get(
            "ORDER_COOLDOWN_SECONDS",
            risk.get("order_cooldown_seconds", 60),
        )
    )
    cfg["i_accept_live_trading"] = _env_bool("I_ACCEPT_LIVE_TRADING", False)
    cfg["paper_initial_cash_krw"] = int(
        os.environ.get("PAPER_INITIAL_CASH_KRW", 10_000_000)
    )
    cfg["kr_session_only"] = _env_bool("KR_SESSION_ONLY", True)

    return cfg


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("true", "1", "yes", "on")
