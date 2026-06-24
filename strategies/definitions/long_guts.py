# strategies/definitions/long_guts.py

from strategies.base import GeneratorType, StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="long_guts",
    generator_type=GeneratorType.TWO_LEG,
    weight_pattern=[("put", 1.0), ("call", 1.0)],
    include_stock=False,
    description="Long Guts - خرید Put + خرید Call با strike متفاوت (ITM)",
    rules={
        "strike_order": "put_gt_call",
        "same_maturity": True,
    }
)