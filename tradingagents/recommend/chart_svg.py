"""Compact SVG daily candle charts with SMA overlays (no matplotlib)."""

from __future__ import annotations

from typing import Any

import pandas as pd


def append_svg_legend(
    parts: list[str],
    items: list[tuple[str, str, float]],
    *,
    width: int,
    y: float,
    swatch_w: float = 18,
    item_gap: float = 18,
    font_size: int = 10,
    stroke_width: float = 2,
) -> None:
    """Centered legend: (label, color, line_width) per series."""
    if not items:
        return
    # Hangul is wider than Latin; use a generous per-char estimate.
    char_w = font_size * 0.95
    label_gap = 6
    blocks: list[tuple[float, str, str, float]] = []
    for label, color, lw in items:
        text_w = max(len(label), 1) * char_w
        block_w = swatch_w + label_gap + text_w
        blocks.append((block_w, label, color, lw))
    total_w = sum(b[0] for b in blocks) + item_gap * max(len(blocks) - 1, 0)
    x = (width - total_w) / 2
    font = (
        f'font-size="{font_size}" font-family="IBM Plex Sans KR, sans-serif" '
        f'dominant-baseline="middle"'
    )
    for block_w, label, color, lw in blocks:
        mid_y = y
        parts.append(
            f'<line x1="{x:.1f}" y1="{mid_y:.1f}" x2="{x + swatch_w:.1f}" y2="{mid_y:.1f}" '
            f'stroke="{color}" stroke-width="{max(lw, stroke_width)}" stroke-linecap="round"/>'
        )
        tx = x + swatch_w + label_gap
        parts.append(
            f'<text x="{tx:.1f}" y="{mid_y:.1f}" fill="{color}" {font}>{label}</text>'
        )
        x += block_w + item_gap


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
    iso_dates: list[str] = []
    for idx in tail.index:
        ts = pd.Timestamp(idx)
        try:
            dates.append(ts.strftime("%m-%d"))
        except Exception:
            dates.append(str(idx)[-5:])
        try:
            iso_dates.append(ts.tz_localize(None).strftime("%Y-%m-%d") if ts.tzinfo else ts.strftime("%Y-%m-%d"))
        except Exception:
            iso_dates.append(str(idx)[:10])

    return {
        "dates": dates,
        "iso_dates": iso_dates,
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
    markers: list[dict[str, str]] | None = None,
) -> str:
    """Render a compact inline SVG candle chart with SMA trend lines.

    ``markers`` optional list of ``{"date": "YYYY-MM-DD", "action": "매수관심"|"주의"}``.
    """
    if not payload or not payload.get("c"):
        return ""

    dates = payload["dates"]
    iso_dates = payload.get("iso_dates") or []
    o = payload["o"]
    h = payload["h"]
    l = payload["l"]
    c = payload["c"]
    n = len(c)
    if n < 2:
        return ""

    pad_l, pad_r, pad_t, pad_b = 8, 8, 18, 28
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

    for g in range(1, 4):
        gy = pad_t + plot_h * g / 4
        parts.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" '
            f'stroke="#d7e0e6" stroke-width="1"/>'
        )

    for i in range(n):
        xi = x_at(i)
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

    # Signal markers (triangles under candles)
    if markers and iso_dates:
        idx_by_date = {d: i for i, d in enumerate(iso_dates)}
        for m in markers:
            day = str(m.get("date") or "")
            action = str(m.get("action") or "")
            i = idx_by_date.get(day)
            if i is None:
                continue
            xi = x_at(i)
            yb = y_at(l[i]) + 6
            if action == "매수관심":
                # up triangle (buy)
                parts.append(
                    f'<polygon points="{xi:.1f},{yb - 7:.1f} {xi - 4.5:.1f},{yb:.1f} '
                    f'{xi + 4.5:.1f},{yb:.1f}" fill="#0b7a63" opacity="0.9"/>'
                )
            elif action == "주의":
                # down triangle (caution)
                parts.append(
                    f'<polygon points="{xi:.1f},{yb:.1f} {xi - 4.5:.1f},{yb - 7:.1f} '
                    f'{xi + 4.5:.1f},{yb - 7:.1f}" fill="#c2410c" opacity="0.9"/>'
                )

    parts.append(
        '<g font-size="10" font-family="IBM Plex Sans KR, sans-serif">'
        f'<text x="{pad_l}" y="12" fill="#5a6d78">3M · SMA</text>'
        f'<text x="{pad_l + 55}" y="12" fill="#0e7490">20</text>'
        f'<text x="{pad_l + 78}" y="12" fill="#b45309">60</text>'
        f'<text x="{pad_l + 101}" y="12" fill="#334155">120</text>'
        f'<text x="{pad_l + 140}" y="12" fill="#0b7a63">▲매수</text>'
        f'<text x="{pad_l + 185}" y="12" fill="#c2410c">▼주의</text>'
        f'<text x="{width - pad_r}" y="12" text-anchor="end" fill="#5a6d78">'
        f"{dates[0]} ~ {dates[-1]}</text>"
        "</g>"
    )
    parts.append(
        f'<text x="{width - pad_r}" y="{pad_t + 10}" text-anchor="end" '
        f'font-size="9" fill="#5a6d78">{ymax:,.0f}</text>'
        f'<text x="{width - pad_r}" y="{height - pad_b}" text-anchor="end" '
        f'font-size="9" fill="#5a6d78">{ymin:,.0f}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def render_score_price_svg(
    points: list[tuple[str, float]] | None,
    hist,
    *,
    width: int = 640,
    height: int = 178,
    y_score_min: float = -100.0,
    y_score_max: float = 100.0,
) -> str:
    """Dual-axis: score (left, fixed ±100) vs close price (right).

    Only days with a score are plotted; consecutive score days are joined
    with a straight line (missing watchlist days are skipped, not gaps).
    """
    if not points or hist is None or getattr(hist, "empty", True):
        return ""
    if "Close" not in getattr(hist, "columns", []):
        return ""

    close = hist["Close"].copy()
    idx = pd.to_datetime(close.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_convert(None)
    close.index = pd.DatetimeIndex(idx).normalize()
    close = close[~close.index.duplicated(keep="last")].sort_index()

    by_day: dict[str, float] = {}
    for day, score in points:
        if not day:
            continue
        try:
            by_day[str(day)[:10]] = float(score)
        except (TypeError, ValueError):
            continue

    series: list[tuple[str, float, float]] = []
    for day, score in sorted(by_day.items()):
        ts = pd.Timestamp(day).normalize()
        if ts not in close.index:
            prior = close.index[close.index <= ts]
            if len(prior) == 0:
                continue
            ts = prior[-1]
        px = float(close.loc[ts])
        if px != px or px <= 0:
            continue
        series.append((day, score, px))

    if len(series) < 2:
        return ""

    n = len(series)
    pad_l, pad_r, pad_t, pad_b = 40, 48, 22, 30
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    if y_score_max <= y_score_min:
        y_score_max = y_score_min + 1

    prices = [p for _, _, p in series]
    p_min, p_max = min(prices), max(prices)
    if p_max <= p_min:
        p_max = p_min + 1
    p_pad = (p_max - p_min) * 0.08
    p_min -= p_pad
    p_max += p_pad

    def x_at(i: int) -> float:
        return pad_l + i * plot_w / max(n - 1, 1)

    def y_score(v: float) -> float:
        v = max(y_score_min, min(y_score_max, v))
        return pad_t + (y_score_max - v) / (y_score_max - y_score_min) * plot_h

    def y_price(v: float) -> float:
        return pad_t + (p_max - v) / (p_max - p_min) * plot_h

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" height="{height}" role="img" '
        f'aria-label="점수와 주가 비교">'
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#f7fafb" rx="10"/>'
    ]

    for g in range(1, 4):
        gy = pad_t + plot_h * g / 4
        parts.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{width - pad_r}" y2="{gy:.1f}" '
            f'stroke="#e2e8f0" stroke-width="1"/>'
        )

    if y_score_min < 0 < y_score_max:
        zy = y_score(0.0)
        parts.append(
            f'<line x1="{pad_l}" y1="{zy:.1f}" x2="{width - pad_r}" y2="{zy:.1f}" '
            f'stroke="#94a3b8" stroke-width="1.2"/>'
        )

    score_pts = [
        f"{x_at(i):.1f},{y_score(s):.1f}" for i, (_, s, _) in enumerate(series)
    ]
    price_pts = [
        f"{x_at(i):.1f},{y_price(p):.1f}" for i, (_, _, p) in enumerate(series)
    ]
    parts.append(
        f'<polyline fill="none" stroke="#64748b" stroke-width="1.5" '
        f'stroke-linejoin="round" stroke-linecap="round" '
        f'points="{" ".join(price_pts)}"/>'
    )
    parts.append(
        f'<polyline fill="none" stroke="#0f766e" stroke-width="1.8" '
        f'stroke-linejoin="round" stroke-linecap="round" '
        f'points="{" ".join(score_pts)}"/>'
    )
    lx, ly = x_at(n - 1), y_score(series[-1][1])
    parts.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3" fill="#0f766e"/>')
    lpx, lpy = x_at(n - 1), y_price(series[-1][2])
    parts.append(f'<circle cx="{lpx:.1f}" cy="{lpy:.1f}" r="2.6" fill="#64748b"/>')

    d0 = series[0][0][5:] if len(series[0][0]) >= 10 else series[0][0]
    d1 = series[-1][0][5:] if len(series[-1][0]) >= 10 else series[-1][0]
    parts.append(
        '<g font-size="10" font-family="IBM Plex Sans KR, sans-serif">'
        f'<text x="{pad_l}" y="14" fill="#334155">점수 vs 종가 (점수 있는 날만 연결)</text>'
        f'<text x="{width - pad_r}" y="14" text-anchor="end" fill="#64748b">'
        f"{d0} ~ {d1} · {n}일</text>"
        f'<text x="{pad_l - 4}" y="{pad_t + 8}" text-anchor="end" fill="#0f766e">'
        f"{y_score_max:.0f}</text>"
        f'<text x="{pad_l - 4}" y="{height - pad_b + 4}" text-anchor="end" fill="#0f766e">'
        f"{y_score_min:.0f}</text>"
        f'<text x="{width - pad_r + 4}" y="{pad_t + 8}" fill="#64748b">'
        f"{p_max:,.0f}</text>"
        f'<text x="{width - pad_r + 4}" y="{height - pad_b + 4}" fill="#64748b">'
        f"{p_min:,.0f}</text>"
        "</g>"
    )
    append_svg_legend(
        parts,
        [("점수", "#0f766e", 1.8), ("종가", "#64748b", 1.5)],
        width=width,
        y=height - 10,
    )
    parts.append("</svg>")
    return "".join(parts)
