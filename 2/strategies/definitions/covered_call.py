# strategies/definitions/covered_call.py
# -*- coding: utf-8 -*-

from core.enums import GeneratorType
from strategies.base import StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="covered_call",
    generator_type=GeneratorType.STOCK_OPTION,
    patterns=[
        {
            "option_type": "CALL",
            "side": "SELL",
            "ratio": 1,
            "strike_group": "K1",
            "maturity_group": "M1",
        },
    ],

    include_stock=True,
    description="Covered Call - Long Stock + Short Call",
    rules={
        "strike_above_spot": True,
    },
)
