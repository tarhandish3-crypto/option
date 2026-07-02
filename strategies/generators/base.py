# strategies/generators/base.py
# -*- coding: utf-8 -*-
"""
ماژول پایه تولیدکننده‌های استراتژی (Base Strategy Generator) - معماری V4
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Optional, Any

import numpy as np

from core.models import OptionContract, UnderlyingAsset, Opportunity, LegDefinition
from strategies.base import StrategyDefinition
from config import get_price_levels, get_price_steps

logger = logging.getLogger("OptionScanner.Strategies.Generators.Base")


class BaseGenerator(ABC):
    """
    کلاس پایه انتزاعی برای تمام ژنراتورهای استراتژی
    """

    def __init__(self, strategy_def: StrategyDefinition):
        self.strategy_def = strategy_def
        self._generated_count = 0
        self._filtered_count = 0

    @abstractmethod
    def generate(
        self,
        underlying: UnderlyingAsset,
        contracts: List[OptionContract],
        contract_scores: Dict[str, float]
    ) -> List[Opportunity]:
        """متد انتزاعی تولید فرصت‌ها"""
        pass

    # ============================================================
    # متدهای مشترک
    # ============================================================

    def _calculate_liquidity_score(
        self,
        legs: List[LegDefinition],
        contract_scores: Dict[str, float]
    ) -> float:
        """محاسبه امتیاز نقدشوندگی پوزیشن"""
        if not legs:
            return 0.0

        scores = [
            contract_scores.get(leg.contract.ticker, 0.0)
            for leg in legs
            if leg.contract is not None and leg.contract.ticker
        ]

        if not scores:
            return 100.0  # فقط سهم پایه

        weakest = min(scores)
        avg = sum(scores) / len(scores)

        return round((weakest * 0.70) + (avg * 0.30), 2)

    def _get_S0_stock(self, underlying: UnderlyingAsset) -> float:
        """دریافت قیمت مرجع دارایی پایه با Fallback"""
        if getattr(underlying, 'close_price', 0) > 0:
            return underlying.close_price
        if getattr(underlying, 'last_price', 0) > 0:
            return underlying.last_price
        if getattr(underlying, 'yesterday_price', 0) > 0:
            return underlying.yesterday_price

        logger.warning(f"قیمت معتبری برای {underlying.ticker} یافت نشد.")
        return 0.0

    def _build_base_metadata(self, custom_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """ساخت متادیتای پایه"""
        metadata = {
            'generator_timestamp': datetime.now().isoformat(),
            'generator_class': self.__class__.__name__,
            'strategy_type': self.strategy_def.generator_type.value,
            'price_levels': get_price_levels(10000.0).tolist(),  # سطوح متمرکز
            'pct_steps': get_price_steps().tolist(),
        }

        if custom_metadata:
            metadata.update(custom_metadata)

        return metadata

    # ============================================================
    # مدیریت آمار
    # ============================================================

    def increment_generated(self) -> None:
        self._generated_count += 1

    def increment_filtered(self) -> None:
        self._filtered_count += 1

    def get_stats(self) -> Dict[str, int]:
        return {
            'generated': self._generated_count,
            'filtered': self._filtered_count
        }

    def reset_stats(self) -> None:
        self._generated_count = 0
        self._filtered_count = 0
