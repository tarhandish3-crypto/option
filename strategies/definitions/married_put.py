# strategies/definitions/married_put.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="married_put",
    generator_type=GeneratorType.STOCK_OPTION,
    include_stock=True,
    
    patterns=(
        # لگ ۱: خرید سهم پایه
        StrategyLegPattern(
            option_type=OptionType.STOCK,
            side=Side.BUY,
            ratio=1,
        ),
        # لگ ۲: خرید پوت حفاظتی (Protective Put)
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.BUY,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
    ),
    
    description="Married Put - Long Stock + Long Protective Put (Insurance Strategy)",
    rules={
        "strike_order": "any",           # strike پوت می‌تواند ATM یا کمی OTM باشد
        "maturity_order": "same",
        "strike_below_spot": False,      # معمولاً نزدیک به قیمت سهم یا کمی بالاتر
        "min_strike_gap_pct": 0.0,       # بدون محدودیت فاصله
    },
)