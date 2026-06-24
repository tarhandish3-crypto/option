# strategies/definitions/conversion.py

from strategies.base import GeneratorType, StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="conversion",
    generator_type=GeneratorType.TWO_LEG,
    weight_pattern=[("call", -1.0), ("put", 1.0)],
    include_stock=True,
    description="Conversion - خرید سهم + فروش کال + خرید پوت (آربیتراژ)",
    rules={
        "strike_equal": True,
        "same_maturity": True,
    }
)