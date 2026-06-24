# strategies/definitions/long_strangle.py

from strategies.base import GeneratorType, StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="long_strangle",
    generator_type=GeneratorType.TWO_LEG,
    weight_pattern=[("put", 1.0), ("call", 1.0)],
    include_stock=False,
    description="Long Strangle - خرید Put + خرید Call (put_strike < call_strike)",
    rules={
        "strike_order": "put_then_call",
        "same_maturity": True,
    }
)