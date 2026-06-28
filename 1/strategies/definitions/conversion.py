# strategies/definitions/conversion.py
# -*- coding: utf-8 -*-

from core.enums import GeneratorType
from strategies.base import StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="conversion",
    generator_type=GeneratorType.STOCK_OPTION,
    patterns=[
        {
            # فروش اختیار خرید
            "option_type": "CALL",
            "side": "SELL",
            "ratio": 1,
            "strike_group": "K1",
            "maturity_group": "M1",
        },
        {
            # خرید اختیار فروش
            "option_type": "PUT",
            "side": "BUY",
            "ratio": 1,
            "strike_group": "K1",      # همان استرایک Call
            "maturity_group": "M1",    # همان سررسید
        },
    ],
    include_stock=True,
    description="Conversion - Long Stock + Short Call + Long Put",
    rules={
        "maturity_order": "same",
    },
)
