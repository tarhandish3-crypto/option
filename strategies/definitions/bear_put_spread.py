# strategies/definitions/bear_put_spread.py

from core.enums import Side, OptionType
from core.models import StrategyLegPattern
from strategies.base import StrategyDefinition, GeneratorType

DEFINITION = StrategyDefinition(
    name="bear_put_spread",
    generator_type=GeneratorType.TWO_LEG,
    patterns=(
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.SELL,
            ratio=1,
            strike_group="K1",
            maturity_group="M1",
        ),
        StrategyLegPattern(
            option_type=OptionType.PUT,
            side=Side.BUY,
            ratio=1,
            strike_group="K2",
            maturity_group="M1",
        ),
    ),

    description="Bear Put Spread",
    rules={
        "strike_order": "ascending",
        "maturity_order": "same",
    },
)