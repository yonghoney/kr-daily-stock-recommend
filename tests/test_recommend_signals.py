import pandas as pd

from tradingagents.recommend.signals import compute_tech, score_tech


def _synth(n: int = 80, trend: float = 1.0) -> pd.DataFrame:
    closes = [100 * (1 + 0.002 * trend) ** i for i in range(n)]
    return pd.DataFrame(
        {
            "Close": closes,
            "Volume": [1_000_000 + (i % 5) * 100_000 for i in range(n)],
        }
    )


def test_compute_tech_uptrend_scores_positive():
    snap = compute_tech(_synth(trend=1.0))
    assert snap is not None
    score, reasons = score_tech(snap)
    assert reasons
    assert score > 0


def test_compute_tech_needs_history():
    assert compute_tech(_synth(n=10)) is None
