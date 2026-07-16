"""Rule-based daily recommendations (no LLM / broker API required)."""

from tradingagents.recommend.engine import Recommendation, run_daily_recommendations

__all__ = ["Recommendation", "run_daily_recommendations"]
