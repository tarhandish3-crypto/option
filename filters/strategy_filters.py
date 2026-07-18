# filters/strategy_filters.py
# -*- coding: utf-8 -*-

"""
لایه فیلتر پویا و هوشمند بر اساس درصد بازدهی استراتژی - نسخه نهایی متناسب با معماری اصلی
"""

import logging
import numpy as np
from typing import Dict, Any

from core.models import Opportunity

logger = logging.getLogger("OptionScanner.Filters.StrategyFilters")


def get_dte_factor(days_to_maturity: int) -> float:
    """
    محاسبه ضریب تعدیل بر اساس زمان تا سررسید
    """
    # مبنا: ۳۰ روز (میانگین)
    BASE_DTE = 30
    # اگر DTE صفر یا نامشخص باشد، از ۳۰ استفاده کن
    if days_to_maturity <= 1:
        return 1.0
    
    # ضریب تعدیل: (DTE / BASE_DTE) ^ 0.5
    # استفاده از ریشه دوم برای کاهش اثر نوسانات شدید

    factor = min(2.5, (days_to_maturity / BASE_DTE) ** 0.5)
    return max(0.3, factor)


def apply_strategy_filter(opp: Opportunity, user_conditions: Dict[str, Any] = None) -> bool:
    """
    فیلتر اصلی هوشمند بر اساس درصد بازدهی روی شیء Opportunity
    """
    if user_conditions is None:
        user_conditions = {}

    name = opp.strategy_name.lower().strip()
    returns = np.array(opp.metadata.get('returns_monthly_pct', []), dtype=float)
    price_levels = np.array(opp.metadata.get("price_levels", []), dtype=float)
    spot_price = opp.S0_stock
    pct_changes = ((price_levels - spot_price) / spot_price) * 100

    if returns.size == 0:
        return False

    max_ret = float(np.max(returns))
    min_ret = float(np.min(returns))
    
    days_to_maturity = getattr(opp, 'days_to_maturity')
    dte_factor = get_dte_factor(days_to_maturity)

    # =====================================================
    # فیلترهای اختصاصی استراتژی
    # =====================================================

    # =====================================================
    # Bullish Strategies
    # =====================================================
    if "covered_call" in name:
        threshold = -15.0 * dte_factor
        indices = pct_changes >= threshold
        return np.all(returns[indices] >= 2)

    elif "married_put" in name:
        threshold = -10.0 * dte_factor
        indices = pct_changes >= threshold
        return np.all(returns[indices] >= 0)

    elif "bull_call_spread" in name:
        threshold = -15.0 * dte_factor
        indices = pct_changes >= threshold
        return np.all(returns[indices] >= 0)

    elif "bull_put_spread" in name:
        threshold = -15.0 * dte_factor
        indices = pct_changes >= threshold
        return np.all(returns[indices] >= 0)

    # =====================================================
    # Bearish Strategies
    # =====================================================
    elif "bear_put_spread" in name:
        threshold = 15.0 * dte_factor
        indices = pct_changes <= threshold
        return np.all(returns[indices] >= 0)

    elif "bear_call_spread" in name:
        threshold = 15.0 * dte_factor
        indices = pct_changes <= threshold
        return np.all(returns[indices] >= 0)

    # =====================================================
    # Neutral Strategies
    # =====================================================
    elif "iron_condor" in name:
        threshold = 10.0 * dte_factor
        indices = (
            (pct_changes >= -threshold) &
            (pct_changes <= threshold))
        return np.all(returns[indices] >= 0)

    elif "iron_butterfly" in name:
        threshold = 10.0 * dte_factor
        indices = (
            (pct_changes >= -threshold) &
            (pct_changes <= threshold))
        return np.all(returns[indices] >= 0)

    elif "short_straddle" in name:
        threshold = 8.0 * dte_factor
        indices = (
            (pct_changes >= -threshold) &
            (pct_changes <= threshold))
        return np.all(returns[indices] > 0)

    elif "short_strangle" in name:
        threshold = 12.0 * dte_factor
        indices = (
            (pct_changes >= -threshold) &
            (pct_changes <= threshold))
        return np.all(returns[indices] > 0)

    # =====================================================
    # Long Volatility Strategies
    # =====================================================
    elif "long_straddle" in name:
        threshold = 15.0 * dte_factor
        indices = (
            (pct_changes <= -threshold) |
            (pct_changes >= threshold))
        return np.all(returns[indices] > 0)

    elif "long_strangle" in name:
        threshold = 15.0 * dte_factor
        indices = (
            (pct_changes <= -threshold) |
            (pct_changes >= threshold))
        return np.all(returns[indices] > 0)

    elif "strip" in name:
        neg = -10.0 * dte_factor
        pos = 15.0 * dte_factor
        indices = (
            (pct_changes <= neg) |
            (pct_changes >= pos))
        return np.all(returns[indices] > 0)

    elif "strap" in name:
        neg = -15.0 * dte_factor
        pos = 10.0 * dte_factor
        indices = (
            (pct_changes <= neg) |
            (pct_changes >= pos))
        return np.all(returns[indices] > 0)


    # =====================================================
    # Arbitrage Strategies
    # =====================================================
    elif "long_box" in name or "conversion" in name:
        threshold = 2.0 * dte_factor
        indices = (pct_changes >= -threshold) & (pct_changes <= threshold)
        return np.all(returns[indices] >= 0) if np.any(indices) else False

    # فیلتر پیش‌فرض
    default_loss_threshold = -2.0 * dte_factor 
    return max_ret >= -2.0 and min_ret > default_loss_threshold