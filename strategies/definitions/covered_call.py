# strategies/definitions/covered_call.py

from strategies.base import GeneratorType, StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="covered_call",
    generator_type=GeneratorType.STOCK_OPTION,
    weight_pattern=[("call", -1.0)],
    include_stock=True,
    description="Covered Call - خرید سهم + فروش Call",
    rules={
        "strike_above_spot": True,
    }
)