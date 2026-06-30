# strategies/definitions/iron_condor.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="iron_condor",
    generator_type=GeneratorType.FOUR_LEG,
    include_stock=False,

    patterns=(
        # لگ ۱: فروش Put با strike پایین (جمع‌آوری پرمیوم)
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.SELL,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
        # لگ ۲: خرید Put با strike بالاتر (حفاظت)
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.BUY,
            ratio=1,
            strike_group="K2",
            maturity_group="M1",
        ),
        # لگ ۳: خرید Call با strike بالاتر (حفاظت)
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.BUY,
            ratio=1,
            strike_group="K3",
            maturity_group="M1",
        ),
        # لگ ۴: فروش Call با strike بالاتر (جمع‌آوری پرمیوم)
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.SELL,
            ratio=1,
            strike_group="K4",
            maturity_group="M1",
        ),
    ),

    description="Iron Condor - Neutral Range-Bound Strategy (Limited Risk / Limited Profit)",
    rules={
        "strike_order": "ascending",        # K1 < K2 < K3 < K4
        "maturity_order": "same",

        "min_strike_gap_pct": 0.02,         # حداقل فاصله بین strikeها
        "max_strike_gap_pct": 0.15,         # حداکثر فاصله منطقی برای Iron Condor

        "enforce_symmetry": True,           # تقارن بال‌ها (K2-K1 ≈ K4-K3)
        "symmetry_tolerance_pct": 0.008,    # تحمل ۰.۸٪
        "min_inner_gap_pct": 0.03,          # فاصله بین بدنه (K3 - K2)
    },
)
