"""Shared order / account types for broker adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass
class Balance:
    cash: float
    currency: str = "KRW"
    buying_power: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Position:
    symbol: str  # Yahoo-style or KRX code
    quantity: int
    avg_price: float
    market_value: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderRequest:
    symbol: str
    side: Side
    quantity: int
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = None
    client_order_id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderResult:
    success: bool
    order_id: str | None
    message: str
    filled_qty: int = 0
    avg_price: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
