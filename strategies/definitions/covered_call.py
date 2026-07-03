# strategies/definitions/covered_call.py
# -*- coding: utf-8 -*-

"""
تعریف استراتژی Covered Call (خرید سهم پایه + فروش اختیار خرید).
این ماژول ساختار الگوها و فیلترهای اولیه قیمت اعمال را برای StockOptionGenerator مشخص می‌کند.
"""

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="Covered Call",
    generator_type=GeneratorType.STOCK_OPTION,
    include_stock=True,
    legs_count=2,  # پوزیشن نهایی شامل ۲ لگ است (۱ سهم + ۱ اختیار معامله)

    patterns=(
        # لنگه اختیار معامله: فروش Call جهت کسب پرمیوم
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.SELL,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
        # لنگه دارایی پایه (Stock) به صورت داینامیک توسط StockOptionGenerator در موتور تزریق می‌شود.
    ),

    description="Covered Call - Long Stock + Short Call (Income Generation Strategy for Tehran Option Market)",

    rules={
        # فیلتر اعمال: اختیار خرید باید حوالی قیمت سهم یا بالاتر از آن (ATM / OTM) فروخته شود.
        "strike_above_spot": True,
        "maturity_order": "same",
        "min_strike_gap_pct": 0.0,
    },
)
