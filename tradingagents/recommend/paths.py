"""Paths for daily / backtest report storage."""

from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def daily_root(output_dir: Path | None = None) -> Path:
    return output_dir or (project_root() / "reports" / "daily")


def dated_report_dir(as_of: str, *, output_dir: Path | None = None) -> Path:
    """Return reports/daily/YYYY/MM/DD for as_of (YYYY-MM-DD)."""
    parts = str(as_of).strip().split("-")
    if len(parts) != 3:
        raise ValueError(f"as_of must be YYYY-MM-DD, got {as_of!r}")
    year, month, day = parts
    return daily_root(output_dir) / year / month / day


def dated_report_json(as_of: str, *, output_dir: Path | None = None) -> Path:
    return dated_report_dir(as_of, output_dir=output_dir) / "report.json"


def legacy_report_json(as_of: str, *, output_dir: Path | None = None) -> Path:
    """Legacy layout: reports/daily/YYYY-MM-DD/report.json"""
    return daily_root(output_dir) / as_of / "report.json"


def report_exists(as_of: str, *, output_dir: Path | None = None) -> bool:
    return dated_report_json(as_of, output_dir=output_dir).exists() or legacy_report_json(
        as_of, output_dir=output_dir
    ).exists()


def run_state_path(*, output_dir: Path | None = None) -> Path:
    return daily_root(output_dir) / ".run_state.json"


def latest_report_date(
    *,
    start: str | None = None,
    end: str | None = None,
    output_dir: Path | None = None,
) -> str | None:
    reports = iter_dated_report_jsons(start=start, end=end, output_dir=output_dir)
    if not reports:
        return None
    return reports[-1][0]


def iter_dated_report_jsons(
    *,
    start: str | None = None,
    end: str | None = None,
    output_dir: Path | None = None,
) -> list[tuple[str, Path]]:
    """Find report.json under YYYY/MM/DD (and legacy YYYY-MM-DD)."""
    root = daily_root(output_dir)
    if not root.exists():
        return []
    found: list[tuple[str, Path]] = []

    # New layout: daily/YYYY/MM/DD/report.json
    for year_dir in sorted(p for p in root.iterdir() if p.is_dir() and p.name.isdigit()):
        for month_dir in sorted(
            p for p in year_dir.iterdir() if p.is_dir() and p.name.isdigit()
        ):
            for day_dir in sorted(
                p for p in month_dir.iterdir() if p.is_dir() and p.name.isdigit()
            ):
                report = day_dir / "report.json"
                if not report.exists():
                    continue
                as_of = f"{year_dir.name}-{month_dir.name}-{day_dir.name}"
                if start and as_of < start:
                    continue
                if end and as_of > end:
                    continue
                found.append((as_of, report))

    # Legacy layout: daily/YYYY-MM-DD/report.json
    for legacy in sorted(p for p in root.iterdir() if p.is_dir() and len(p.name) == 10):
        if legacy.name.count("-") != 2:
            continue
        report = legacy / "report.json"
        if not report.exists():
            continue
        as_of = legacy.name
        if start and as_of < start:
            continue
        if end and as_of > end:
            continue
        # Prefer new layout if both exist
        if any(a == as_of for a, _ in found):
            continue
        found.append((as_of, report))

    found.sort(key=lambda x: x[0])
    return found
