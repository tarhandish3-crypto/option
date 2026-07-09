# strategies/definitions/conversion.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="conversion",
    generator_type=GeneratorType.TWO_LEG,   # سهم پایه جداگانه تزریق می‌شود؛ مچر فقط Call+Put می‌بیند
    include_stock=True,

    patterns=(
        # لگ ۱: فروش Call با strike K1
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.SELL,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
        # لگ ۲: خرید Put با همان strike K1
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.BUY,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
    ),

    description="Conversion - Long Stock + Short Call + Long Put at same strike (Synthetic Short Forward)",
    rules={
        "strike_order": "any",
        "maturity_order": "same",
        "strike_equal": True,                  # Call و Put باید همان strike را داشته باشند
        "strike_equal_tolerance_pct": 0.001,
    },
)
