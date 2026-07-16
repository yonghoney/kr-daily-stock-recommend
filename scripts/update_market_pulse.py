"""Build market pulse (recent 3 months) and inject into latest.html."""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytz

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

KST = pytz.timezone("Asia/Seoul")


def main() -> int:
    from tradingagents.recommend.market_pulse import (
        load_or_build_market_pulse,
        render_market_pulse_html,
    )

    end = datetime.now(KST).strftime("%Y-%m-%d")
    start = (pd.Timestamp(end) - pd.DateOffset(months=3)).strftime("%Y-%m-%d")
    pulse = load_or_build_market_pulse(start=start, end=end, rebuild=True)
    block = render_market_pulse_html(pulse).strip()
    print(
        f"pulse {start}~{end} · kospi={len(pulse['metrics']['코스피'])} "
        f"kosdaq={len(pulse['metrics']['코스닥'])}",
        flush=True,
    )

    latest = ROOT / "reports" / "daily" / "latest.html"
    if not latest.exists():
        print("latest.html missing — run run_daily.py later to embed pulse")
        return 0

    html = latest.read_text(encoding="utf-8")
    if ".market-pulse" not in html:
        css = """
    .market-pulse { margin: 0 0 1.1rem; }
    body.detail-open .market-pulse { display: none; }
    .pulse-head { margin: 0 0 0.75rem; }
    .pulse-head h2 { margin: 0 0 0.25rem; font-size: 1.15rem; }
    .pulse-head p { margin: 0; color: var(--muted); font-size: 0.9rem; line-height: 1.45; max-width: 46rem; }
    .pulse-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0.85rem; }
    .pulse-card { background: var(--panel); border: 1px solid var(--line); border-radius: 16px; padding: 0.75rem 0.85rem 0.9rem; }
    .pulse-card h3 { margin: 0 0 0.55rem; font-size: 1rem; }
    .pulse-charts { display: grid; gap: 0.55rem; }
    .block.chart.pulse { margin-top: 0; }
    @media (max-width: 900px) { .pulse-grid { grid-template-columns: 1fr; } }
"""
        html = html.replace("</style>", css + "\n  </style>", 1)

    if 'class="market-pulse"' in html:
        html = re.sub(
            r'<section class="market-pulse"[\s\S]*?</section>\s*',
            block + "\n\n    ",
            html,
            count=1,
        )
    else:
        html = html.replace("</header>", "</header>\n\n    " + block + "\n", 1)

    latest.write_text(html, encoding="utf-8")
    print(f"updated {latest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
