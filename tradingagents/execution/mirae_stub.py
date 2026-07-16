"""Mirae Asset stub — personal KR domestic Open API is not available."""

from __future__ import annotations

from tradingagents.execution.types import Balance, OrderRequest, OrderResult, Position

_MSG = (
    "Mirae Asset (미래에셋증권) does not provide a personal Open API for "
    "Korean domestic equities. Use broker=paper or broker=kis instead. "
    "This stub exists only to keep the BrokerAdapter interface stable."
)


class MiraeStubBroker:
    name = "mirae"

    def get_balance(self) -> Balance:
        raise NotImplementedError(_MSG)

    def get_positions(self) -> list[Position]:
        raise NotImplementedError(_MSG)

    def place_order(self, order: OrderRequest) -> OrderResult:
        return OrderResult(False, None, _MSG)

    def cancel_order(self, order_id: str) -> None:
        raise NotImplementedError(_MSG)
