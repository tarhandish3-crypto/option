# strategies/generators/base.py
# -*- coding: utf-8 -*-

"""
ماژول پایه تولیدکننده‌های استراتژی (Base Strategy Generator)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Iterator

from core.models import UnderlyingAsset, Opportunity, LegDefinition
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

    def _calculate_liquidity_score(
            self,
            legs: List[LegDefinition],
            contract_scores: Dict[str, float]) -> float:
        """
        محاسبه امتیاز نقدشوندگی بدون round و بدون List Comprehension.
        """
        if not legs:
            return 0.0

        total_score = 0.0
        min_score = float('inf')
        count = 0
        get_score = contract_scores.get

        for leg in legs:
            contract = leg.contract
            if contract is not None and contract.ticker:
                score = get_score(contract.ticker, 0.0)
                total_score += score
                if score < min_score:
                    min_score = score
                count += 1

        if count == 0:
            return 100.0

        # بازگشت خام (بدون round) - انتقال بار پردازشی به لایه Scoring
        return (min_score * 0.70) + ((total_score / count) * 0.30)

    def _get_S0_stock(self, underlying: UnderlyingAsset) -> float:
        """
        دریافت قیمت پایه بدون لاگ‌گذاری در صورت خطا.
        """
        try:
            val = underlying.close_price
            if val > 0.0:
                return float(val)
            val = underlying.last_price
            if val > 0.0:
                return float(val)
            val = underlying.yesterday_price
            if val > 0.0:
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
