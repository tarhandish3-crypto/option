# strategies/definitions/long_calendar_call.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="long_calendar_call",
    generator_type=GeneratorType.TWO_LEG,
    include_stock=False,

    patterns=(
        # لگ ۱: فروش Call در سررسید نزدیک (Near-Term)
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.SELL,
            ratio=1,
            strike_group="K1",
            maturity_group="M_near",
        ),
        # لگ ۲: خرید Call در سررسید دور (Far-Term)
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.BUY,
            ratio=1,
            strike_group="K1",
            maturity_group="M_far",
        ),
    ),

    rules={
        "maturity_order": "different",   # ← فعال‌سازی Calendar
        "strike_equal": True,            # strike یکسان
        "strike_equal_tolerance_pct": 0.001,
        "min_dte_gap_days": 7,           # حداقل ۱ هفته فاصله
        "max_dte_gap_days": 180,         # حداکثر ۶ ماه فاصله
        "far_maturity_first": False,     # pattern[0] = نزدیک
    },
)