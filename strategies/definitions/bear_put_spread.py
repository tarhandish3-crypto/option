# strategies/definitions/bear_put_spread.py
# -*- coding: utf-8 -*-

"""
تعریف استراتژی Bear Put Spread (اختیار فروش خرس‌گرا / بدهی).
این ماژول شروط و پترن‌های دو لگی را برای ساختار اسکن دو لگی (TwoLegGenerator) مشخص می‌کند.
"""

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="bear_put_spread",
    generator_type=GeneratorType.TWO_LEG,
    include_stock=False,

    patterns=(
        # لگ ۱: فروش PUT با استرایک پایین‌تر (K1) - جهت کاهش کل هزینه پرمیوم پرداختی
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.SELL,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
        # لگ ۲: خرید PUT با استرایک بالاتر (K2) - موتور اصلی سود در حرکت نزولی
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.BUY,
            ratio=1,
            strike_group="K2",
            maturity_group="M1",
        ),
    ),


    rules={
        # پترن‌ها به ترتیب صعودی (K1 < K2) چیده شده‌اند تا با PatternMatcher سازگار باشند
        "strike_order": "ascending",
        "maturity_order": "same",
        "min_strike_gap_pct": 0.01,   # حداقل فاصله ۱ درصدی بین دو استرایک در بازار ایران
        # حداکثر فاصله ۱۵ درصدی جهت پرهیز از بی‌اثر شدن پوزیشن فروش
        "max_strike_gap_pct": 0.15,
    },
)
