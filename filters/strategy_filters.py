# filters/strategy_filters.py
# -*- coding: utf-8 -*-

"""
موتور فیلتر هوشمند بر اساس دامنه‌های سودآوری و حدود تغییر قیمت دارایی پایه
(تنظیم مستقیم بازه‌های سوددهی، حد افت مجاز و حداقل درصد بازدهی توسط کاربر)
"""

import logging
import numpy as np
from typing import Dict, Any, Optional

from core.models import Opportunity


logger = logging.getLogger("OptionScanner.Filters.StrategyFilters")


def get_dte_factor(days_to_maturity: int) -> float:
    """محاسبه ضریب تعدیل DTE بر مبنای ۳۰ روز"""
    BASE_DTE = 30
    if days_to_maturity <= 1:
        return 1.0
    factor = min(2.5, (days_to_maturity / BASE_DTE) ** 0.5)
    return max(0.3, factor)


def get_default_filter_config() -> Dict[str, Dict[str, Any]]:
    """
    تنظیمات پیش‌فرض بازه و شروط سودآوری برای تمام استراتژی‌ها
    rule_type:
      - 'outside_range': سوددهی بیرون از بازه [min_pct, max_pct] (مانند Strap, Straddle, Volatility)
      - 'inside_range': سوددهی داخل بازه [min_pct, max_pct] (مانند Iron Condor, Short Straddle, Arbitrage)
      - 'above_level': سوددهی در قیمت‌های بالاتر از min_pct (مانند Bull Spreads, Long Call, Covered Call)
      - 'below_level': سوددهی در قیمت‌های پایین‌تر از max_pct (مانند Bear Spreads, Long Put, Short Call)
    """
    return {
        # ۱. استراتژی‌های نوسانی و دوجهته
        "strap": {
            "enabled": True,
            "rule_type": "outside_range",
            "loss_range_min": -5.0,     # از ۵-٪ تا ۵+٪ مجاز به زیان، بیرون از این بازه حتماً سود
            "loss_range_max": 5.0,
            "min_profit_pct": 2.0,      # حداقل درصد سود در ناحیه مثبت
            "use_dte_factor": True
        },
        "strip": {
            "enabled": True,
            "rule_type": "outside_range",
            "loss_range_min": -5.0,
            "loss_range_max": 5.0,
            "min_profit_pct": 2.0,
            "use_dte_factor": True
        },
        "long_straddle": {
            "enabled": True,
            "rule_type": "outside_range",
            "loss_range_min": -7.0,
            "loss_range_max": 7.0,
            "min_profit_pct": 2.0,
            "use_dte_factor": True
        },
        "long_strangle": {
            "enabled": True,
            "rule_type": "outside_range",
            "loss_range_min": -9.0,
            "loss_range_max": 9.0,
            "min_profit_pct": 2.0,
            "use_dte_factor": True
        },
        "long_guts": {
            "enabled": True,
            "rule_type": "outside_range",
            "loss_range_min": -8.0,
            "loss_range_max": 8.0,
            "min_profit_pct": 2.0,
            "use_dte_factor": True
        },

        # ۲. استراتژی‌های صعودی و درآمدی
        "covered_call": {
            "enabled": True,
            "rule_type": "above_level",
            "profit_above_pct": -4.5,   # تا ۴.۵-٪ افت سهم همچنان بدون زیان، و بالاتر از ۰٪ سود کامل
            "min_profit_pct": 2.5,
            "use_dte_factor": True
        },
        "bull_call_spread": {
            "enabled": True,
            "rule_type": "above_level",
            "profit_above_pct": 3.0,    # در رشد بالای ۳٪ باید سودده باشد
            "min_profit_pct": 5.0,
            "use_dte_factor": True
        },
        "bull_put_spread": {
            "enabled": True,
            "rule_type": "above_level",
            "profit_above_pct": -4.0,
            "min_profit_pct": 3.0,
            "use_dte_factor": True
        },
        "long_call": {
            "enabled": True,
            "rule_type": "above_level",
            "profit_above_pct": 4.0,
            "min_profit_pct": 15.0,
            "use_dte_factor": True
        },
        "short_put": {
            "enabled": True,
            "rule_type": "above_level",
            "profit_above_pct": -5.0,
            "min_profit_pct": 2.5,
            "use_dte_factor": True
        },
        "collar": {
            "enabled": True,
            "rule_type": "above_level",
            "profit_above_pct": -5.0,
            "min_profit_pct": 2.0,
            "use_dte_factor": True
        },
        "married_put": {
            "enabled": True,
            "rule_type": "above_level",
            "profit_above_pct": 2.0,
            "min_profit_pct": 4.0,
            "use_dte_factor": True
        },

        # ۳. استراتژی‌های نزولی
        "bear_put_spread": {
            "enabled": True,
            "rule_type": "below_level",
            "profit_below_pct": -3.0,   # در افت زیر ۳-٪ باید سودده باشد
            "min_profit_pct": 5.0,
            "use_dte_factor": True
        },
        "bear_call_spread": {
            "enabled": True,
            "rule_type": "below_level",
            "profit_below_pct": 4.0,
            "min_profit_pct": 3.0,
            "use_dte_factor": True
        },
        "long_put": {
            "enabled": True,
            "rule_type": "below_level",
            "profit_below_pct": -4.0,
            "min_profit_pct": 15.0,
            "use_dte_factor": True
        },
        "short_call": {
            "enabled": True,
            "rule_type": "below_level",
            "profit_below_pct": 5.0,
            "min_profit_pct": 2.5,
            "use_dte_factor": True
        },

        # ۴. استراتژی‌های خنثی و بدون جهت
        "iron_condor": {
            "enabled": True,
            "rule_type": "inside_range",
            "profit_range_min": -8.0,   # در بازه ۸-٪ تا ۸+٪ باید حتماً سودده باشد
            "profit_range_max": 8.0,
            "min_profit_pct": 3.0,
            "use_dte_factor": True
        },
        "iron_butterfly": {
            "enabled": True,
            "rule_type": "inside_range",
            "profit_range_min": -6.0,
            "profit_range_max": 6.0,
            "min_profit_pct": 4.0,
            "use_dte_factor": True
        },
        "short_straddle": {
            "enabled": True,
            "rule_type": "inside_range",
            "profit_range_min": -6.0,
            "profit_range_max": 6.0,
            "min_profit_pct": 4.0,
            "use_dte_factor": True
        },
        "short_strangle": {
            "enabled": True,
            "rule_type": "inside_range",
            "profit_range_min": -8.0,
            "profit_range_max": 8.0,
            "min_profit_pct": 3.5,
            "use_dte_factor": True
        },

        # ۵. آربیتراژ
        "conversion": {
            "enabled": True,
            "rule_type": "inside_range",
            "profit_range_min": -45.0,
            "profit_range_max": 45.0,
            "min_profit_pct": 0.0,
            "use_dte_factor": False
        },
        "long_box": {
            "enabled": True,
            "rule_type": "inside_range",
            "profit_range_min": -45.0,
            "profit_range_max": 45.0,
            "min_profit_pct": 0.0,
            "use_dte_factor": False
        },
    }


def apply_strategy_filter(opp: Opportunity, user_conditions: Optional[Dict[str, Any]] = None) -> bool:
    """
    اعمال دقیق فیلتر بر اساس بازه و شروط تعریف‌شده توسط کاربر
    """
    if user_conditions is None:
        user_conditions = {}

    name = str(getattr(opp, 'strategy_name', '')).lower().strip()
    metadata = getattr(opp, 'metadata', {}) or {}

    returns = np.array(metadata.get('returns_monthly_pct', []), dtype=float)
    if returns.size == 0:
        returns = np.array(metadata.get('net_returns_closed', []), dtype=float)

    if returns.size == 0:
        return False

    price_levels = np.array(metadata.get("price_levels", []), dtype=float)
    spot_price = float(getattr(opp, 'underlying_price', 0.0)
                       or getattr(opp, 'S0_stock', 0.0) or 0.0)

    if spot_price > 0 and price_levels.size == returns.size:
        pct_changes = ((price_levels - spot_price) / spot_price) * 100.0
    else:
        pct_changes = np.linspace(-45.0, 45.0, returns.size)

    days_to_maturity = int(getattr(opp, 'days_to_maturity', 30) or 30)
    dte_factor = get_dte_factor(days_to_maturity)

    strat_key = _match_strategy_key(name)
    defaults = get_default_filter_config().get(strat_key, {})
    cfg = user_conditions.get(
        strat_key, defaults) if user_conditions else defaults

    if not cfg.get("enabled", True):
        return True

    use_dte = cfg.get("use_dte_factor", True)
    f = dte_factor if use_dte else 1.0
    rule_type = cfg.get("rule_type", defaults.get(
        "rule_type", "outside_range"))
    min_profit = float(cfg.get("min_profit_pct", 2.0))

    # ۱. قانون بیرون از بازه (Outside Range) - مانند Strap/Strip/Straddle
    if rule_type == "outside_range":
        loss_min = float(cfg.get("loss_range_min", -5.0)) * f
        loss_max = float(cfg.get("loss_range_max", 5.0)) * f

        outside_indices = (pct_changes <= loss_min) | (pct_changes >= loss_max)
        if not np.any(outside_indices):
            return False
        # تمام نقاط خارج از بازه باید سودده باشند
        return bool(np.all(returns[outside_indices] >= min_profit))

    # ۲. قانون داخل بازه (Inside Range) - مانند Iron Condor / Neutral / Arbitrage
    elif rule_type == "inside_range":
        p_min = float(cfg.get("profit_range_min", -8.0)) * f
        p_max = float(cfg.get("profit_range_max", 8.0)) * f

        inside_indices = (pct_changes >= p_min) & (pct_changes <= p_max)
        if not np.any(inside_indices):
            return False
        return bool(np.all(returns[inside_indices] >= min_profit))

    # ۳. قانون رشد بالاتر از سطح (Above Level) - مانند Bull Spreads / Covered Call
    elif rule_type == "above_level":
        above_val = float(cfg.get("profit_above_pct", -4.5)) * f
        indices = pct_changes >= above_val
        if not np.any(indices):
            return False
        return bool(np.all(returns[indices] >= min_profit))

    # ۴. قانون افت پایین‌تر از سطح (Below Level) - مانند Bear Spreads / Long Put
    elif rule_type == "below_level":
        below_val = float(cfg.get("profit_below_pct", -3.0)) * f
        indices = pct_changes <= below_val
        if not np.any(indices):
            return False
        return bool(np.all(returns[indices] >= min_profit))

    return bool(np.max(returns) >= min_profit)


def _match_strategy_key(name: str) -> str:
    keys = [
        "covered_call", "bull_call_spread", "bear_put_spread", "bull_put_spread",
        "bear_call_spread", "iron_condor", "iron_butterfly", "short_straddle", "short_strangle",
        "long_straddle", "long_strangle", "long_guts", "strap", "strip",
        "collar", "married_put", "long_call", "short_call", "long_put",
        "short_put", "conversion", "long_box"
    ]
    for k in keys:
        if k in name:
            return k
    return "strap"
