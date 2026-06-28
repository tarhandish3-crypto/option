# strategies/definitions/long_straddle.py
# -*- coding: utf-8 -*-

from core.enums import GeneratorType
from strategies.base import StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="long_straddle",
    generator_type=GeneratorType.TWO_LEG,
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
            # هر دو باید دقیقاً یک استرایک داشته باشند
            "strike_group": "K1",
            "maturity_group": "M1",
        },
    ],
    include_stock=False,
    description="Long Straddle - Buy ATM Call + Buy ATM Put",
    rules={
        "maturity_order": "same",
    },
)
