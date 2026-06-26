# strategies/definitions/long_strangle.py
# -*- coding: utf-8 -*-

from core.enums import GeneratorType
from strategies.base import StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="long_strangle",
    generator_type=GeneratorType.TWO_LEG,
    patterns=[
        {
            "option_type": "PUT",
            "side": "BUY",
            "ratio": 1,
            "strike_group": "K1",
            "maturity_group": "M1",
        },
        {
            "option_type": "CALL",
            "side": "BUY",
            "ratio": 1,
            "strike_group": "K2",
            "maturity_group": "M1",
        },
    ],
    include_stock=False,
    description="Long Strangle",
    rules={
        "strike_order": "ascending",
        "maturity_order": "same",

        # فاصله حداقل بین دو استرایک
        "min_strike_gap_pct": 0.01,
    },
)
