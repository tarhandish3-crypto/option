# filters/strategy_filters.py
# -*- coding: utf-8 -*-


"""
لایه فیلتر پویا و هوشمند بر اساس درصد بازدهی استراتژی
"""

import logging
import numpy as np
from typing import List, Dict, Any, Callable

from core.models import Opportunity

logger = logging.getLogger("OptionScanner.Filters.StrategyFilters")


def apply_strategy_filter(opp: Opportunity, user_conditions: Dict[str, Any] = None) -> bool:
    """
    فیلتر اصلی هوشمند بر اساس درصد بازدهی
    """
    if user_conditions is None:
        user_conditions = {}

    name = opp.strategy_name.lower().strip()
    returns = np.array(opp.metadata.get(
        'returns_monthly_pct', []), dtype=float)

    if len(returns) == 0:
        return False

    max_ret = float(np.max(returns))
    min_ret = float(np.min(returns))
    avg_ret = float(np.mean(returns))

    # =====================================================
    # فیلترهای اختصاصی استراتژی
    # =====================================================

    if "covered_call" in name:
        return max_ret >= 0 and min_ret > -15.0

    elif "married_put" in name:
        return min_ret > -12.0 and max_ret > 0

    elif "collar" in name:
        return max_ret > 3.0 and min_ret > -10.0

    elif "bull_call_spread" in name:
        return max_ret > 8.0 and min_ret > -25.0 and avg_ret > 0

    elif "bear_put_spread" in name:
        return max_ret > 8.0 and min_ret > -25.0

    elif "long_straddle" in name or "long_strangle" in name:
        return max_ret > 25.0 or np.max(np.abs(returns)) > 35.0

    elif "strap" in name:
        return max_ret > 22.0 and min_ret > -28.0

    elif "strip" in name:
        return min_ret < -22.0 and max_ret < 32.0

    elif "long_box" in name or "conversion" in name:
        return min_ret > -5.0 and max_ret < 18.0 and avg_ret > 0

    elif "iron_condor" in name:
        mid = returns[len(returns)//4: 3*len(returns)//4]
        return np.mean(mid) > 0 and min_ret > -18.0

    # =====================================================
    # فیلترهای عمومی کاربر
    # =====================================================
    if "min_max_profit_pct" in user_conditions:
        if max_ret < user_conditions["min_max_profit_pct"]:
            return False

    if "max_max_loss_pct" in user_conditions:
        if min_ret < user_conditions["max_max_loss_pct"]:
            return False

    # فیلتر پیش‌فرض
    return max_ret >= -5.0


def filter_payoff_matrix_vectorized(
    strategy_names: List[str],
    returns_matrix: np.ndarray
) -> np.ndarray:
    """
    فیلتر برداری سریع روی ماتریس درصد بازدهی
    """
    num_strategies = len(strategy_names)
    keep_mask = np.ones(num_strategies, dtype=bool)

    for i in range(num_strategies):
        name = strategy_names[i].lower()
        rets = returns_matrix[i]

        if len(rets) == 0:
            keep_mask[i] = False
            continue

        max_r = float(np.max(rets))
        min_r = float(np.min(rets))

        if "covered_call" in name:
            keep_mask[i] = max_r >= 0 and min_r > -15
        elif "collar" in name:
            keep_mask[i] = max_r > 3 and min_r > -10
        elif "iron_condor" in name:
            keep_mask[i] = min_r > -18
        elif max_r < -8:   # فیلتر عمومی
            keep_mask[i] = False

    return keep_mask


def create_custom_filter(conditions: Dict[str, Any]) -> Callable[[Opportunity], bool]:
    """ایجاد فیلتر سفارشی"""
    def custom_filter(opp: Opportunity) -> bool:
        returns = np.array(opp.metadata.get(
            'returns_monthly_pct', []), dtype=float)
        if len(returns) == 0:
            return False

        if "strategy_contains" in conditions:
            if conditions["strategy_contains"].lower() not in opp.strategy_name.lower():
                return False

        if "min_max_profit_pct" in conditions:
            if float(np.max(returns)) < conditions["min_max_profit_pct"]:
                return False

        if "max_max_loss_pct" in conditions:
            if float(np.min(returns)) < conditions["max_max_loss_pct"]:
                return False

        return True

    return custom_filter


# دیکشنری فیلترهای آماده
STRATEGY_FILTERS = {
    "covered_call": lambda opp: apply_strategy_filter(opp),
    "collar": lambda opp: apply_strategy_filter(opp),
    "long_straddle": lambda opp: apply_strategy_filter(opp),
    "iron_condor": lambda opp: apply_strategy_filter(opp),
    "strap": lambda opp: apply_strategy_filter(opp),
    "strip": lambda opp: apply_strategy_filter(opp),
}

__all__ = [
    "apply_strategy_filter",
    "filter_payoff_matrix_vectorized",
    "create_custom_filter",
    "STRATEGY_FILTERS"
]
