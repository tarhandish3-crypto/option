# strategies/definitions/iron_condor.py

from strategies.base import GeneratorType, StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="iron_condor",
    generator_type=GeneratorType.FOUR_LEG,
    weight_pattern=[("put", -1.0), ("put", 1.0), ("call", 1.0), ("call", -1.0)],
    include_stock=False,
    description="Iron Condor - سود از نوسان محدود قیمت",
    rules={
        "strike_order": "put1_put2_call1_call2",
        "same_maturity": True,
        "min_width_pct": 0.02,
        "max_width_pct": 0.15,
    }
)