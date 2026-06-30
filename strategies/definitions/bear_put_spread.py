# strategies/definitions/bear_put_spread.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="bear_put_spread",
    generator_type=GeneratorType.TWO_LEG,
    include_stock=False,
    
    patterns=(
        # لگ ۱: خرید PUT با strike بالاتر (سود اصلی در حرکت نزولی)
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.BUY,
            ratio=1,
            strike_group="K2",      # strike بالاتر
            maturity_group="M1",
        ),
        # لگ ۲: فروش PUT با strike پایین‌تر (کاهش هزینه خالص)
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.SELL,
            ratio=1,
            strike_group="K1",      # strike پایین‌تر
            maturity_group="M1",
        ),
    ),
    
    description="Bear Put Spread - Buy Higher Strike Put / Sell Lower Strike Put (Debit Spread)",
    rules={
        "strike_order": "ascending",      # K1 < K2
        "maturity_order": "same",
        "min_strike_gap_pct": 0.01,       # حداقل فاصله ۱٪
        "max_strike_gap_pct": 0.15,       # حداکثر فاصله منطقی
    },
)