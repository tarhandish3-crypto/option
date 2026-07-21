# strategies/definitions/long_put.py
# -*- coding: utf-8 -*-

from core.enums import GeneratorType
from strategies.base import StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="long_put",
    generator_type=GeneratorType.SINGLE_LEG,
    patterns=[
        {
            "option_type": "PUT",
            "side": "BUY",
            "ratio": 1,
        },
    ],
    rules={
        "min_liquidity_score": 30,
    },
)
