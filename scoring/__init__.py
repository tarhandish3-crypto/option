# scoring/__init__.py
# -*- coding: utf-8 -*-

"""
ماژول امتیازدهی و رتبه‌بندی (Scoring Module)

این ماژول مسئولیت محاسبه معیارها، امتیازدهی نهایی و تحلیل نقطه‌ای
استراتژی‌ها را بر عهده دارد.

قابلیت‌ها:
    - محاسبه معیارهای کلیدی (Win Rate, Risk/Reward, Margin, ROM)
    - امتیازدهی چندبعدی و رتبه‌بندی بر اساس ۵ پروفایل سرمایه‌گذاری
    - امتیاز نقدشوندگی قراردادها
    - 🆕 تحلیل نقطه‌ای (R30، M30، سربه‌سر، Cobb-Douglas)
    - 🆕 فیلتر نقطه‌ای و استخراج شاخص‌های ساده

نکته مهم:
    ماژول point_analyzer یک ماژول مستقل است و می‌تواند بدون ranker
    استفاده شود. اما استفاده‌ی همزمان از آن‌ها انعطاف بیشتری می‌دهد.
"""

from __future__ import annotations


# ═════════════════════════════════════════════════════════════
# ۱. Metrics — معیارهای آماری
# ═════════════════════════════════════════════════════════════

from scoring.metrics import (
    StrategyMetrics,
    calculate_risk_reward_ratio,
    calculate_rom,
    calculate_margin_efficiency,
    calculate_all_metrics,
)


# ═════════════════════════════════════════════════════════════
# ۲. Ranker — رتبه‌بندی چندبعدی
# ═════════════════════════════════════════════════════════════

from scoring.ranker import (
    OpportunityRanker,
    RankingWeights,
    PROFILES,
)

# سازگاری با importهای قدیمی
from core.enums import RankingProfile


# ═════════════════════════════════════════════════════════════
# ۳. Liquidity Score — امتیاز نقدشوندگی
# ═════════════════════════════════════════════════════════════

from scoring.liquidity_score import LiquidityScorer


# ═════════════════════════════════════════════════════════════
# ۴. 🆕 Point Analyzer — تحلیل نقطه‌ای
# ═════════════════════════════════════════════════════════════

from scoring.point_analyzer import (
    # Enrichment
    enrich_opportunity,
    enrich_all,

    # Filters
    apply_point_filters,
    filter_by_strategy,

    # High-Level API
    process_opportunities,
    get_summary,

    # Constants
    STRATEGY_FILTERS,
    DEFAULT_R_MIN,
    DEFAULT_M_MIN,
    DEFAULT_SCORE_THRESHOLD,
)


# ═════════════════════════════════════════════════════════════
# ۵. __all__ — صادرات عمومی
# ═════════════════════════════════════════════════════════════

__all__ = [
    # ─── Metrics ─────────────────────────────────
    "StrategyMetrics",
    "calculate_risk_reward_ratio",
    "calculate_rom",
    "calculate_margin_efficiency",
    "calculate_all_metrics",

    # ─── Ranker ──────────────────────────────────
    "OpportunityRanker",
    "RankingWeights",
    "PROFILES",
    "RankingProfile",

    # ─── Liquidity ───────────────────────────────
    "LiquidityScorer",

    # ─── 🆕 Point Analyzer ──────────────────────
    # Enrichment
    "enrich_opportunity",
    "enrich_all",

    # Filters
    "apply_point_filters",
    "filter_by_strategy",

    # High-Level
    "process_opportunities",
    "get_summary",

    # Constants
    "STRATEGY_FILTERS",
    "DEFAULT_R_MIN",
    "DEFAULT_M_MIN",
    "DEFAULT_SCORE_THRESHOLD",
]