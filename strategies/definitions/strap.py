# strategies/definitions/strap.py
# -*- coding: utf-8 -*-

from core.enums import GeneratorType
from strategies.base import StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="strap",
    generator_type=GeneratorType.THREE_LEG,
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
            "strike_group": "K1",
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
    description="Strap - Long 1 Put + Long 2 Calls",
    rules={
        "maturity_order": "same",
    },
)
