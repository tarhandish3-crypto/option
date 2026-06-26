# strategies/definitions/long_guts.py
# -*- coding: utf-8 -*-

from core.enums import GeneratorType
from strategies.base import StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="long_guts",
    generator_type=GeneratorType.TWO_LEG,
    patterns=[
        {
            "option_type": "PUT",
            "side": "BUY",
            "ratio": 1,
            "strike_group": "K2",
            "maturity_group": "M1",
        },
        {
            "option_type": "CALL",
            "side": "BUY",
            "ratio": 1,
            "strike_group": "K1",
            "maturity_group": "M1",
        },
    ],
    include_stock=False,
    description="Long Guts",
    rules={
        "strike_order": "ascending",
        "maturity_order": "same",
    },
)
