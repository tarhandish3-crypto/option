# strategies/definitions/strip.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="strip",
    generator_type=GeneratorType.TWO_LEG,   # ۱ Call + ۲ Put با همان strike → ۲ نوع ابزار
    include_stock=False,

    patterns=(
        # لگ ۱: خرید Call (۱ عدد)
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.BUY,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
        # لگ ۲: خرید Put (۲ عدد) — ratio=2 نشان‌دهنده دو قرارداد است
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.BUY,
            ratio=2,
            strike_group="K1",
            maturity_group="M1",
        ),
    ),

    description="Strip - Long 1 Call + Long 2 Puts at same strike (Bearish Volatility Strategy)",
    rules={
        "maturity_order": "same",
        "strike_equal": True,              # هر دو لگ باید همان strike را داشته باشند
        "strike_equal_tolerance_pct": 0.001,
    },
)
