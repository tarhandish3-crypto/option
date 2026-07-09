# strategies/definitions/collar.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="collar",
    generator_type=GeneratorType.THREE_LEG,   # سهم پایه + پوت + کال → سه لگ
    include_stock=True,

    patterns=(
        # لگ ۱: خرید سهم پایه (توسط ThreeLegGenerator از طریق include_stock مدیریت می‌شود)
        StrategyLegPattern(
            option_type=OptionType.STOCK,
            side=Side.BUY,
            ratio=1,
        ),
        # لگ ۲: خرید Put — کف حمایتی
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.BUY,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
        # لگ ۳: فروش Call — سقف و تامین هزینه
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.SELL,
            ratio=1,
            strike_group="K2",
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
