# strategies/definitions/strip.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="strip",
    generator_type=GeneratorType.THREE_LEG,
    include_stock=False,

    patterns=(
        # لگ ۱: خرید Call (۱ عدد)
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.BUY,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
        # لگ ۲: خرید Put (۲ عدد)
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.BUY,
            ratio=2,          # مهم: نسبت ۲
            strike_group="K1",
            maturity_group="M1",
        ),
    ),

    description="Strip - Long 1 Call + Long 2 Puts (Bearish Volatility Strategy)",
    rules={
        "maturity_order": "same",
        "strike_order": "any",
    },
)
