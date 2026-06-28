# strategies/config.py

"""
تنظیمات استراتژی‌ها (Strategies Configuration)

این فایل شامل تنظیمات مربوط به استراتژی‌های فعال، سیاست‌های بستن سهم،
و تنظیمات نمایش برای فیلترهای داینامیک می‌باشد.
"""

from typing import Dict, List

# =====================================================
# استراتژی‌های فعال (Active Strategies)
# =====================================================

TARGET_STRATEGIES: List[str] = [
    # ----- استراتژی‌های تک لگی (Single-Leg) -----
    'long_call',
    # 'short_call',
    'long_put',
    # 'short_put',

    # ----- استراتژی‌های پوششی (Hedging) -----
    'covered_call',
    'married_put',
    'collar',

    # ----- استراتژی‌های اسپرد (Spreads) -----
    'bull_call_spread',
    # 'bear_call_spread',
    'bear_put_spread',
    # 'bull_put_spread',

    # ----- استراتژی‌های نوسانی (Volatility) -----
    'long_straddle',
    # 'short_straddle',
    'long_strangle',
    # 'short_strangle',
    'long_guts',

    # ----- استراتژی‌های چندلگی نوسانی -----
    'strip',
    'strap',

    # ----- استراتژی‌های خنثی (Neutral) -----
    'conversion',
    'long_box',
    # 'iron_condor',
]

# =====================================================
# سیاست بستن سهم در سررسید (Close Stock Policy)
# =====================================================
# True  = سهم در سررسید به‌صورت اتوماتیک بسته/فروخته می‌شود
# False = سهم نگه داشته می‌شود تا طرف مقابل exercise کند

CLOSE_STOCK_POLICY: Dict[str, bool] = {
    # ----- استراتژی‌های تک لگی (Single-Leg) -----
    "long_call": True,      # بدون سهم پایه، اتوماتیک بسته می‌شود
    "short_call": True,     # بدون سهم پایه، اتوماتیک بسته می‌شود
    "long_put": True,       # بدون سهم پایه، اتوماتیک بسته می‌شود
    "short_put": True,      # بدون سهم پایه، اتوماتیک بسته می‌شود

    # ----- استراتژی‌های پوششی (Hedging) -----
    "covered_call": False,  # نیاز به نگه داشتن سهم پایه
    "married_put": False,   # نیاز به نگه داشتن سهم پایه
    "collar": True,         # معمولاً سهم پایه بسته می‌شود

    # ----- استراتژی‌های اسپرد (Spreads) -----
    "bull_call_spread": True,
    "bear_call_spread": True,
    "bull_put_spread": True,
    "bear_put_spread": True,

    # ----- استراتژی‌های نوسانی (Volatility) -----
    "long_straddle": True,
    "short_straddle": True,
    "long_strangle": True,
    "short_strangle": True,
    "long_guts": True,

    # ----- استراتژی‌های چندلگی نوسانی -----
    "strip": True,
    "strap": True,

    # ----- استراتژی‌های خنثی (Neutral) -----
    "conversion": False,
    "long_box": True,
    "iron_condor": True,
}

# =====================================================
# تنظیمات نمایش برای فیلترهای داینامیک (Dynamic Range Config)
# =====================================================
# برای هر استراتژی، نقاطی که سودآوری در آن‌ها بررسی می‌شود

STRATEGY_CONFIG: Dict[str, List[int]] = {
    # ----- استراتژی‌های تک لگی -----
    "long_call": [-4, 0, 4],
    "short_call": [-4, 0, 4],
    "long_put": [-4, 0, 4],
    "short_put": [-4, 0, 4],

    # ----- استراتژی‌های پوششی -----
    "covered_call": [-6, 0, 5],
    "married_put": [0, 5],
    "collar": [-5, 5],

    # ----- استراتژی‌های اسپرد -----
    "bull_call_spread": [-8, 0, 7],
    "bear_call_spread": [-7, 0, 7],
    "bear_put_spread": [-7, 0, 7],
    "bull_put_spread": [-7, 0, 7],

    # ----- استراتژی‌های نوسانی -----
    "long_straddle": [-5, 5],
    "short_straddle": [-5, 5],
    "long_strangle": [-5, 5],
    "short_strangle": [-5, 5],
    "long_guts": [-5, 0, 5],

    # ----- استراتژی‌های چندلگی نوسانی -----
    "strap": [-7, -5, 5, 7],
    "strip": [-7, -5, 5, 7],

    # ----- استراتژی‌های خنثی -----
    "conversion": [-4, 0, 4],
    "long_box": [-4, 0, 4],
    "iron_condor": [-6, -2, 2, 6],
}

# =====================================================
# تابع کمکی برای دریافت تنظیمات
# =====================================================

def get_strategy_config(strategy_name: str) -> List[int]:
    """
    دریافت تنظیمات نمایش یک استراتژی خاص
    
    Args:
        strategy_name: نام استراتژی
        
    Returns:
        لیست نقاط درصدی برای بررسی سودآوری
    """
    return STRATEGY_CONFIG.get(strategy_name, [0])


def get_close_stock_policy(strategy_name: str) -> bool:
    """
    دریافت سیاست بستن سهم برای یک استراتژی خاص
    
    Args:
        strategy_name: نام استراتژی
        
    Returns:
        True اگر سهم بسته شود، False در غیر این صورت
    """
    return CLOSE_STOCK_POLICY.get(strategy_name, True)


def is_strategy_active(strategy_name: str) -> bool:
    """
    بررسی فعال بودن یک استراتژی
    
    Args:
        strategy_name: نام استراتژی
        
    Returns:
        True اگر استراتژی فعال باشد، False در غیر این صورت
    """
    return strategy_name in TARGET_STRATEGIES