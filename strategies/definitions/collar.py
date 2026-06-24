# strategies/definitions/collar.py

from strategies.base import GeneratorType, StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="collar",
    generator_type=GeneratorType.TWO_LEG,
    weight_pattern=[("put", 1.0), ("call", -1.0)],
    include_stock=True,
    description="Collar - خرید سهم + خرید Put + فروش Call",
    rules={
        "strike_order": "put_then_call",
        "same_maturity": True,
    }
)