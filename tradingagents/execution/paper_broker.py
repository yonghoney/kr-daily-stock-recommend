"""Local SQLite paper broker for KR equities."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import yfinance as yf

from tradingagents.dataflows.kr_symbols import kr_base_code, normalize_kr_symbol
from tradingagents.execution.types import (
    Balance,
    OrderRequest,
    OrderResult,
    OrderType,
    Position,
    Side,
)


class PaperBroker:
    name = "paper"

    def __init__(
        self,
        db_path: str | Path | None = None,
        initial_cash: float = 10_000_000,
    ):
        home = Path.home() / ".tradingagents" / "paper"
        home.mkdir(parents=True, exist_ok=True)
        self.db_path = Path(db_path) if db_path else home / "paper_broker.db"
        self.initial_cash = float(initial_cash)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS account (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    cash REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    quantity INTEGER NOT NULL,
                    avg_price REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    symbol TEXT,
                    side TEXT,
                    quantity INTEGER,
                    price REAL,
                    status TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            row = conn.execute("SELECT cash FROM account WHERE id = 1").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO account (id, cash) VALUES (1, ?)",
                    (self.initial_cash,),
                )

    def get_balance(self) -> Balance:
        with self._connect() as conn:
            cash = float(conn.execute("SELECT cash FROM account WHERE id = 1").fetchone()["cash"])
        return Balance(cash=cash, currency="KRW", buying_power=cash)

    def get_positions(self) -> list[Position]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT symbol, quantity, avg_price FROM positions WHERE quantity != 0"
            ).fetchall()
        return [
            Position(
                symbol=r["symbol"],
                quantity=int(r["quantity"]),
                avg_price=float(r["avg_price"]),
                market_value=None,
            )
            for r in rows
        ]

    def _last_price(self, symbol: str) -> float:
        yahoo = normalize_kr_symbol(symbol)
        hist = yf.Ticker(yahoo).history(period="5d")
        if hist is None or hist.empty:
            raise RuntimeError(f"No price for paper fill: {yahoo}")
        return float(hist["Close"].iloc[-1])

    def place_order(self, order: OrderRequest) -> OrderResult:
        symbol = normalize_kr_symbol(order.symbol)
        if order.quantity <= 0:
            return OrderResult(False, None, "quantity must be > 0")

        try:
            if order.order_type == OrderType.LIMIT and order.limit_price is not None:
                price = float(order.limit_price)
            else:
                price = self._last_price(symbol)
        except Exception as exc:
            return OrderResult(False, None, f"price lookup failed: {exc}")

        notional = price * order.quantity
        order_id = order.client_order_id or f"PAPER-{uuid.uuid4().hex[:12]}"

        with self._connect() as conn:
            cash = float(conn.execute("SELECT cash FROM account WHERE id = 1").fetchone()["cash"])
            pos = conn.execute(
                "SELECT quantity, avg_price FROM positions WHERE symbol = ?",
                (symbol,),
            ).fetchone()
            qty = int(pos["quantity"]) if pos else 0
            avg = float(pos["avg_price"]) if pos else 0.0

            if order.side == Side.BUY:
                if cash < notional:
                    return OrderResult(
                        False, order_id, f"Insufficient cash: need {notional:.0f}, have {cash:.0f}"
                    )
                new_qty = qty + order.quantity
                new_avg = ((avg * qty) + notional) / new_qty if new_qty else 0.0
                conn.execute(
                    "UPDATE account SET cash = ? WHERE id = 1", (cash - notional,)
                )
                conn.execute(
                    """
                    INSERT INTO positions (symbol, quantity, avg_price)
                    VALUES (?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        quantity = excluded.quantity,
                        avg_price = excluded.avg_price
                    """,
                    (symbol, new_qty, new_avg),
                )
            else:
                if qty < order.quantity:
                    return OrderResult(
                        False, order_id, f"Insufficient shares: have {qty}, sell {order.quantity}"
                    )
                new_qty = qty - order.quantity
                conn.execute(
                    "UPDATE account SET cash = ? WHERE id = 1", (cash + notional,)
                )
                if new_qty == 0:
                    conn.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
                else:
                    conn.execute(
                        "UPDATE positions SET quantity = ? WHERE symbol = ?",
                        (new_qty, symbol),
                    )

            conn.execute(
                """
                INSERT INTO orders (order_id, symbol, side, quantity, price, status)
                VALUES (?, ?, ?, ?, ?, 'FILLED')
                """,
                (order_id, symbol, order.side.value, order.quantity, price),
            )

        return OrderResult(
            True,
            order_id,
            "Paper fill",
            filled_qty=order.quantity,
            avg_price=price,
            raw={"broker": "paper", "kr_code": kr_base_code(symbol)},
        )

    def cancel_order(self, order_id: str) -> None:
        # Paper fills are immediate; nothing to cancel.
        return None
