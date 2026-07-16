"""Tests for KRX analysis as_of selection."""

from __future__ import annotations

from datetime import datetime

import pytz

from tradingagents.recommend.session import analysis_as_of_date

KST = pytz.timezone("Asia/Seoul")


def test_after_close_weekday_uses_today() -> None:
    now = KST.localize(datetime(2026, 7, 16, 15, 55))
    assert analysis_as_of_date(now=now) == "2026-07-16"


def test_before_close_weekday_uses_previous() -> None:
    now = KST.localize(datetime(2026, 7, 16, 14, 0))
    assert analysis_as_of_date(now=now) == "2026-07-15"


def test_weekend_uses_friday() -> None:
    now = KST.localize(datetime(2026, 7, 18, 16, 0))  # Saturday
    assert analysis_as_of_date(now=now) == "2026-07-17"


def test_monday_morning_uses_friday() -> None:
    now = KST.localize(datetime(2026, 7, 20, 10, 0))
    assert analysis_as_of_date(now=now) == "2026-07-17"
