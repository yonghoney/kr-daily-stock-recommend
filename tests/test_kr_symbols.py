"""Unit tests for Korean ticker normalization and risk gates."""

from tradingagents.dataflows.symbol_utils import normalize_symbol
from tradingagents.execution.risk import RiskGuard, RiskLimits
from tradingagents.kr_config import apply_kr_defaults


def test_normalize_kospi_bare_code():
    assert normalize_symbol("005930") == "005930.KS"


def test_normalize_kosdaq_bare_code():
    # EcoPro BM remains KOSDAQ; Kakao is KOSPI now
    assert normalize_symbol("247540") == "247540.KQ"
    assert normalize_symbol("035720") == "035720.KS"


def test_normalize_already_suffixed():
    assert normalize_symbol("005930.ks") == "005930.KS"


def test_kr_defaults():
    cfg = apply_kr_defaults()
    assert cfg["market"] == "kr"
    assert cfg["benchmark_map"][".KS"] == "^KS11"
    assert "korean_news" in cfg["data_vendors"]["news_data"]


def test_live_requires_acceptance():
    g = RiskGuard(RiskLimits(trading_mode="live", i_accept_live_trading=False))
    assert g.check_live_gate().ok is False
