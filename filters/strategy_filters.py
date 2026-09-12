# filters/strategy_filters.py
# -*- coding: utf-8 -*-

"""
موتور فیلتر هوشمند بر اساس دامنه‌های سودآوری و حدود تغییر قیمت دارایی پایه
با قابلیت بالانس پویای بازه‌ها بر اساس روز تا سررسید (DTE Dynamic Scaling)
"""

from __future__ import annotations

import logging
import re
from typing import Dict, Any, Optional
import numpy as np

from core.models import Opportunity


logger = logging.getLogger("OptionScanner.Filters.StrategyFilters")

# =========================================================================
# نگاشت نام‌های فارسی و استانداردسازی کلیدها
# =========================================================================

PERSIAN_STRATEGY_ALIASES: Dict[str, str] = {
    "کاورکال": "covered_call",
    "کاور_کال": "covered_call",
    "اختیار_خرید_پوشش_داده_شده": "covered_call",
    "اسپرد_صعودی_خرید": "bull_call_spread",
    "بول_کال_اسپرد": "bull_call_spread",
    "اسپرد_صعودی_فروش": "bull_put_spread",
    "بول_پوت_اسپرد": "bull_put_spread",
    "اسپرد_نزولی_خرید": "bear_put_spread",
    "بیر_پوت_اسپرد": "bear_put_spread",
    "اسپرد_نزولی_فروش": "bear_call_spread",
    "بیر_کال_اسپرد": "bear_call_spread",
    "کندور_آهنی": "iron_condor",
    "پروانه_آهنی": "iron_butterfly",
    "استرادل": "long_straddle",
    "استرانگل": "long_strangle",
    "کالار": "collar",
    "مرید_پوت": "married_put",
    "کانورژن": "conversion",
    "باکس": "long_box",
    "استرپ": "strap",
    "استریپ": "strip",
    "لانگ_کال": "long_call",
    "شورت_کال": "short_call",
    "لانگ_پوت": "long_put",
    "شورت_پوت": "short_put",
    "لانگ_گاتس": "long_guts",
}

# لیست کلیدها مرتب‌شده از طولانی‌ترین به کوتاه‌ترین جهت جلوگیری از خطای تطبیق زیررشته‌ها
KNOWN_STRATEGY_KEYS = sorted(
    [
        "bear_call_spread",
        "bull_call_spread",
        "bear_put_spread",
        "bull_put_spread",
        "iron_butterfly",
        "short_straddle",
        "short_strangle",
        "long_straddle",
        "long_strangle",
        "covered_call",
        "iron_condor",
        "married_put",
        "conversion",
        "short_call",
        "short_put",
        "long_call",
        "long_guts",
        "long_put",
        "long_box",
        "collar",
        "strap",
        "strip",
    ],
    key=len,
    reverse=True,
)


def get_dte_factor(days_to_maturity: int, base_dte: float = 30.0) -> float:
    """
    محاسبه ضریب تعدیل پویا بر اساس جذر زمان (sqrt(DTE / 30))
    مبنای استانداردهای ورودی کاربر دوره ۳۰ روزه (۱ ماه) در نظر گرفته می‌شود.
    """
    if days_to_maturity <= 1:
        return 0.3
    factor = (float(days_to_maturity) / base_dte) ** 0.5
    return float(np.clip(factor, 0.3, 2.5))


def get_default_filter_config() -> Dict[str, Dict[str, Any]]:
    """
    تنظیمات پیش‌فرض بازه و شروط سودآوری برای ۲۲ استراتژی سیستم
    """
    return {
        # ۱. استراتژی‌های نوسانی و دوجهته
        "strap": {
            "enabled": True,
            "rule_type": "outside_range",
            "loss_range_min": -5.0,
            "loss_range_max": 5.0,
            "min_profit_pct": 2.0,
            "use_dte_factor": True,
        },
        "strip": {
            "enabled": True,
            "rule_type": "outside_range",
            "loss_range_min": -5.0,
            "loss_range_max": 5.0,
            "min_profit_pct": 2.0,
            "use_dte_factor": True,
        },
        "long_straddle": {
            "enabled": True,
            "rule_type": "outside_range",
            "loss_range_min": -7.0,
            "loss_range_max": 7.0,
            "min_profit_pct": 2.0,
            "use_dte_factor": True,
        },
        "long_strangle": {
            "enabled": True,
            "rule_type": "outside_range",
            "loss_range_min": -9.0,
            "loss_range_max": 9.0,
            "min_profit_pct": 2.0,
            "use_dte_factor": True,
        },
        "long_guts": {
            "enabled": True,
            "rule_type": "outside_range",
            "loss_range_min": -8.0,
            "loss_range_max": 8.0,
            "min_profit_pct": 2.0,
            "use_dte_factor": True,
        },

        # ۲. استراتژی‌های صعودی و درآمدی
        "covered_call": {
            "enabled": True,
            "rule_type": "above_level",
            "profit_above_pct": -4.5,
            "min_profit_pct": 2.5,
            "use_dte_factor": True,
        },
        "bull_call_spread": {
            "enabled": True,
            "rule_type": "above_level",
            "profit_above_pct": 3.0,
            "min_profit_pct": 5.0,
            "use_dte_factor": True,
        },
        "bull_put_spread": {
            "enabled": True,
            "rule_type": "above_level",
            "profit_above_pct": -4.0,
            "min_profit_pct": 3.0,
            "use_dte_factor": True,
        },
        "long_call": {
            "enabled": True,
            "rule_type": "above_level",
            "profit_above_pct": 4.0,
            "min_profit_pct": 15.0,
            "use_dte_factor": True,
        },
        "short_put": {
            "enabled": True,
            "rule_type": "above_level",
            "profit_above_pct": -5.0,
            "min_profit_pct": 2.5,
            "use_dte_factor": True,
        },
        "collar": {
            "enabled": True,
            "rule_type": "above_level",
            "profit_above_pct": -5.0,
            "min_profit_pct": 2.0,
            "use_dte_factor": True,
        },
        "married_put": {
            "enabled": True,
            "rule_type": "above_level",
            "profit_above_pct": 2.0,
            "min_profit_pct": 4.0,
            "use_dte_factor": True,
        },

        # ۳. استراتژی‌های نزولی
        "bear_put_spread": {
            "enabled": True,
            "rule_type": "below_level",
            "profit_below_pct": -3.0,
            "min_profit_pct": 5.0,
            "use_dte_factor": True,
        },
        "bear_call_spread": {
            "enabled": True,
            "rule_type": "below_level",
            "profit_below_pct": 4.0,
            "min_profit_pct": 3.0,
            "use_dte_factor": True,
        },
        "long_put": {
            "enabled": True,
            "rule_type": "below_level",
            "profit_below_pct": -4.0,
            "min_profit_pct": 15.0,
            "use_dte_factor": True,
        },
        "short_call": {
            "enabled": True,
            "rule_type": "below_level",
            "profit_below_pct": 5.0,
            "min_profit_pct": 2.5,
            "use_dte_factor": True,
        },

        # ۴. استراتژی‌های خنثی و بدون جهت
        "iron_condor": {
            "enabled": True,
            "rule_type": "inside_range",
            "profit_range_min": -8.0,
            "profit_range_max": 8.0,
            "min_profit_pct": 3.0,
            "use_dte_factor": True,
        },
        "iron_butterfly": {
            "enabled": True,
            "rule_type": "inside_range",
            "profit_range_min": -6.0,
            "profit_range_max": 6.0,
            "min_profit_pct": 4.0,
            "use_dte_factor": True,
        },
        "short_straddle": {
            "enabled": True,
            "rule_type": "inside_range",
            "profit_range_min": -6.0,
            "profit_range_max": 6.0,
            "min_profit_pct": 4.0,
            "use_dte_factor": True,
        },
        "short_strangle": {
            "enabled": True,
            "rule_type": "inside_range",
            "profit_range_min": -8.0,
            "profit_range_max": 8.0,
            "min_profit_pct": 3.5,
            "use_dte_factor": True,
        },

        # ۵. آربیتراژ (مستقل از زمان)
        "conversion": {
            "enabled": True,
            "rule_type": "inside_range",
            "profit_range_min": -45.0,
            "profit_range_max": 45.0,
            "min_profit_pct": 0.0,
            "use_dte_factor": False,
        },
        "long_box": {
            "enabled": True,
            "rule_type": "inside_range",
            "profit_range_min": -45.0,
            "profit_range_max": 45.0,
            "min_profit_pct": 0.0,
            "use_dte_factor": False,
        },
    }


def _match_strategy_key(name: str) -> Optional[str]:
    """
    تطبیق هوشمند و ایمن نام استراتژی با کلیدهای استاندارد
    """
    if not name or not isinstance(name, str):
        return None

    cleaned_name = name.lower().strip()
    norm_name = re.sub(r"[\s\-]+", "_", cleaned_name)

    # بررسی تطابق با اسامی فارسی
    for fa_key, en_key in PERSIAN_STRATEGY_ALIASES.items():
        if fa_key in norm_name:
            return en_key

    # بررسی تطابق دقیق
    if norm_name in KNOWN_STRATEGY_KEYS:
        return norm_name

    # بررسی تطابق زیررشته‌ای بر مبنای اولویت طول کلمه
    for k in KNOWN_STRATEGY_KEYS:
        if k in norm_name:
            return k

    return None


def apply_strategy_filter(
    opp: Opportunity, user_conditions: Optional[Dict[str, Any]] = None
) -> bool:
    """
    اعمال دقیق فیلتر بر اساس بازه و شروط تعریف‌شده توسط کاربر
    با بالانس پویای بازه‌ها بر اساس DTE
    """
    if user_conditions is None:
        user_conditions = {}

    name = str(getattr(opp, "strategy_name", "")).lower().strip()
    metadata = getattr(opp, "metadata", {}) or {}

    # اولویت با بازدهی تا سررسید و سپس بازدهی ماهانه‌شده
    raw_returns = metadata.get("net_returns_closed")
    if raw_returns is None or len(raw_returns) == 0:
        raw_returns = metadata.get("returns_monthly_pct")

    if raw_returns is None or len(raw_returns) == 0:
        return False

    returns = np.asarray(raw_returns, dtype=np.float32)

    strat_key = _match_strategy_key(name)
    if not strat_key:
        # اگر استراتژی ناشناخته باشد، بررسی حداقل یک نقطه سودآور
        return bool(np.max(returns) > 0.0)

    defaults = get_default_filter_config().get(strat_key, {})
    cfg = user_conditions.get(strat_key, defaults) if user_conditions else defaults

    if not cfg.get("enabled", True):
        return True

    price_levels = metadata.get("price_levels")
    spot_price = float(
        getattr(opp, "underlying_price", 0.0)
        or getattr(opp, "S0_stock", 0.0)
        or 0.0
    )

    if spot_price > 0 and price_levels is not None and len(price_levels) == len(returns):
        pct_changes = ((np.asarray(price_levels, dtype=np.float32) - spot_price) / spot_price) * 100.0
    else:
        pct_changes = np.linspace(-45.0, 45.0, len(returns), dtype=np.float32)

    days_to_maturity = int(getattr(opp, "days_to_maturity", 30) or 30)
    use_dte = cfg.get("use_dte_factor", defaults.get("use_dte_factor", True))
    f = get_dte_factor(days_to_maturity) if use_dte else 1.0

    rule_type = cfg.get("rule_type", defaults.get("rule_type", "outside_range"))
    min_profit = float(cfg.get("min_profit_pct", defaults.get("min_profit_pct", 2.0)))

    # ۱. قانون بیرون از بازه (Outside Range) - نوسان‌گیری (Strap/Strip/Straddle/Strangle)
    if rule_type == "outside_range":
        loss_min = float(cfg.get("loss_range_min", defaults.get("loss_range_min", -7.0))) * f
        loss_max = float(cfg.get("loss_range_max", defaults.get("loss_range_max", 7.0))) * f

        outside_indices = (pct_changes <= loss_min) | (pct_changes >= loss_max)
        if not np.any(outside_indices):
            return False
        return bool(np.all(returns[outside_indices] >= min_profit))

    # ۲. قانون داخل بازه (Inside Range) - خنثی و آربیتراژ (Iron Condor / Butterfly / Arbitrage)
    elif rule_type == "inside_range":
        p_min = float(cfg.get("profit_range_min", defaults.get("profit_range_min", -8.0))) * f
        p_max = float(cfg.get("profit_range_max", defaults.get("profit_range_max", 8.0))) * f

        inside_indices = (pct_changes >= p_min) & (pct_changes <= p_max)
        if not np.any(inside_indices):
            return False
        return bool(np.all(returns[inside_indices] >= min_profit))

    # ۳. قانون رشد بالاتر از سطح (Above Level) - صعودی و کاورکال
    elif rule_type == "above_level":
        above_val = float(cfg.get("profit_above_pct", defaults.get("profit_above_pct", -4.5))) * f

        if above_val < 0:
            # استراتژی‌های درآمدی اعتباری (Covered Call / Short Put / Collar)
            target_indices = pct_changes >= 0.0
            buffer_indices = (pct_changes >= above_val) & (pct_changes < 0.0)

            cond_profit = np.all(returns[target_indices] >= min_profit) if np.any(target_indices) else True
            cond_buffer = np.all(returns[buffer_indices] >= 0.0) if np.any(buffer_indices) else True
            return bool(cond_profit and cond_buffer)
        else:
            # استراتژی‌های صعودی اهرمی (Bull Call Spread / Long Call)
            indices = pct_changes >= above_val
            if not np.any(indices):
                return False
            return bool(np.max(returns[indices]) >= min_profit)

    # ۴. قانون افت پایین‌تر از سطح (Below Level) - نزولی
    elif rule_type == "below_level":
        below_val = float(cfg.get("profit_below_pct", defaults.get("profit_below_pct", -3.0))) * f

        if below_val > 0:
            # استراتژی‌های نزولی اعتباری (Bear Call Spread / Short Call)
            target_indices = pct_changes <= 0.0
            buffer_indices = (pct_changes <= below_val) & (pct_changes > 0.0)

            cond_profit = np.all(returns[target_indices] >= min_profit) if np.any(target_indices) else True
            cond_buffer = np.all(returns[buffer_indices] >= 0.0) if np.any(buffer_indices) else True
            return bool(cond_profit and cond_buffer)
        else:
            # استراتژی‌های نزولی اهرمی (Bear Put Spread / Long Put)
            indices = pct_changes <= below_val
            if not np.any(indices):
                return False
            return bool(np.max(returns[indices]) >= min_profit)

    return bool(np.max(returns) >= min_profit)