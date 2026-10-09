# scoring/__init__.py
# -*- coding: utf-8 -*-

"""
ماژول امتیازدهی و رتبه‌بندی (Scoring Module)

این ماژول مسئولیت محاسبه معیارها، امتیازدهی چند-شخصیتی و تحلیل
نقطه‌ای استراتژی‌ها را بر عهده دارد.

قابلیت‌ها:
    - محاسبه معیارهای کلیدی (Risk/Reward، ROM، Margin Efficiency)
    - 🆕 امتیازدهی سه‌شخصیتی (محافظه‌کار، متعادل، پرریسک)
    - امتیاز نقدشوندگی قراردادها
    - تحلیل نقطه‌ای (R30، M30، سربه‌سر، Cobb-Douglas)

معماری امتیازدهی:
    هر فرصت معاملاتی، سه امتیاز می‌گیرد:
        - conservative : برای شخص محافظه‌کار
        - balanced     : برای شخص متعادل (پیش‌فرض)
        - aggressive   : برای شخص پرریسک

    اگر فرصت در یک شخصیت رد شود، امتیاز آن -1.0 می‌شود.
"""

from __future__ import annotations


# ═════════════════════════════════════════════════════════════
# ۱. Metrics — معیارهای آماری پایه
# ═════════════════════════════════════════════════════════════

from scoring.metrics import (
    StrategyMetrics,
    calculate_risk_reward_ratio,
    calculate_rom,
    calculate_margin_efficiency,
    calculate_all_metrics,
)


# ═════════════════════════════════════════════════════════════
# ۲. Ranker — رتبه‌بندی سه‌شخصیتی
# ═════════════════════════════════════════════════════════════

from scoring.ranker import (
    OpportunityRanker,
    PERSONALITY_WEIGHTS,
    PERSONALITY_ORDER,
    DEFAULT_PERSONALITY,
)


# ═════════════════════════════════════════════════════════════
# ۳. Liquidity Score — امتیاز نقدشوندگی
# ═════════════════════════════════════════════════════════════

from scoring.liquidity_score import LiquidityScorer


# ═════════════════════════════════════════════════════════════
# ۴. Point Analyzer — تحلیل نقطه‌ای
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

    # ─── Ranker (سه‌شخصیتی) ──────────────────────
    "OpportunityRanker",
    "PERSONALITY_WEIGHTS",
    "PERSONALITY_ORDER",
    "DEFAULT_PERSONALITY",

    # ─── Liquidity ───────────────────────────────
    "LiquidityScorer",

    # ─── Point Analyzer ──────────────────────────
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