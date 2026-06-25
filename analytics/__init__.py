# analytics/__init__.py
# -*- coding: utf-8 -*-

"""
پکیج تحلیل پیشرفته برای استراتژی‌های اختیار معامله بورس ایران
"""

from analytics.greeks_and_probabilities import (
    calculate_d1_d2,
    calculate_leg_greeks,
    calculate_vega,
    calculate_full_greeks,
    get_price_step_probabilities,
    calculate_strategy_greeks,
)

from analytics.payoff_calculator import (
    IranMarketPayoffCalculator,
    enrich_opportunity_with_pnl,
)

from analytics.risk_engine import (
    RiskEngine,
    RiskMetrics,
    CurveType,
    print_risk_summary,
    calculate_risk_metrics_from_payoff
)

from analytics.margin_calculator import (
    MarginCalculator,
    MarginResult,
    MarginContract,
    LegDefinition
)

from analytics.cost_calculator import (
    IranMarketCostCalculator,
    StrategyCosts,
)

from core.enums import OptionType, Side

__all__ = [
    # یونانی‌ها
    'calculate_d1_d2',
    'calculate_leg_greeks',
    'calculate_vega',
    'calculate_full_greeks',
    'get_price_step_probabilities',
    'calculate_strategy_greeks',

    # P&L
    'IranMarketPayoffCalculator',
    'enrich_opportunity_with_pnl',

    # ریسک
    'RiskEngine',
    'RiskMetrics',
    'CurveType',
    'print_risk_summary',
    'calculate_risk_metrics_from_payoff',

    # مارجین
    'MarginCalculator',
    'MarginResult',
    'MarginContract',
    'LegDefinition',

    # کارمزد
    'IranMarketCostCalculator',
    'StrategyCosts',

    # انوم‌ها
    'OptionType',
    'Side',
]
