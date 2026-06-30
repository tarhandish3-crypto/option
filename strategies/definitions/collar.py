# strategies/definitions/collar.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="collar",
    generator_type=GeneratorType.STOCK_OPTION,   # چون ۱ لگ سهم + ۲ لگ آپشن
    include_stock=True,
    
    patterns=(
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.BUY,
            ratio=1,
            strike_group="K1",      # کف قیمت (حمایت)
            maturity_group="M1",
        ),
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.SELL,
            ratio=1,
            strike_group="K2",      # سقف قیمت (فروش پوشش)
            maturity_group="M1",
        ),
    ),
    
    description="Collar Strategy - Long Stock + Long Put + Short Call (Zero-Cost or Low-Cost Hedge)",
    rules={
        "strike_order": "ascending",   # K1 (Put) < K2 (Call)
        "maturity_order": "same",
        "min_strike_gap_pct": 0.03,    # حداقل فاصله بین strikeها
    },
)