# strategies/generators/base.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from datetime import datetime
import logging

from core.models import OptionContract, UnderlyingAsset, Opportunity, LegDefinition
from strategies.base import StrategyDefinition

# تنظیم لوگر اختصاصی برای لایه پایه ژنراتورها
logger = logging.getLogger("OptionScanner.Strategies.Generators.Base")


class BaseGenerator(ABC):
    """
    کلاس پایه تولیدکننده ترکیب‌های استراتژی (معماری V4)

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
            contract_scores: Dict[str, float]) -> List[Opportunity]:
        """تولید فرصت‌ها (باید در کلاس‌های فرزند پیاده‌سازی و اورراید شود)"""
        pass

    def _calculate_liquidity_score(
            self,
            legs: List[LegDefinition],
            contract_scores: Dict[str, float]) -> float:
        """
        محاسبه امتیاز نقدشوندگی با پشتیبانی از لگ‌های بدون قرارداد (مانند لگ سهم در Covered Call)
        """
        if not legs:
            return 0.0

        scores = [
            contract_scores.get(leg.contract.ticker, 0.0)
            for leg in legs
            if leg.contract is not None and hasattr(leg.contract, 'ticker')
        ]

        if not scores:
            return 0.0

        weakest = min(scores)
        avg = sum(scores) / len(scores)

        # وزن‌دهی ترکیبی: ۷۰٪ ضعیف‌ترین لگ (تنگنای خروج) + ۳۰٪ میانگین کل پوزیشن
        return (weakest * 0.70) + (avg * 0.30)

    def _get_S0_stock(self, underlying: UnderlyingAsset) -> float:
        """
        دریافت قیمت روز دارایی پایه از شیء underlying با مکانیزم Fallback زنجیره‌ای اولویت‌دار
        """
        if hasattr(underlying, 'last_price') and underlying.last_price > 0:
            return underlying.last_price
        if hasattr(underlying, 'close_price') and underlying.close_price > 0:
            return underlying.close_price
        if hasattr(underlying, 'yesterday_price') and underlying.yesterday_price > 0:
            return underlying.yesterday_price

        logger.warning(
            f"S0_stock not found or invalid for {getattr(underlying, 'ticker', 'Unknown')}, using default 0.0")
        return 0.0

    def _build_enriched_metadata(
            self,
            base_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        ساخت متادیتای غنی‌شده متمرکز - بدون ذخیره داده‌های تکراری لایه اول
        """

        enriched_metadata = {
            'timestamp': datetime.now().isoformat(),

            # فیلدهای آرایه‌ای و غیرساختاریافته سنگین نمودار پِی‌آف
            'net_profits_closed': [],
            'net_profits_exercised': [],
            'gross_profits': [],
            'price_levels': [],
            'profitable_indices': [],
            'dynamic_range': [],
            'recommended_action': 'recommended_action',
        }

        # ادغام مابقی دیتای خاص فرعی (بدون فیلدهای پاپ شده لایه اول)
        if base_metadata:
            enriched_metadata.update(base_metadata)

        return enriched_metadata

    def _create_opportunity(
            self,
            legs: List[LegDefinition],
            underlying: UnderlyingAsset,
            days_to_maturity: int,
            contract_scores: Dict[str, float],
            base_metadata: Optional[Dict[str, Any]] = None,) -> Optional[Opportunity]:
        """
        کارخانه ساخت متمرکز شیء Opportunity (اصلاح‌شده: فاقد هم‌پوشانی و داده موازی)
        """
        if not legs:
            return None

        if base_metadata is None:
            base_metadata = {}

        # ۱. استخراج کامل فیلدهای عددی و ساختاریافته اصلی از دیتای فرزند جهت جلوگیری از تکرار در متادیتا
        S0_stock = self._get_S0_stock(underlying)

        # ۲. محاسبه امتیاز نقدشوندگی لگ‌ها
        liquidity_score = self._calculate_liquidity_score(
            legs, contract_scores)

        # ۳. تولید متادیتای غنی‌شده منحصربه‌فرد (فیلدهای بالا قبلاً pop شده‌اند)
        enriched_metadata = self._build_enriched_metadata(
            base_metadata=base_metadata,)

        # ۴. قالب‌بندی و کپسوله‌سازی مدل رسمی با فیلدهای منحصربه‌فرد در لایه اول
        opportunity = Opportunity(
            strategy_name=self.strategy_def.name,
            underlying_ticker=underlying.ticker,
            legs=legs,
            S0_stock=S0_stock,
            days_to_maturity=days_to_maturity,
            net_premium=0.0,
            max_profit=0.0,
            max_loss=0.0,
            break_even_points=[],
            required_margin=0.0,
            risk_reward_ratio=0.0,
            expected_return_pct=0.0,
            max_profit_pct=0.0,
            max_loss_pct=0.0,
            liquidity_score=round(liquidity_score, 2),
            final_score=0.0,
            rank=0,
            metadata=enriched_metadata)

        self._generated_count += 1

        logger.debug(
            f"Successfully instantiated clean Opportunity object: {self.strategy_def.name} on {opportunity.underlying_ticker} ")

        return opportunity

    def get_stats(self) -> Dict[str, int]:
        """دریافت گزارش آماری از تعداد موقعیت‌های اسکن شده جاری"""
        return {
            'generated': self._generated_count,
            'filtered': self._filtered_count}

    def reset_stats(self) -> None:
        """بازنشانی شمارنده‌های آماری ژنراتور"""
        self._generated_count = 0
        self._filtered_count = 0
