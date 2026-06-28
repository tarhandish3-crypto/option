# strategies/definitions/iron_condor.py
# -*- coding: utf-8 -*-

from core.enums import GeneratorType
from strategies.base import StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="iron_condor",
    generator_type=GeneratorType.FOUR_LEG,
    patterns=[
        {
            "option_type": "PUT",
            "side": "SELL",
            "ratio": 1,
            "strike_group": "K1",
            "maturity_group": "M1",
        },
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
            "strike_group": "K3",
            "maturity_group": "M1",
        },
        {
            "option_type": "CALL",
            "side": "SELL",
            "ratio": 1,
            "strike_group": "K4",
            "maturity_group": "M1",
        },
    ],

    include_stock=False,
    description="Iron Condor - Limited Risk / Limited Profit",
    rules={
        "strike_order": "ascending",
        "maturity_order": "same",

        "min_strike_gap_pct": 0.02,
        "max_strike_gap_pct": 0.15,

        "enforce_symmetry": False,
    },
)
