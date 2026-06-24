# strategies/definitions/bear_put_spread.py

from strategies.base import GeneratorType, StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="bear_put_spread",
    generator_type=GeneratorType.TWO_LEG,
    weight_pattern=[("put", -1.0), ("put", 1.0)],
    include_stock=False,
    description="Bear Put Spread - فروش Put پایین‌تر + خرید Put بالاتر",
    rules={
        "strike_order": "ascending",
        "same_maturity": True,
    }
)