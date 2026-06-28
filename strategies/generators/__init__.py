# strategies/generators/__init__.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import Optional

from strategies.generators.base import BaseGenerator
from strategies.generators.two_leg import TwoLegGenerator
from strategies.generators.three_leg import ThreeLegGenerator
from strategies.generators.four_leg import FourLegGenerator
from strategies.generators.stock_option import StockOptionGenerator

from strategies.base import GeneratorType, StrategyDefinition

logger = logging.getLogger("OptionScanner.Strategies.Generators")

GENERATOR_MAP = {
    GeneratorType.STOCK_OPTION: StockOptionGenerator,
    GeneratorType.SINGLE_LEG: None,  # در صورت پیاده‌سازی کلاس، جایگزین None شود
    GeneratorType.TWO_LEG: TwoLegGenerator,
    GeneratorType.THREE_LEG: ThreeLegGenerator,
    GeneratorType.FOUR_LEG: FourLegGenerator,
}


def get_generator(strategy_def: StrategyDefinition) -> Optional[BaseGenerator]:
    """دریافت Generator مناسب برای استراتژی بر اساس الگوی طراحی فکتوری.
    
    Returns:
        نمونه Generator مناسب، یا None اگر generator برای این نوع پیاده‌سازی نشده باشد.
    """
    generator_class = GENERATOR_MAP.get(strategy_def.generator_type)

    if generator_class is None:
        # SINGLE_LEG و هر نوع ناشناخته → None (caller با if generator is None: continue مدیریت می‌کند)
        logger.debug(f"No generator available for type: {strategy_def.generator_type} ({strategy_def.name})")
        return None

    return generator_class(strategy_def)


__all__ = [
    "BaseGenerator",
    "StockOptionGenerator",
    "TwoLegGenerator",
    "ThreeLegGenerator",
    "FourLegGenerator",
    "GENERATOR_MAP",
    "get_generator",
]