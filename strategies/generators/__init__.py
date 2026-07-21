# strategies/generators/__init__.py
# -*- coding: utf-8 -*-

"""
کارخانه تولیدکننده‌های استراتژی (Strategy Generator Factory).
مسئولیت: ایزوله‌سازی منطق تولید کلاس‌ها و مدیریت Dependency Injection استراتژی‌ها.
"""

from __future__ import annotations

import logging
from typing import Optional, Type, Dict

from strategies.base import StrategyDefinition, GeneratorType
from strategies.generators.base import BaseGenerator
from strategies.generators.single_leg import SingleLegGenerator
from strategies.generators.two_leg import TwoLegGenerator
from strategies.generators.three_leg import ThreeLegGenerator
from strategies.generators.four_leg import FourLegGenerator

# Logger در لایه کانفیگ و استارت‌آپ (نه در Hot Path)
logger = logging.getLogger("OptionScanner.Strategies.Generators")

# استفاده از Type[BaseGenerator] برای اطمینان از نوع کلاس‌های نقشه
GENERATOR_MAP: Dict[GeneratorType, Optional[Type[BaseGenerator]]] = {
    GeneratorType.STOCK_OPTION: TwoLegGenerator,
    GeneratorType.SINGLE_LEG: SingleLegGenerator,
    GeneratorType.TWO_LEG: TwoLegGenerator,
    GeneratorType.THREE_LEG: ThreeLegGenerator,
    GeneratorType.FOUR_LEG: FourLegGenerator,
}


def get_generator(strategy_def: StrategyDefinition) -> Optional[BaseGenerator]:
    """
    دریافت نمونه کلاس ژنراتور مناسب بر اساس نوع استراتژی.

    این تابع یکبار در زمان بارگذاری استراتژی فراخوانی می‌شود، بنابراین
    تمرکز آن بر سلامت (Sanity) و قابلیت نگهداری است.
    """
    generator_class = GENERATOR_MAP.get(strategy_def.generator_type)

    if generator_class is None:
        # لاگ‌گذاری صرفاً برای دیتای غیرمنتظره در فاز توسعه یا کانفیگ
        logger.warning(
            f"No generator implemented for type: {strategy_def.generator_type.value} "
            f"in strategy: {strategy_def.name}"
        )
        return None

    try:
        # تزریق وابستگی (Dependency Injection) استراتژی به ژنراتور
        return generator_class(strategy_def)
    except Exception as e:
        # مدیریت خطا در زمان ایجاد نمونه (مثلاً خطاهای کانفیگ داخل کلاس‌ها)
        logger.error(
            f"Failed to instantiate generator {generator_class.__name__} "
            f"for strategy {strategy_def.name}: {str(e)}"
        )
        return None


__all__ = [
    "BaseGenerator",
    "SingleLegGenerator",
    "TwoLegGenerator",
    "ThreeLegGenerator",
    "FourLegGenerator",
    "GENERATOR_MAP",
    "get_generator",
]
