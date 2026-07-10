# strategies/definitions/married_put.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="married_put",
    generator_type=GeneratorType.TWO_LEG,

    patterns=(
        # لگ ۱: خرید سهم پایه
        StrategyLegPattern(
            option_type=OptionType.STOCK,
            side=Side.BUY,
            ratio=1,
        ),
        # لگ ۲: خرید Put حفاظتی
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
        "maturity_order": "same",
        "strike_order": "any",
        "min_strike_gap_pct": 0.0,
    },
)
