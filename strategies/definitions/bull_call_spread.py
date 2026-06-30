# strategies/definitions/bull_call_spread.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="bull_call_spread",
    generator_type=GeneratorType.TWO_LEG,
    include_stock=False,

    patterns=(
        # لگ ۱: خرید Call با strike پایین‌تر (سود اصلی در حرکت صعودی)
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.BUY,
            ratio=1,
            strike_group="K1",      # strike پایین‌تر
            maturity_group="M1",
        ),
        # لگ ۲: فروش Call با strike بالاتر (کاهش هزینه خالص)
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.SELL,
            ratio=1,
            strike_group="K2",      # strike بالاتر
            maturity_group="M1",
        ),
    ),

    description="Bull Call Spread - Buy Lower Strike Call / Sell Higher Strike Call (Debit Spread)",
    rules={
        "strike_order": "ascending",      # K1 < K2
        "maturity_order": "same",
        "min_strike_gap_pct": 0.01,       # حداقل فاصله ۱٪
        "max_strike_gap_pct": 0.10,       # حداکثر فاصله منطقی
    },
)
