# strategies/definitions/conversion.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="conversion",
    generator_type=GeneratorType.THREE_LEG,

    patterns=(
        # لگ ۱: خرید سهم پایه
        StrategyLegPattern(
            option_type=OptionType.STOCK,
            side=Side.BUY,
            ratio=1,
        ),
        # لگ ۲: فروش Call با strike K1
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.SELL,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
        # لگ ۳: خرید Put با همان strike K1
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.BUY,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
    ),

    description="Conversion - Long Stock + Short Call + Long Put (Synthetic Short Forward)",
    rules={
        "maturity_order": "same",
        "strike_order": "any",
        "strike_equal": True,
        "strike_equal_tolerance_pct": 0.001,
    },
)
