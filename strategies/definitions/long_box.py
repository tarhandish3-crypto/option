# strategies/definitions/long_box.py

from strategies.base import GeneratorType, StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="long_box",
    generator_type=GeneratorType.FOUR_LEG,
    weight_pattern=[("call", 1.0), ("call", -1.0), ("put", -1.0), ("put", 1.0)],
    include_stock=False,
    description="Long Box - استراتژی آربیتراژ",
    rules={
        "strike_order": "k1_k2",
        "same_maturity": True,
    }
)