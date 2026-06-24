# strategies/definitions/strap.py

from strategies.base import GeneratorType, StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="strap",
    generator_type=GeneratorType.THREE_LEG,
    weight_pattern=[("put", 1.0), ("call", 1.0), ("call", 1.0)],
    include_stock=False,
    description="Strap - 1 Put + 2 Call - دیدگاه صعودی",
    rules={
        "strike_equal": True,
        "same_maturity": True,
        "call_count": 2,
        "put_count": 1,
    }
)