"""Migrate reports/daily/YYYY-MM-DD → reports/daily/YYYY/MM/DD."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DAILY = ROOT / "reports" / "daily"


def main() -> int:
    if not DAILY.exists():
        print("no daily dir")
        return 0
    moved = skipped = 0
    for legacy in sorted(DAILY.iterdir()):
        if not legacy.is_dir():
            continue
        name = legacy.name
        if len(name) != 10 or name.count("-") != 2:
            continue
        y, m, d = name.split("-")
        if not (y.isdigit() and m.isdigit() and d.isdigit()):
            continue
        dest = DAILY / y / m / d
        if dest.exists():
            # Prefer keeping dest; remove empty-ish legacy if identical intent
            print(f"skip (exists): {name} -> {dest.relative_to(DAILY)}")
            skipped += 1
            # Remove legacy only if dest has report.json
            if (dest / "report.json").exists():
                shutil.rmtree(legacy, ignore_errors=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy), str(dest))
        print(f"moved: {name} -> {y}/{m}/{d}")
        moved += 1
    print(f"done: moved={moved} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
