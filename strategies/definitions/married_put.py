# strategies/definitions/married_put.py
# -*- coding: utf-8 -*-

from core.enums import GeneratorType
from strategies.base import StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="married_put",
    generator_type=GeneratorType.STOCK_OPTION,
    patterns=[
        {
            "option_type": "STOCK",
            "side": "BUY",
            "ratio": 1,
        },
        {
            "option_type": "PUT",
            "side": "BUY",
            "ratio": 1,
            "strike_group": "K1",
            "maturity_group": "M1",
        },
    ],
    include_stock=True,
    description="Married Put - Buy Stock + Buy Protective Put",
    rules={
        "strike_order": "any",
        "maturity_order": "same",
        "strike_above_spot": False,
    },
)
