"""KRX session helpers for daily as_of selection."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pandas as pd
import pytz

KST = pytz.timezone("Asia/Seoul")

# Regular cash-session close (KRX). After this, today's bar is treated as usable.
MARKET_CLOSE_KST = time(15, 30)


def analysis_as_of_date(*, now: datetime | None = None) -> str:
    """Return the session date whose close should back the analysis.

    - Weekday after market close (15:30 KST): today
    - Weekday before close / weekend: last completed weekday before today
    """
    now = now or datetime.now(KST)
    if now.tzinfo is None:
        now = KST.localize(now)
    else:
        now = now.astimezone(KST)

    today = now.date()
    if today.weekday() < 5 and now.time() >= MARKET_CLOSE_KST:
        return today.strftime("%Y-%m-%d")

    end = today - timedelta(days=1)
    days = pd.bdate_range(end=pd.Timestamp(end), periods=1)
    return days[-1].strftime("%Y-%m-%d")


def previous_session_date(*, now: datetime | None = None) -> str:
    """Last weekday session strictly before today (legacy helper)."""
    now = now or datetime.now(KST)
    if now.tzinfo is None:
        now = KST.localize(now)
    else:
        now = now.astimezone(KST)
    end = now.date() - timedelta(days=1)
    days = pd.bdate_range(end=pd.Timestamp(end), periods=1)
    return days[-1].strftime("%Y-%m-%d")
