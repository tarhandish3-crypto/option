# strategies/definitions/covered_call.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="covered_call",
    generator_type=GeneratorType.TWO_LEG,

    patterns=(
        # لگ ۱: خرید سهم پایه
        StrategyLegPattern(
            option_type=OptionType.STOCK,
            side=Side.BUY,
            ratio=1,
        ),
        # لگ ۲: فروش Call (ATM/OTM)
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.SELL,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
    ),

    rules={
        "maturity_order": "same",
        "strike_above_spot": True,
    },
)
