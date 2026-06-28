# strategies/generators/base.py
# -*- coding: utf-8 -*-

"""
ماژول پایه تولیدکننده‌های استراتژی (Base Strategy Generator) - معماری V4

این کلاس به عنوان والد تمام ژنراتورهای تک‌لگی و چندلگی عمل می‌کند و متدهای کلیدی و مشترک 
نظیر محاسبه سنترالیزه امتیاز نقدشوندگی پوزیشن و استخراج قیمت امن دارایی پایه را فراهم می‌سازد.
شایان ذکر است کپسوله‌سازی نهایی مدل‌ها بر عهده OpportunityBuilder کارخانه مرکزی است.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Optional, Any

from core.models import OptionContract, UnderlyingAsset, Opportunity, LegDefinition
from strategies.base import StrategyDefinition

# تنظیم لوگر اختصاصی برای لایه پایه ژنراتورها
logger = logging.getLogger("OptionScanner.Strategies.Generators.Base")


class BaseGenerator(ABC):
    """
    کلاس پایه انتزاعی برای تمام ژنراتورهای استراتژی در لایه V4.
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
        """
        متد انتزاعی تولید فرصت‌ها که باید در تمام کلاس‌های فرزند (مانند StockOptionGenerator) 
        اورراید و پیاده‌سازی شود.
        """
        pass

    # ============================================================
    # متدهای مشترک و کمکی لایه پایه (Shared Production Helpers)
    # ============================================================

    def _calculate_liquidity_score(
        self,
        legs: List[LegDefinition],
        contract_scores: Dict[str, float]
    ) -> float:
        """
        محاسبه هوشمند و ترکیبی امتیاز نقدشوندگی کل پوزیشن.
        
        این متد از لنگه‌های بدون قرارداد (مانند خرید خود سهم پایه در کاورکال) پشتیبانی کرده 
        و با فرمول وزنی (۷۰٪ ضعیف‌ترین لگ به عنوان تنگنای خروج + ۳۰٪ میانگین پوزیشن) ریسک نقدشوندگی را مدل می‌کند.
        """
        if not legs:
            return 0.0

        # استخراج امتیاز فقط برای لنگه‌هایی که قرارداد اختیار معامله دارند
        scores = [
            contract_scores.get(leg.contract.ticker, 0.0)
            for leg in legs
            if leg.contract is not None and getattr(leg.contract, 'ticker', None) is not None
        ]

        if not scores:
            # اگر پوزیشن فاقد اختیار معامله باشد (مثلاً فقط سهم)، امتیاز پیش‌فرض کامل یا بالا لحاظ می‌شود
            return 100.0

        weakest = min(scores)
        avg = sum(scores) / len(scores)

        # دکترین مدیریت ریسک: ۷۰٪ ضعیف‌ترین لگ (ریسک عدم خروج) + ۳۰٪ میانگین کل پوزیشن
        return round((weakest * 0.70) + (avg * 0.30), 2)

    def _get_S0_stock(self, underlying: UnderlyingAsset) -> float:
        """
        دریافت قیمت مرجع دارایی پایه (S0) با مکانیزم Fallback زنجیره‌ای هماهنگ با بورس ایران.
        
        اولویت اول با قیمت پایانی (close_price) است تا اسکنر در پیش‌گشایش‌ها یا نوسانات فرعی دچار خطا نشود.
        """
        if getattr(underlying, 'close_price', 0) and underlying.close_price > 0:
            return underlying.close_price
        if getattr(underlying, 'last_price', 0) and underlying.last_price > 0:
            return underlying.last_price
        if getattr(underlying, 'yesterday_price', 0) and underlying.yesterday_price > 0:
            return underlying.yesterday_price

        logger.warning(
            f"قیمت معتبری برای دارایی پایه {getattr(underlying, 'ticker', 'Unknown')} یافت نشد. مقدار پیش‌فرض 0.0"
        )
        return 0.0

    def _build_base_metadata(self, custom_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        تولید ساختار اولیه و استاندارد متادیتای غنی‌شده بدون هاردکد کردن آرایه‌های سنگین محاسباتی.
        """
        metadata = {
            'generator_timestamp': datetime.now().isoformat(),
            'generator_class': self.__class__.__name__,
            'strategy_type': self.strategy_def.generator_type.value if self.strategy_def.generator_type else "UNKNOWN"
        }

        if custom_metadata:
            metadata.update(custom_metadata)

        return metadata

    # ============================================================
    # مدیریت متادیتای آماری و پایش لایه اسکنر
    # ============================================================

    def increment_generated(self) -> None:
        """افزایش شمارنده فرصت‌های کشف شده"""
        self._generated_count += 1

    def increment_filtered(self) -> None:
        """افزایش شمارنده موقعیت‌های فیلتر شده (به دلیل نقض قوانین استرایک و...)"""
        self._filtered_count += 1

    def get_stats(self) -> Dict[str, int]:
        """دریافت گزارش آماری اسکن جاری جهت مانیتورینگ سلامت انجین"""
        return {
            'generated': self._generated_count,
            'filtered': self._filtered_count
        }

    def reset_stats(self) -> None:
        """بازنشانی شمارنده‌های آماری ژنراتور برای چرخه اسکن بعدی"""
        self._generated_count = 0
        self._filtered_count = 0