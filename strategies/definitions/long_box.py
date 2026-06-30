# strategies/definitions/long_box.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="long_box",
    generator_type=GeneratorType.FOUR_LEG,
    include_stock=False,

    patterns=(
        # لگ ۱: خرید Call با strike پایین‌تر
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.BUY,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
        # لگ ۲: فروش Call با strike بالاتر
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.SELL,
            ratio=1,
            strike_group="K2",
            maturity_group="M1",
        ),
        # لگ ۳: فروش Put با strike پایین‌تر
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.SELL,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
        # لگ ۴: خرید Put با strike بالاتر
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.BUY,
            ratio=1,
            strike_group="K2",
            maturity_group="M1",
        ),
    ),

    description="Long Box Spread - Arbitrage Strategy (Synthetic Long + Synthetic Short)",
    rules={
        "strike_order": "ascending",      # K1 < K2
        "maturity_order": "same",
        # حداقل فاصله ۵٪ (برای سودآوری آربیتراژ)
        "min_strike_gap_pct": 0.05,
        "max_strike_gap_pct": 0.50,       # حداکثر فاصله منطقی
        "strike_equal_tolerance_pct": 0.001,  # تحمل بسیار کم برای برابری در جفت‌ها
    },
)
