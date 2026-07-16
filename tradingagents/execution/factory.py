"""Create a BrokerAdapter from config / env."""

from __future__ import annotations

import os
from typing import Any

from tradingagents.execution.base import BrokerAdapter
from tradingagents.execution.kis_broker import KisBroker
from tradingagents.execution.mirae_stub import MiraeStubBroker
from tradingagents.execution.paper_broker import PaperBroker


def create_broker(config: dict[str, Any] | None = None) -> BrokerAdapter:
    cfg = config or {}
    name = (cfg.get("broker") or os.environ.get("BROKER") or "paper").lower()
    mode = (cfg.get("trading_mode") or os.environ.get("TRADING_MODE") or "paper").lower()

    if name == "mirae":
        return MiraeStubBroker()

    if name == "kis":
        # kis + trading_mode=paper → KIS 모의투자 endpoint
        # kis + trading_mode=live → real endpoint (requires I_ACCEPT_LIVE_TRADING)
        paper = mode != "live"
        return KisBroker(paper=paper)

    if name in {"paper", "local"}:
        return PaperBroker(
            initial_cash=float(cfg.get("paper_initial_cash_krw") or 10_000_000),
        )

    raise ValueError(
        f"Unknown broker={name!r}. Use paper | kis | mirae."
    )
