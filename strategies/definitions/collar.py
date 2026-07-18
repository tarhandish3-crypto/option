# strategies/definitions/collar.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="collar",
    generator_type=GeneratorType.THREE_LEG,

    patterns=(
        # لگ ۱: خرید سهم پایه
        StrategyLegPattern(
            option_type=OptionType.STOCK,
            side=Side.BUY,
            ratio=1,
        ),
        # لگ ۲: خرید Put — کف حمایتی (K1)
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.BUY,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
        # لگ ۳: فروش Call — سقف قیمت (K2 > K1)
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.SELL,
            ratio=1,
            strike_group="K2",
            maturity_group="M1",
        ),
    ),

    rules={
        "maturity_order": "same",
        "strike_order": "ascending",
        "min_strike_gap_pct": 0.03,
    },
)
