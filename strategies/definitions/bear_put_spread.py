# strategies/definitions/bear_put_spread.py
# -*- coding: utf-8 -*-

from core.enums import GeneratorType
from strategies.base import StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="bear_put_spread",
    generator_type=GeneratorType.TWO_LEG,
    patterns=[
        {
            # خرید PUT با استرایک بالاتر — سود اصلی استراتژی
            "option_type": "PUT",
            "side": "BUY",
            "ratio": 1,
            "strike_group": "K2",
            "maturity_group": "M1",
        },
        {
            # فروش PUT با استرایک پایین‌تر — کاهش هزینه
            "option_type": "PUT",
            "side": "SELL",
            "ratio": 1,
            "strike_group": "K1",
            "maturity_group": "M1",
        },
    ],
    include_stock=False,
    description="Bear Put Spread - Buy Higher Strike Put / Sell Lower Strike Put",
    rules={
        "strike_order": "ascending",   # K1 < K2
        "maturity_order": "same",
        "min_strike_gap_pct": 0.01,
        "max_strike_gap_pct": 0.15,
    },
)
