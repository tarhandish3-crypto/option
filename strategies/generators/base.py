# strategies/generators/base.py
# -*- coding: utf-8 -*-

"""
ماژول پایه تولیدکننده‌های استراتژی (Base Strategy Generator)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Iterator

from core.models import UnderlyingAsset, Opportunity
from strategies.base import StrategyDefinition
from strategies.matching.contract_index import ContractIndex


class BaseGenerator(ABC):
    """
    کلاس پایه انتزاعی برای تولیدکننده‌های استراتژی.
    این کلاس اکنون صرفاً مسئول منطق اجرای استراتژی است و هیچ مسئولیت جانبی
    (مانند Logging یا Metadata) ندارد.
    """

    __slots__ = (
        'strategy_def',
        '_generated_count',
        '_filtered_count',
        '_missing_price_count')

    def __init__(self, strategy_def: StrategyDefinition):
        self.strategy_def = strategy_def
        self._generated_count = 0
        self._filtered_count = 0
        self._missing_price_count = 0

    @abstractmethod
    def generate(
            self,
            underlying: UnderlyingAsset,
            index: ContractIndex,
            contract_scores: Dict[str, float]) -> Iterator[Opportunity]:
        """
        تولید فرصت‌ها بدون هیچ سربار اضافی.
        """
        pass

    # ============================================================
    # HOT PATH METHODS (ZERO ALLOCATION & NO I/O)
    # ============================================================

    def _get_S0_stock(self, underlying: UnderlyingAsset) -> float:
        """
        دریافت قیمت پایه بدون لاگ‌گذاری در صورت خطا.
        """
        try:
            val = underlying.last_price
            return float(val)
        except (AttributeError, TypeError):
            pass

        #  Telemetry به جای Logger
        self._missing_price_count += 1
        return 0.0

    # ============================================================
    # TELEMETRY & STATS
    # ============================================================

    def increment_generated(self) -> None:
        """افزایش شمارنده کاندیداهای تولید شده"""
        self._generated_count += 1

    def increment_filtered(self) -> None:
        """افزایش شمارنده کاندیداهای فیلتر شده"""
        self._filtered_count += 1

    def get_stats(self) -> Dict[str, int]:
        """دریافت آمار تولید، فیلتر و خطاها"""
        return {
            'generated': self._generated_count,
            'filtered': self._filtered_count,
            'missing_price_errors': self._missing_price_count
        }

    def reset_stats(self) -> None:
        """بازنشانی آمار"""
        self._generated_count = 0
        self._filtered_count = 0
        self._missing_price_count = 0
