# strategies/definitions/conversion.py
# -*- coding: utf-8 -*-

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="conversion",
    generator_type=GeneratorType.THREE_LEG,
    include_stock=True,

    patterns=(
        # لگ ۱: خرید سهم پایه
        StrategyLegPattern(
            option_type=OptionType.STOCK,
            side=Side.BUY,
            ratio=1,
        ),
        # لگ ۲: فروش Call
        StrategyLegPattern(
            option_type=OptionType.CALL,
            side=Side.SELL,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
        # لگ ۳: خرید Put (با همان strike)
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.BUY,
            ratio=1,
            strike_group="K1",      # دقیقاً همان strike Call
            maturity_group="M1",
        ),
    ),

    description="Conversion - Synthetic Long Position (Long Stock + Short Call + Long Put)",
    rules={
        "strike_order": "any",      # strikeها باید برابر باشند (K1 == K1)
        "maturity_order": "same",
        "strike_equal": True,       # تأکید بر برابری strikeها
        "strike_equal_tolerance_pct": 0.001,  # تحمل بسیار کم
    },
)
