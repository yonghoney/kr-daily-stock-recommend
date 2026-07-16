"""Hard risk guards before any broker call."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time

import pytz

KST = pytz.timezone("Asia/Seoul")


@dataclass
class RiskLimits:
    max_order_notional_krw: float = 1_000_000
    max_daily_notional_krw: float = 5_000_000
    max_positions: int = 5
    order_cooldown_seconds: int = 60
    session_only: bool = True
    trading_mode: str = "paper"
    i_accept_live_trading: bool = False


@dataclass
class RiskCheckResult:
    ok: bool
    reason: str = ""


class RiskGuard:
    def __init__(self, limits: RiskLimits):
        self.limits = limits
        self._daily_notional = 0.0
        self._daily_date: str | None = None
        self._last_order_ts: float | None = None

    def _roll_day(self) -> None:
        today = datetime.now(KST).strftime("%Y-%m-%d")
        if self._daily_date != today:
            self._daily_date = today
            self._daily_notional = 0.0

    def check_live_gate(self) -> RiskCheckResult:
        mode = (self.limits.trading_mode or "paper").lower()
        if mode == "live" and not self.limits.i_accept_live_trading:
            return RiskCheckResult(
                False,
                "TRADING_MODE=live requires I_ACCEPT_LIVE_TRADING=true",
            )
        if mode not in {"paper", "live", "kis_paper"}:
            return RiskCheckResult(False, f"Unknown trading_mode={mode!r}")
        return RiskCheckResult(True)

    def check_session(self) -> RiskCheckResult:
        if not self.limits.session_only:
            return RiskCheckResult(True)
        mode = (self.limits.trading_mode or "paper").lower()
        # Paper/local simulation may run anytime; live/kis must be in session.
        if mode == "paper":
            return RiskCheckResult(True)
        now = datetime.now(KST)
        if now.weekday() >= 5:
            return RiskCheckResult(False, "KR market closed (weekend)")
        t = now.time()
        if not (time(9, 0) <= t <= time(15, 30)):
            return RiskCheckResult(False, "Outside KR cash session 09:00–15:30 KST")
        return RiskCheckResult(True)

    def check_order(
        self,
        *,
        notional: float,
        side: str,
        open_positions: int,
        is_new_position: bool,
        now_ts: float,
    ) -> RiskCheckResult:
        gate = self.check_live_gate()
        if not gate.ok:
            return gate
        session = self.check_session()
        if not session.ok:
            return session

        self._roll_day()

        if notional <= 0:
            return RiskCheckResult(False, "Order notional must be positive")
        if notional > self.limits.max_order_notional_krw:
            return RiskCheckResult(
                False,
                f"Order notional {notional:,.0f} exceeds max_order_notional_krw "
                f"{self.limits.max_order_notional_krw:,.0f}",
            )
        if self._daily_notional + notional > self.limits.max_daily_notional_krw:
            return RiskCheckResult(
                False,
                f"Daily notional would exceed max_daily_notional_krw "
                f"{self.limits.max_daily_notional_krw:,.0f}",
            )

        if (
            self._last_order_ts is not None
            and (now_ts - self._last_order_ts) < self.limits.order_cooldown_seconds
        ):
            return RiskCheckResult(
                False,
                f"Cooldown: wait {self.limits.order_cooldown_seconds}s between orders",
            )

        if (
            side.upper() == "BUY"
            and is_new_position
            and open_positions >= self.limits.max_positions
        ):
            return RiskCheckResult(
                False,
                f"max_positions={self.limits.max_positions} already reached",
            )

        return RiskCheckResult(True)

    def record_fill(self, notional: float, now_ts: float) -> None:
        self._roll_day()
        self._daily_notional += abs(notional)
        self._last_order_ts = now_ts
