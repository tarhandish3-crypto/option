# strategies/definitions/short_call.py
# -*- coding: utf-8 -*-

from core.enums import GeneratorType
from strategies.base import StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="short_call",
    generator_type=GeneratorType.SINGLE_LEG,
    patterns=[
        {
            "option_type": "CALL",
            "side": "SELL",
            "ratio": 1,
        },
    ],
    rules={
        "min_liquidity_score": 30,
    },
)