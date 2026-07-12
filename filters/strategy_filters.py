# filters/strategy_filters.py
# -*- coding: utf-8 -*-

"""
لایه فیلتر پویا و هوشمند بر اساس درصد بازدهی استراتژی - نسخه نهایی متناسب با معماری اصلی
"""

import logging
import numpy as np
from typing import List, Dict, Any, Callable

from core.models import Opportunity

logger = logging.getLogger("OptionScanner.Filters.StrategyFilters")


def get_dte_factor(days_to_maturity: int) -> float:
    """
    محاسبه ضریب تعدیل بر اساس زمان تا سررسید
    """
    # مبنا: ۳۰ روز (میانگین)
    BASE_DTE = 30
    # اگر DTE صفر یا نامشخص باشد، از ۳۰ استفاده کن
    if days_to_maturity <= 0:
        return 1.0
    
    # ضریب تعدیل: (DTE / BASE_DTE) ^ 0.5
    # استفاده از ریشه دوم برای کاهش اثر نوسانات شدید
    return min(2.0 , (days_to_maturity / BASE_DTE) ** 0.5)


def apply_strategy_filter(opp: Opportunity, user_conditions: Dict[str, Any] = None) -> bool:
    """
    فیلتر اصلی هوشمند بر اساس درصد بازدهی روی شیء Opportunity
    """
    if user_conditions is None:
        user_conditions = {}

    name = opp.strategy_name.lower().strip()
    returns = np.array(opp.metadata.get('returns_monthly_pct', []), dtype=float)

    if returns.size == 0:
        return False

    max_ret = float(np.max(returns))
    min_ret = float(np.min(returns))
    
    days_to_maturity = getattr(opp, 'days_to_maturity')
    dte_factor = get_dte_factor(days_to_maturity)

    # =====================================================
    # فیلترهای اختصاصی استراتژی
    # =====================================================
    if "covered_call" in name:
        max_loss_threshold = -15.0 * dte_factor 
        return max_ret >= 0 and min_ret > max_loss_threshold

    elif "married_put" in name:
        max_loss_threshold = -12.0 * dte_factor 
        return min_ret > max_loss_threshold and max_ret > 0

    elif "collar" in name:
        min_profit_threshold = 3.0 * dte_factor 
        max_loss_threshold = -10.0 * dte_factor 
        return max_ret > min_profit_threshold and min_ret > max_loss_threshold

    elif "bull_call_spread" in name or "bear_put_spread" in name:
        min_profit_threshold = 8.0 * dte_factor 
        max_loss_threshold = -25.0 * dte_factor 
        return max_ret > min_profit_threshold and min_ret > max_loss_threshold

    elif "long_straddle" in name or "long_strangle" in name:
        # if opp.metadata['l2_ticker'] == 'ضملت4022':
        #     pass
        min_profit_threshold = 25.0 * dte_factor 
        max_move_threshold = 35.0 * dte_factor 
        return max_ret > min_profit_threshold or np.max(np.abs(returns)) > max_move_threshold

    elif "strap" in name:
        min_profit_threshold = 22.0 * dte_factor 
        max_loss_threshold = -28.0 * dte_factor 
        return max_ret > min_profit_threshold and min_ret > max_loss_threshold

    elif "strip" in name:
        max_loss_threshold = -22.0 * dte_factor 
        max_profit_threshold = 32.0 * dte_factor 
        return min_ret < max_loss_threshold and max_ret < max_profit_threshold

    elif "long_box" in name or "conversion" in name:
        max_loss_threshold = -5.0 * dte_factor 
        max_profit_threshold = 15.0 * dte_factor 
        return min_ret > max_loss_threshold and max_ret < max_profit_threshold

    elif "iron_condor" in name:
        # فیلتر هوشمند بر اساس بخش میانی توزیع
        max_loss_threshold = -18.0 * dte_factor 
        mid = returns[returns.size // 4 : 3 * returns.size // 4]
        return np.mean(mid) > 0 and min_ret > max_loss_threshold
        

    # =====================================================
    # فیلترهای عمومی کاربر
    # =====================================================
    if "min_max_profit_pct" in user_conditions:
            # کاربر ممکن است سود ماهانه را مشخص کند
        if max_ret < user_conditions["min_max_profit_pct"]:
            return False

    if "max_max_loss_pct" in user_conditions:
        if min_ret < user_conditions["max_max_loss_pct"]:
            return False

    # فیلتر پیش‌فرض
    default_loss_threshold = -2.0 * dte_factor 
    return max_ret >= -2.0 and min_ret > default_loss_threshold


def filter_payoff_matrix_vectorized(
    strategy_names: List[str],
    returns_matrix: np.ndarray) -> np.ndarray:
    """
    فیلتر برداری سریع روی ماتریس درصد بازدهی برای غربالگری دسته‌ای
    """
    num = len(strategy_names)
    keep = np.ones(num, dtype=bool)
    
    dtes = [30] * num

    for i in range(num):
        name = strategy_names[i].lower()
        rets = returns_matrix[i]
        dte = dtes[i] if i < len(dtes) else 30

        if rets.size == 0:
            keep[i] = False
            continue

        max_r = float(np.max(rets))
        min_r = float(np.min(rets))
        # فیلترهای پویا بر اساس DTE
        max_loss_threshold = -15.0 * (dte / 30.0)
        min_profit_threshold = 3.0 * (30.0 / dte) if dte > 0 else 3.0

        if "covered_call" in name:
            keep[i] = max_r >= 0 and min_r > max_loss_threshold
        elif "collar" in name:
            keep[i] = max_r > min_profit_threshold and min_r > max_loss_threshold
        elif "iron_condor" in name:
            max_loss_threshold_ic = -18.0 * (dte / 30.0)
            keep[i] = min_r > max_loss_threshold_ic
        elif "strap" in name:
            min_profit_threshold_s = 22.0 * (30.0 / dte) if dte > 0 else 22.0
            max_loss_threshold_s = -28.0 * (dte / 30.0)
            keep[i] = max_r > min_profit_threshold_s and min_r > max_loss_threshold_s
        elif "strip" in name:
            max_loss_threshold_st = -22.0 * (dte / 30.0)
            max_profit_threshold_st = 32.0 * (30.0 / dte) if dte > 0 else 32.0
            keep[i] = min_r < max_loss_threshold_st and max_r < max_profit_threshold_st
        elif max_r < -8.0:
            keep[i] = False

    return keep


def create_custom_filter(conditions: Dict[str, Any]) -> Callable[[Opportunity], bool]:
    """ایجاد فیلتر سفارشی روی Opportunity"""
    def custom_filter(opp: Opportunity) -> bool:
        returns = np.array(opp.metadata.get('returns_monthly_pct', []), dtype=float)
        if returns.size == 0:
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