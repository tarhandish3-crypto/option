# strategies/definitions/bull_call_spread.py

from strategies.base import GeneratorType, StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="bull_call_spread",
    generator_type=GeneratorType.TWO_LEG,
    weight_pattern=[("call", 1.0), ("call", -1.0)],
    include_stock=False,
    description="Bull Call Spread - خرید Call پایین‌تر + فروش Call بالاتر",
    rules={
        "strike_order": "ascending",
        "same_maturity": True,
        "min_strike_gap_pct": 0.01,
        "max_strike_gap_pct": 0.10,
    })