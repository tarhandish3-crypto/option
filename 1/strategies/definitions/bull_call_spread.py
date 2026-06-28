# strategies/definitions/bull_call_spread.py
# -*- coding: utf-8 -*-

from core.enums import GeneratorType
from strategies.base import StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="bull_call_spread",
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
            "option_type": "CALL",
            "side": "SELL",
            "ratio": 1,
            "strike_group": "K2",
            "maturity_group": "M1",
        },
    ],

    include_stock=False,
    description="Bull Call Spread - Buy Lower Strike Call / Sell Higher Strike Call",
    rules={
        "strike_order": "ascending",
        "maturity_order": "same",
        "min_strike_gap_pct": 0.01,
        "max_strike_gap_pct": 0.10,
    },
)
