from tradingagents.dataflows.korean_investor_flow import (
    InvestorFlowSnapshot,
    _parse_signed_int,
)
from tradingagents.recommend.signals import score_investor_flow


def test_parse_signed_int():
    assert _parse_signed_int("+1,799,843") == 1_799_843
    assert _parse_signed_int("-413,531") == -413_531
    assert _parse_signed_int("") == 0


def test_score_investor_flow_both_buy():
    flow = InvestorFlowSnapshot(
        code="005930",
        as_of="2026-07-15",
        foreign_net_1d=1000,
        organ_net_1d=500,
        individual_net_1d=-1500,
        foreign_net_5d=3000,
        organ_net_5d=2000,
        individual_net_5d=-5000,
        foreign_hold_ratio=46.6,
        days=5,
    )
    score, reasons, factors = score_investor_flow(flow)
    assert score == 14  # +8 day +6 multi-day
    assert factors
    assert any("동반 순매수" in r for r in reasons)
