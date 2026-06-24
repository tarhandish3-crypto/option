# strategies/definitions/long_straddle.py

from strategies.base import GeneratorType, StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="long_straddle",
    generator_type=GeneratorType.TWO_LEG,
    weight_pattern=[("call", 1.0), ("put", 1.0)],
    include_stock=False,
    description="Long Straddle - خرید Call + خرید Put با strike یکسان",
    rules={
        "strike_equal": True,
        "same_maturity": True,
    }
)