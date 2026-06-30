# strategies/definitions/long_strangle.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="long_strangle",
    generator_type=GeneratorType.TWO_LEG,
    include_stock=False,

    patterns=(
        # لگ ۱: خرید Put با strike پایین‌تر
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.BUY,
            ratio=1,
            strike_group="K1",      # strike پایین‌تر
            maturity_group="M1",
        ),
        # لگ ۲: خرید Call با strike بالاتر
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.BUY,
            ratio=1,
            strike_group="K2",      # strike بالاتر
            maturity_group="M1",
        ),
    ),

    description="Long Strangle - Buy OTM Put + Buy OTM Call (Volatility Play with Wider Range)",
    rules={
        "strike_order": "ascending",      # K1 (Put) < K2 (Call)
        "maturity_order": "same",
        "min_strike_gap_pct": 0.01,       # حداقل فاصله بین دو strike
        "max_strike_gap_pct": 0.20,       # حداکثر فاصله پیشنهادی (اختیاری)
    },
)
