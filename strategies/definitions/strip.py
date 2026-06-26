# strategies/definitions/strip.py
# -*- coding: utf-8 -*-

from core.enums import GeneratorType
from strategies.base import StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="strip",
    generator_type=GeneratorType.THREE_LEG,
    patterns=[
        {
            "option_type": "CALL",
            "side": "BUY",
            "ratio": 1,
            "strike_group": "K1",
            "maturity_group": "M1",
        },
        {
            "option_type": "PUT",
            "side": "BUY",
            "ratio": 1,
            "strike_group": "K1",
            "maturity_group": "M1",
        },
        {
            "option_type": "PUT",
            "side": "BUY",
            "ratio": 1,
            "strike_group": "K1",
            "maturity_group": "M1",
        },
    ],
    include_stock=False,
    description="Strip - Long 1 Call + Long 2 Puts",
    rules={
        "maturity_order": "same",
    },
)
