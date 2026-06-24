# scoring/__init__.py

"""
ماژول امتیازدهی و رتبه‌بندی (Scoring Module)

این ماژول مسئولیت محاسبه معیارها و امتیازدهی نهایی به استراتژی‌ها را بر عهده دارد.

قابلیت‌ها:
    - محاسبه معیارهای کلیدی (Win Rate, Risk/Reward, Margin, ROM)
    - امتیازدهی نهایی و رتبه‌بندی
    - گلچین کردن موقعیت‌های برتر
"""

from scoring.metrics import (
    StrategyMetrics,
    calculate_win_rate,
    calculate_risk_reward_ratio,
    calculate_rom,
    calculate_margin_efficiency,)

from scoring.ranker import (
    OpportunityRanker,
    RankingProfile,
    PROFILES,)

from scoring.liquidity_score import LiquidityScorer

__all__ = [
    # Metrics
    "StrategyMetrics",
    "calculate_win_rate",
    "calculate_risk_reward_ratio",
    "calculate_rom",
    "calculate_margin_efficiency",
    
    # Ranker
    "OpportunityRanker",
    "RankedOpportunity",
    "RankingProfile",
    "PROFILES",
    
    # Liquidity
    "LiquidityScorer",
]