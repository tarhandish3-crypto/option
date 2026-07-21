# strategies/definitions/long_call.py
# -*- coding: utf-8 -*-

from core.enums import GeneratorType
from strategies.base import StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="long_call",
    generator_type=GeneratorType.SINGLE_LEG,
    patterns=[
        {
            "option_type": "CALL",
            "side": "BUY",
            "ratio": 1,
        },
    ],
    rules={
        "min_liquidity_score": 30,
    },
)
