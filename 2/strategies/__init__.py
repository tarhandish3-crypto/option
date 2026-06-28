# strategies/__init__.py

from core.models import LegDefinition

from strategies.base import (
    StrategyDefinition,
    GeneratorType,)

from strategies.core import (
    get_strategy,
    get_all_strategies,
    get_strategy_names,
    get_strategies_by_generator,
    reload_strategies,
    register_strategy,)

from strategies.config import (
    TARGET_STRATEGIES,
    CLOSE_STOCK_POLICY,
    STRATEGY_CONFIG,
    get_strategy_config,
    get_close_stock_policy,
    is_strategy_active,)

from strategies.generators import (
    get_generator,
    BaseGenerator,
    TwoLegGenerator,
    ThreeLegGenerator,
    FourLegGenerator,)

__all__ = [
    # Base
    "StrategyDefinition",
    "LegDefinition",
    "GeneratorType",

    # Core (Registry)
    "get_strategy",
    "get_all_strategies",
    "get_strategy_names",
    "get_strategies_by_generator",
    "reload_strategies",
    "register_strategy",

    # Config
    "TARGET_STRATEGIES",
    "CLOSE_STOCK_POLICY",
    "STRATEGY_CONFIG",
    "get_strategy_config",
    "get_close_stock_policy",
    "is_strategy_active",

    # Generators
    "get_generator",
    "BaseGenerator",
    "TwoLegGenerator",
    "ThreeLegGenerator",
    "FourLegGenerator",
]
