"""Map Portfolio Manager ratings to broker orders with risk guards."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import yfinance as yf

from tradingagents.agents.utils.rating import parse_rating
from tradingagents.dataflows.kr_symbols import normalize_kr_symbol
from tradingagents.execution.audit import OrderAuditLog
from tradingagents.execution.base import BrokerAdapter
from tradingagents.execution.factory import create_broker
from tradingagents.execution.risk import RiskGuard, RiskLimits
from tradingagents.execution.types import OrderRequest, OrderResult, OrderType, Side

logger = logging.getLogger(__name__)

_BUY_RATINGS = {"Buy", "Overweight"}
_SELL_RATINGS = {"Sell", "Underweight"}

_SIZING_PCT_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*%\s*(?:of\s+)?(?:portfolio|cash|자산|포트폴리오)?",
    re.IGNORECASE,
)


@dataclass
class ExecutionResult:
    executed: bool
    skipped: bool
    rating: str
    message: str
    order_result: OrderResult | None = None
    details: dict[str, Any] = field(default_factory=dict)


class ExecutionGateway:
    def __init__(
        self,
        config: dict[str, Any],
        broker: BrokerAdapter | None = None,
        audit: OrderAuditLog | None = None,
    ):
        self.config = config
        self.broker = broker or create_broker(config)
        self.audit = audit or OrderAuditLog(
            config.get("order_audit_path"),
        )
        self.guard = RiskGuard(
            RiskLimits(
                max_order_notional_krw=float(config.get("max_order_notional_krw", 1_000_000)),
                max_daily_notional_krw=float(config.get("max_daily_notional_krw", 5_000_000)),
                max_positions=int(config.get("max_positions", 5)),
                order_cooldown_seconds=int(config.get("order_cooldown_seconds", 60)),
                session_only=bool(config.get("kr_session_only", True)),
                trading_mode=str(config.get("trading_mode", "paper")),
                i_accept_live_trading=bool(config.get("i_accept_live_trading", False)),
            )
        )

    def execute_from_decision(
        self,
        ticker: str,
        final_trade_decision: str,
        trader_plan: str | None = None,
    ) -> ExecutionResult:
        if not self.config.get("execution_enabled", False):
            return ExecutionResult(
                False, True, "Hold", "execution_enabled=false; order skipped"
            )

        rating = parse_rating(final_trade_decision or "")
        symbol = normalize_kr_symbol(ticker)

        if rating == "Hold":
            msg = "Rating Hold — no order"
            self.audit.append(
                {"event": "skip", "ticker": symbol, "rating": rating, "reason": msg}
            )
            return ExecutionResult(False, True, rating, msg)

        side = Side.BUY if rating in _BUY_RATINGS else Side.SELL if rating in _SELL_RATINGS else None
        if side is None:
            msg = f"Unhandled rating {rating}"
            return ExecutionResult(False, True, rating, msg)

        try:
            price = self._last_price(symbol)
        except Exception as exc:
            msg = f"Price lookup failed: {exc}"
            self.audit.append(
                {"event": "error", "ticker": symbol, "rating": rating, "reason": msg}
            )
            return ExecutionResult(False, True, rating, msg)

        try:
            balance = self.broker.get_balance()
            positions = self.broker.get_positions()
        except Exception as exc:
            msg = f"Broker account inquiry failed: {exc}"
            self.audit.append(
                {"event": "error", "ticker": symbol, "rating": rating, "reason": msg}
            )
            return ExecutionResult(False, True, rating, msg)

        qty = self._size_quantity(
            side=side,
            symbol=symbol,
            price=price,
            cash=balance.cash,
            positions=positions,
            trader_plan=trader_plan or "",
            decision_text=final_trade_decision or "",
        )
        if qty <= 0:
            msg = "Computed quantity is 0 — skip"
            self.audit.append(
                {"event": "skip", "ticker": symbol, "rating": rating, "reason": msg}
            )
            return ExecutionResult(False, True, rating, msg)

        notional = qty * price
        held = {normalize_kr_symbol(p.symbol): p for p in positions}
        is_new = side == Side.BUY and symbol not in held
        now_ts = time.time()

        check = self.guard.check_order(
            notional=notional,
            side=side.value,
            open_positions=len(held),
            is_new_position=is_new,
            now_ts=now_ts,
        )
        if not check.ok:
            self.audit.append(
                {
                    "event": "blocked",
                    "ticker": symbol,
                    "rating": rating,
                    "reason": check.reason,
                    "notional": notional,
                    "qty": qty,
                }
            )
            return ExecutionResult(False, True, rating, f"Risk blocked: {check.reason}")

        order = OrderRequest(
            symbol=symbol,
            side=side,
            quantity=qty,
            order_type=OrderType.MARKET,
            meta={"rating": rating, "broker": getattr(self.broker, "name", "?")},
        )
        result = self.broker.place_order(order)
        if result.success:
            self.guard.record_fill(notional, now_ts)

        self.audit.append(
            {
                "event": "order",
                "ticker": symbol,
                "rating": rating,
                "side": side.value,
                "qty": qty,
                "notional": notional,
                "success": result.success,
                "order_id": result.order_id,
                "message": result.message,
                "broker": getattr(self.broker, "name", "?"),
                "mode": self.config.get("trading_mode"),
            }
        )

        return ExecutionResult(
            executed=result.success,
            skipped=not result.success,
            rating=rating,
            message=result.message,
            order_result=result,
            details={"qty": qty, "notional": notional, "price": price},
        )

    def _last_price(self, symbol: str) -> float:
        hist = yf.Ticker(symbol).history(period="5d")
        if hist is None or hist.empty:
            raise RuntimeError(f"No market data for {symbol}")
        return float(hist["Close"].iloc[-1])

    def _size_quantity(
        self,
        *,
        side: Side,
        symbol: str,
        price: float,
        cash: float,
        positions: list,
        trader_plan: str,
        decision_text: str,
    ) -> int:
        max_notional = float(self.config.get("max_order_notional_krw", 1_000_000))
        # Prefer explicit % sizing from trader / PM text; else use full max order budget.
        pct = None
        for text in (trader_plan, decision_text):
            m = _SIZING_PCT_RE.search(text or "")
            if m:
                pct = float(m.group(1)) / 100.0
                break

        if side == Side.BUY:
            budget = min(max_notional, cash)
            if pct is not None:
                budget = min(budget, cash * pct)
            if price <= 0:
                return 0
            return max(int(budget // price), 0)

        # SELL: sell entire position by default, or pct of position
        held_qty = 0
        for p in positions:
            if normalize_kr_symbol(p.symbol) == symbol:
                held_qty = int(p.quantity)
                break
        if held_qty <= 0:
            return 0
        if pct is not None:
            return max(int(held_qty * pct), 0)
        # Cap sell notional too
        max_qty = int(max_notional // price) if price > 0 else held_qty
        return min(held_qty, max_qty) if max_qty > 0 else held_qty
