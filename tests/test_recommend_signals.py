import pandas as pd

from tradingagents.recommend.signals import compute_tech, score_tech


def _synth(n: int = 150, trend: float = 1.0) -> pd.DataFrame:
    closes = [100 * (1 + 0.002 * trend) ** i for i in range(n)]
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c * 1.01 for c in closes],
            "Low": [c * 0.99 for c in closes],
            "Close": closes,
            "Volume": [1_000_000 + (i % 5) * 100_000 for i in range(n)],
        }
    )


def test_compute_tech_uptrend_scores_positive():
    snap = compute_tech(_synth(trend=1.0))
    assert snap is not None
    assert snap.sma120 > 0
    score, reasons, factors = score_tech(snap)
    assert reasons
    assert factors
    assert score > 0
    assert abs(factors[0].impact) >= abs(factors[-1].impact)
    assert any("120" in r for r in reasons)


def test_compute_tech_needs_history():
    assert compute_tech(_synth(n=10)) is None
