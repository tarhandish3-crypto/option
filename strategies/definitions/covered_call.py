# strategies/definitions/covered_call.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="covered_call",
    generator_type=GeneratorType.STOCK_OPTION,
    include_stock=True,

    patterns=(
        # فقط لگ آپشن: فروش Call
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.SELL,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
        # لگ STOCK به‌صورت خودکار توسط StockOptionGenerator اضافه می‌شود
    ),

    description="Covered Call - Long Stock + Short Call (Income Generation Strategy)",
    rules={
        # کال باید بالای قیمت سهم فروخته شود (معمولاً OTM)
        "strike_above_spot": True,
        "maturity_order": "same",
        "min_strike_gap_pct": 0.0,
    },
)
