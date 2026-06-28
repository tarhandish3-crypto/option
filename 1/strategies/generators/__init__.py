# strategies/generators/__init__.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from strategies.generators.base import BaseGenerator
from strategies.generators.two_leg import TwoLegGenerator
from strategies.generators.three_leg import ThreeLegGenerator
from strategies.generators.four_leg import FourLegGenerator
from strategies.generators.stock_option import StockOptionGenerator

from strategies.base import GeneratorType, StrategyDefinition

GENERATOR_MAP = {
    GeneratorType.STOCK_OPTION: StockOptionGenerator,
    GeneratorType.SINGLE_LEG: None,  # در صورت پیاده‌سازی کلاس، جایگزین None شود
    GeneratorType.TWO_LEG: TwoLegGenerator,
    GeneratorType.THREE_LEG: ThreeLegGenerator,
    GeneratorType.FOUR_LEG: FourLegGenerator,
}


def get_generator(strategy_def: StrategyDefinition) -> BaseGenerator:
    """دریافت Generator مناسب برای استراتژی بر اساس الگوی طراحی فکتوری"""
    generator_class = GENERATOR_MAP.get(strategy_def.generator_type)
    
    if generator_class is None:
        if strategy_def.generator_type == GeneratorType.SINGLE_LEG:
            raise NotImplementedError("تولیدکننده استراتژی‌های تک‌لگی (SINGLE_LEG) هنوز پیاده‌سازی نشده است.")
        raise ValueError(f"نوع ژنراتور ناشناخته است: {strategy_def.generator_type}")
    
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