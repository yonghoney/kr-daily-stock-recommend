"""Compact SVG daily candle charts with SMA overlays (no matplotlib)."""

from __future__ import annotations

from typing import Any

import pandas as pd


def build_chart_payload(
    hist: pd.DataFrame,
    *,
    bars: int = 63,
) -> dict[str, Any] | None:
    """Downsample last ~3 months OHLCV + SMA20/60/120 for SVG rendering."""
    if hist is None or hist.empty or len(hist) < 20:
        return None
    df = hist.copy()
    close = df["Close"].astype(float)
    if "Open" not in df.columns:
        df["Open"] = close
    if "High" not in df.columns:
        df["High"] = close
    if "Low" not in df.columns:
        df["Low"] = close

    df["SMA20"] = close.rolling(20, min_periods=20).mean()
    df["SMA60"] = close.rolling(60, min_periods=20).mean()
    df["SMA120"] = close.rolling(120, min_periods=40).mean()
    tail = df.tail(bars)

    def _round_px(v: float) -> float:
        if not (v == v):  # NaN
            return float("nan")
        av = abs(v)
        if av >= 1000:
            return round(v)
        if av >= 100:
            return round(v, 1)
        return round(v, 2)

    dates: list[str] = []
    for idx in tail.index:
        try:
            dates.append(pd.Timestamp(idx).strftime("%m-%d"))
        except Exception:
            dates.append(str(idx)[-5:])

    return {
        "dates": dates,
        "o": [_round_px(float(x)) for x in tail["Open"].astype(float)],
        "h": [_round_px(float(x)) for x in tail["High"].astype(float)],
        "l": [_round_px(float(x)) for x in tail["Low"].astype(float)],
        "c": [_round_px(float(x)) for x in tail["Close"].astype(float)],
        "sma20": [
            None if pd.isna(x) else _round_px(float(x)) for x in tail["SMA20"]
        ],
        "sma60": [
            None if pd.isna(x) else _round_px(float(x)) for x in tail["SMA60"]
        ],
        "sma120": [
            None if pd.isna(x) else _round_px(float(x)) for x in tail["SMA120"]
        ],
    }


def render_candle_svg(
    payload: dict[str, Any] | None,
    *,
    width: int = 640,
    height: int = 220,
) -> str:
    """Render a compact inline SVG candle chart with SMA trend lines."""
    if not payload or not payload.get("c"):
        return ""

    dates = payload["dates"]
    o = payload["o"]
    h = payload["h"]
    l = payload["l"]
    c = payload["c"]
    n = len(c)
    if n < 2:
        return ""

    pad_l, pad_r, pad_t, pad_b = 8, 8, 18, 22
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    y_vals = [v for v in h + l if v is not None and v == v]
    for key in ("sma20", "sma60", "sma120"):
        y_vals.extend(
            v for v in (payload.get(key) or []) if v is not None and v == v
        )
    ymin, ymax = min(y_vals), max(y_vals)
    if ymax <= ymin:
        ymax = ymin + 1
    margin = (ymax - ymin) * 0.06
    ymin -= margin
    ymax += margin

    def x_at(i: int) -> float:
        return pad_l + (i + 0.5) * plot_w / n

    def y_at(p: float) -> float:
        return pad_t + (ymax - p) / (ymax - ymin) * plot_h

    candle_w = max(1.2, plot_w / n * 0.55)
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" height="{height}" role="img" aria-label="3개월 일봉 차트">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#f7fafb" rx="10"/>'
    ]

    # light grid
    for g in range(1, 4):
        gy = pad_t + plot_h * g / 4
        parts.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" '
            f'stroke="#d7e0e6" stroke-width="1"/>'
        )

    for i in range(n):
        xi = x_at(i)
        # KR convention: 양봉(상승)=red, 음봉(하락)=blue
        up = c[i] >= o[i]
        color = "#dc2626" if up else "#2563eb"
        y_h, y_l = y_at(h[i]), y_at(l[i])
        y_o, y_c = y_at(o[i]), y_at(c[i])
        body_top = min(y_o, y_c)
        body_h = max(1.0, abs(y_c - y_o))
        parts.append(
            f'<line x1="{xi:.1f}" y1="{y_h:.1f}" x2="{xi:.1f}" y2="{y_l:.1f}" '
            f'stroke="{color}" stroke-width="1"/>'
        )
        parts.append(
            f'<rect x="{xi - candle_w / 2:.1f}" y="{body_top:.1f}" '
            f'width="{candle_w:.1f}" height="{body_h:.1f}" fill="{color}"/>'
        )

    def polyline(values: list[float | None], color: str, width_px: float) -> None:
        pts = []
        for i, v in enumerate(values):
            if v is None or not (v == v):
                continue
            pts.append(f"{x_at(i):.1f},{y_at(v):.1f}")
        if len(pts) >= 2:
            parts.append(
                f'<polyline fill="none" stroke="{color}" stroke-width="{width_px}" '
                f'points="{" ".join(pts)}"/>'
            )

    polyline(payload.get("sma20") or [], "#0e7490", 1.4)
    polyline(payload.get("sma60") or [], "#b45309", 1.4)
    polyline(payload.get("sma120") or [], "#334155", 1.6)

    # legend
    parts.append(
        '<g font-size="10" font-family="IBM Plex Sans KR, sans-serif">'
        f'<text x="{pad_l}" y="12" fill="#5a6d78">3M · SMA</text>'
        f'<text x="{pad_l + 55}" y="12" fill="#0e7490">20</text>'
        f'<text x="{pad_l + 78}" y="12" fill="#b45309">60</text>'
        f'<text x="{pad_l + 101}" y="12" fill="#334155">120</text>'
        f'<text x="{width - pad_r}" y="12" text-anchor="end" fill="#5a6d78">'
        f"{dates[0]} ~ {dates[-1]}</text>"
        "</g>"
    )
    # y labels
    parts.append(
        f'<text x="{width - pad_r}" y="{pad_t + 10}" text-anchor="end" '
        f'font-size="9" fill="#5a6d78">{ymax:,.0f}</text>'
        f'<text x="{width - pad_r}" y="{height - pad_b}" text-anchor="end" '
        f'font-size="9" fill="#5a6d78">{ymin:,.0f}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)
