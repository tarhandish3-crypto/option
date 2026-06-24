# strategies/definitions/strip.py

from strategies.base import GeneratorType, StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="strip",
    generator_type=GeneratorType.THREE_LEG,
    weight_pattern=[("call", 1.0), ("put", 1.0), ("put", 1.0)],
    include_stock=False,
    description="Strip - 1 Call + 2 Put - دیدگاه نزولی",
    rules={
        "strike_equal": True,
        "same_maturity": True,
        "put_count": 2,
        "call_count": 1,
    }
)