# strategies/definitions/married_put.py

from strategies.base import GeneratorType, StrategyDefinition

DEFINITION = StrategyDefinition.create(
    name="married_put",
    generator_type=GeneratorType.STOCK_OPTION,
    weight_pattern=[("put", 1.0)],
    
    include_stock=True,
    description="خرید سهم + خرید اختیار فروش - محافظت در برابر کاهش قیمت",
    rules={"strike_above_spot": False  # برای Married Put معمولاً استرایک‌های هم‌قیمت یا در سود انتخاب می‌شوند
    })