# strategies/definitions/long_straddle.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="long_straddle",
    generator_type=GeneratorType.TWO_LEG,
    include_stock=False,

    patterns=(
        # لگ ۱: خرید Call
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.BUY,
            ratio=1,
            strike_group="K1",      # strike یکسان
            maturity_group="M1",
        ),
        # لگ ۲: خرید Put (با همان strike)
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.BUY,
            ratio=1,
            strike_group="K1",      # دقیقاً همان strike Call
            maturity_group="M1",
        ),
    ),

    description="Long Straddle - Buy ATM Call + Buy ATM Put (Volatility Play)",
    rules={
        "strike_order": "any",           # strikeها باید برابر باشند
        "maturity_order": "same",
        "strike_equal": True,            # تأکید بر برابری strikeها
        "strike_equal_tolerance_pct": 0.001,  # تحمل بسیار کم
    },
)
