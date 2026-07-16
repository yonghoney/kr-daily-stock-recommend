"""BrokerAdapter protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from tradingagents.execution.types import Balance, OrderRequest, OrderResult, Position


@runtime_checkable
class BrokerAdapter(Protocol):
    name: str

    def get_balance(self) -> Balance: ...

    def get_positions(self) -> list[Position]: ...

    def place_order(self, order: OrderRequest) -> OrderResult: ...

    def cancel_order(self, order_id: str) -> None: ...
