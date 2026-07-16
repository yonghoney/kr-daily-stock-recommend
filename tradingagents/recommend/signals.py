"""Technical signal helpers from OHLCV — no LLM."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class TechSnapshot:
    last_close: float
    ret_1d: float
    ret_5d: float
    ret_20d: float
    sma20: float
    sma60: float
    rsi14: float
    vol_ratio: float  # today vol / 20d avg
    above_sma20: bool
    above_sma60: bool
    golden_cross_proxy: bool  # sma20 > sma60
    bars: int


def _rsi(series: pd.Series, period: int = 14) -> float:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    val = float(rsi.iloc[-1])
    return val if np.isfinite(val) else 50.0


def compute_tech(hist: pd.DataFrame) -> TechSnapshot | None:
    if hist is None or hist.empty or len(hist) < 25:
        return None
    df = hist.copy()
    close = df["Close"].astype(float)
    volume = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series(0.0, index=df.index)

    sma20 = float(close.tail(20).mean())
    sma60 = float(close.tail(min(60, len(close))).mean())
    last = float(close.iloc[-1])
    ret_1d = float(close.iloc[-1] / close.iloc[-2] - 1) if len(close) >= 2 else 0.0
    ret_5d = float(close.iloc[-1] / close.iloc[-6] - 1) if len(close) >= 6 else 0.0
    ret_20d = float(close.iloc[-1] / close.iloc[-21] - 1) if len(close) >= 21 else 0.0
    vol_ma = float(volume.tail(20).mean()) or 1.0
    vol_ratio = float(volume.iloc[-1] / vol_ma) if vol_ma else 1.0

    return TechSnapshot(
        last_close=last,
        ret_1d=ret_1d,
        ret_5d=ret_5d,
        ret_20d=ret_20d,
        sma20=sma20,
        sma60=sma60,
        rsi14=_rsi(close, 14),
        vol_ratio=vol_ratio,
        above_sma20=last >= sma20,
        above_sma60=last >= sma60,
        golden_cross_proxy=sma20 >= sma60,
        bars=len(df),
    )


def score_tech(snap: TechSnapshot) -> tuple[float, list[str]]:
    """Return score in roughly [-100, 100] and human-readable reasons."""
    score = 0.0
    reasons: list[str] = []

    # Trend
    if snap.above_sma20 and snap.above_sma60:
        score += 20
        reasons.append("종가가 20·60일 이동평균 위 (추세 우호)")
    elif snap.above_sma20:
        score += 8
        reasons.append("종가가 20일선 위")
    else:
        score -= 15
        reasons.append("종가가 20일선 아래 (단기 약세)")

    if snap.golden_cross_proxy:
        score += 10
        reasons.append("20일선 ≥ 60일선 (중기 정배열 성향)")
    else:
        score -= 8
        reasons.append("20일선 < 60일선 (중기 역배열 성향)")

    # Momentum
    if snap.ret_5d > 0.03:
        score += 12
        reasons.append(f"5일 수익률 +{snap.ret_5d*100:.1f}% (모멘텀)")
    elif snap.ret_5d < -0.03:
        score -= 12
        reasons.append(f"5일 수익률 {snap.ret_5d*100:.1f}% (단기 조정)")

    if snap.ret_20d > 0.05:
        score += 10
        reasons.append(f"20일 수익률 +{snap.ret_20d*100:.1f}%")
    elif snap.ret_20d < -0.08:
        score -= 12
        reasons.append(f"20일 수익률 {snap.ret_20d*100:.1f}% (중기 약세)")

    # RSI
    if 45 <= snap.rsi14 <= 65:
        score += 10
        reasons.append(f"RSI14={snap.rsi14:.0f} (중립~건전 구간)")
    elif 30 <= snap.rsi14 < 45:
        score += 6
        reasons.append(f"RSI14={snap.rsi14:.0f} (과매도 근접, 반등 여지)")
    elif snap.rsi14 < 30:
        score += 2
        reasons.append(f"RSI14={snap.rsi14:.0f} (과매도 — 반등·추가하락 모두 가능)")
    elif 65 < snap.rsi14 <= 75:
        score -= 5
        reasons.append(f"RSI14={snap.rsi14:.0f} (과열 주의)")
    else:
        score -= 15
        reasons.append(f"RSI14={snap.rsi14:.0f} (과매수 — 조정 위험)")

    # Volume
    if snap.vol_ratio >= 1.5 and snap.ret_1d > 0:
        score += 8
        reasons.append(f"거래량 {snap.vol_ratio:.1f}× + 상승일 (수급 유입)")
    elif snap.vol_ratio >= 1.5 and snap.ret_1d < 0:
        score -= 8
        reasons.append(f"거래량 {snap.vol_ratio:.1f}× + 하락일 (매도 압력)")

    return max(-100.0, min(100.0, score)), reasons
