# strategies/definitions/collar.py
# -*- coding: utf-8 -*-

from core.enums import GeneratorType
from strategies.base import StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="collar",
    generator_type=GeneratorType.TWO_LEG,
    patterns=[
        {
            # خرید اختیار فروش
            "option_type": "PUT",
            "side": "BUY",
            "ratio": 1,
            "strike_group": "K1",
            "maturity_group": "M1",
        },
        {
            # فروش اختیار خرید
            "option_type": "CALL",
            "side": "SELL",
            "ratio": 1,
            "strike_group": "K2",
            "maturity_group": "M1",
        },
    ],
    include_stock=True,
    description="Collar - Long Stock + Long Put + Short Call",
    rules={
        # هر دو اختیار باید هم‌سررسید باشند
        "maturity_order": "same",

        # استرایک Put پایین‌تر از Call
        "strike_order": "ascending",
    },
)
