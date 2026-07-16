"""Tests for daily report gap fill."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradingagents.recommend.gap_fill import (
    MIN_REPORT_DATE,
    find_missing_report_days,
    gap_scan_start,
    save_run_state,
)
from tradingagents.recommend.paths import dated_report_dir, report_exists


@pytest.fixture
def daily_tmp(tmp_path: Path) -> Path:
    return tmp_path / "daily"


def _write_report(root: Path, as_of: str) -> None:
    d = dated_report_dir(as_of, output_dir=root)
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.json").write_text(
        json.dumps({"as_of": as_of, "recommendations": []}), encoding="utf-8"
    )


def test_find_missing_from_min_when_no_state(daily_tmp: Path) -> None:
    _write_report(daily_tmp, "2025-01-02")
    missing = find_missing_report_days("2025-01-06", output_dir=daily_tmp)
    assert "2025-01-02" not in missing
    assert "2025-01-03" in missing
    assert "2025-01-06" in missing


def test_gap_scan_start_uses_last_cover_to(daily_tmp: Path) -> None:
    save_run_state(last_cover_to="2025-06-30", output_dir=daily_tmp)
    assert gap_scan_start(output_dir=daily_tmp) == "2025-07-01"


def test_find_missing_only_after_last_cover(daily_tmp: Path) -> None:
    _write_report(daily_tmp, "2025-01-02")
    save_run_state(last_cover_to="2025-01-06", output_dir=daily_tmp)
    _write_report(daily_tmp, "2025-01-03")
    missing = find_missing_report_days("2025-01-10", output_dir=daily_tmp)
    assert MIN_REPORT_DATE <= "2025-01-07"
    assert "2025-01-03" not in missing  # before scan window
    assert "2025-01-07" in missing
    assert report_exists("2025-01-02", output_dir=daily_tmp)
