# engine/opportunity_builder.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from core.models import Opportunity, LegDefinition
from core.enums import Side, OptionType
from scoring.liquidity_score import LiquidityScorer
from analytics.margin_calculator import MarginCalculator
import config

logger = logging.getLogger("OptionScanner.Engine.OpportunityBuilder")


class OpportunityBuilder:
    """
    کارخانه پیشرفته و صنعتی تبدیل لنگه‌های ساختاریافته به شیء نهایی Opportunity
    با اعمال ضریب قرارداد بورس تهران، فیلترینگ هوشمند سهم پایه و نگاشت مستقیم ماتریس ریسک.
    """

    @staticmethod
    def create_opportunity(
        strategy_name: str,
        ticker: str,
        legs: List[LegDefinition],
        days_to_maturity: int,
        metrics: Optional[Dict[str, Any]] = None,
        underlying_price: float = 0.0,
        break_even_points: Optional[List[float]] = None
    ) -> Opportunity:
        """
        ساخت، محاسبه و تنظیم فیلدهای تخت و ساختاریافته مدل Opportunity
        """
        metadata = metrics or {}

        # ۱. محاسبه کل حق بیمه واقعی با احتساب Contract Size بورس ایران
        total_premium = OpportunityBuilder._calculate_total_premium(legs)

        # ۲. محاسبه وجه تضمین کل (پاس دادن کل لنگه‌ها برای استراتژی‌های اسپرد)
        required_margin = OpportunityBuilder._calculate_required_margin(
            legs, underlying_price)

        # ۳. محاسبه امتیاز نقدشوندگی
        liquidity_score = OpportunityBuilder._calculate_liquidity_score(legs)

        # ۴. محاسبه امتیاز قابلیت اجرا (بدون دخالت دادن حجم سهم پایه)
        execution_score = OpportunityBuilder._calculate_execution_score(legs)

        # ۵. استخراج نقاط سربه‌سر
        if break_even_points is None:
            break_even_points = metadata.get("break_even_points", [])

        # ۶. کپسوله‌سازی و ساخت فرصت معاملاتی با فیلدهای کاملاً تخت (رفع ایراد شماره ۴)
        opp = Opportunity(
            strategy_name=strategy_name,
            underlying_ticker=ticker,
            legs=legs,
            days_to_maturity=days_to_maturity,
            timestamp=datetime.now(),

            # معیارهای مالی و سرمایه‌ای واقعی
            required_margin=required_margin,
            net_premium=total_premium,

            # فیلدهای تخت شده محاسباتی (امپراتوری متریک‌ها روی شیء اصلی)
            max_profit=metadata.get("max_profit", 0.0),
            max_loss=metadata.get("max_loss", 0.0),
            pop=metadata.get("pop", 0.0),
            risk_reward_ratio=metadata.get("risk_reward_ratio", 0.0),
            expected_return_pct=metadata.get("expected_return_pct", 0.0),

            # معیارهای ریسک و عملیات بازار
            liquidity_score=liquidity_score,
            execution_score=execution_score,

            # داده‌های جانبی و یونانی‌ها (Delta, Gamma, Vega, Theta)
            metadata=metadata,
            break_even_points=break_even_points,

            # رتبه و امتیاز نهایی پیش‌فرض
            final_score=0.0,
            rank=0
        )

        return opp

    @staticmethod
    def _calculate_total_premium(legs: List[LegDefinition]) -> float:
        """
        محاسبه کل ارزش ریالی حق بیمه استراتژی بر اساس فرآیند عرضه و تقاضا و اندازه قرارداد.

        Formula: Sum(Entry Price * Contract Size * Ratio)
        """
        total = 0.0
        for leg in legs:
            contract = leg.contract

            # 🛠️ رفع ایراد شماره ۵: هشدار برای لنگه بدون قرارداد
            if not contract:
                logger.warning(
                    f"لنگه معاملاتی فاقد ابزار کانتراکت کپسوله‌شده است. لنگه نادیده گرفته شد.")
                continue

            # استخراج ضریب قرارداد (برای سهام عادی به صورت پیش‌فرض ۱ در نظر گرفته می‌شود اگر فیلد پر نباشد)
            size = getattr(contract, "contract_size", 1) or 1

            # تعیین قیمت لنگه بر اساس عرضه/تقاضا
            if contract.option_type == OptionType.STOCK:
                entry_price = contract.last_price
            else:
                if leg.side == Side.BUY:
                    entry_price = contract.ask if contract.ask > 0 else contract.last_price
                else:
                    entry_price = contract.bid if contract.bid > 0 else contract.last_price

            # 🛠️ رفع ایراد شماره ۱ و ۲: ضرب دقیق در اندازه قرارداد (Contract Size)
            premium_value = entry_price * size * leg.ratio

            if leg.side == Side.BUY:
                total += premium_value
            else:
                total -= premium_value

        return round(total, 2)

    @staticmethod
    def _calculate_required_margin(legs: List[LegDefinition], underlying_price: float) -> float:
        """
        محاسبه وجه تضمین مورد نیاز استراتژی.
        اگر feature flag مارجین غیرفعال باشد، صفر برمی‌گرداند.
        """
        flags = config.get_feature_flags()
        if not flags.get("calculate_margin", True):
            return 0.0

        try:
            margin_result = MarginCalculator.calculate_strategy_margin(legs, underlying_price)
            return round(margin_result.required_margin, 2)
        except Exception as e:
            logger.error(f"خطا در محاسبات مارجین ترکیبی استراتژی: {e}")

        # Fallback به محاسبات تک‌لگی در صورت خطای لایه مارجین
        total_margin = 0.0
        for leg in legs:
            if leg.side == Side.SELL:
                contract = leg.contract
                if not contract or contract.option_type == OptionType.STOCK:
                    continue
                margin_info = MarginCalculator.calculate_contract_margin(
                    contract=contract,
                    underlying_price=underlying_price or contract.underlying_price
                )
                total_margin += margin_info.get("required_margin", 0.0) * leg.ratio

        return round(total_margin, 2)

    @staticmethod
    def _calculate_liquidity_score(legs: List[LegDefinition]) -> float:
        """
        محاسبه امتیاز نقدشوندگی استراتژی بر مبنای جریمه ضعیف‌ترین لنگه معاملاتی.
        """
        if not legs:
            return 0.0

        scores = []
        for leg in legs:
            contract = leg.contract
            if not contract:
                continue

            if contract.option_type == OptionType.STOCK:
                scores.append(100.0)  # نقدشوندگی کامل دارایی پایه در بورس
            else:
                score = LiquidityScorer.score_single_contract(contract)
                scores.append(score)

        if not scores:
            return 0.0

        return round((min(scores) * 0.70) + ((sum(scores) / len(scores)) * 0.30), 2)

    @staticmethod
    def _calculate_execution_score(legs: List[LegDefinition]) -> float:
        """
        محاسبه امتیاز ریسک لغزش قیمت بر برآیند همزمان لنگه‌های آپشن.
        """
        if not legs:
            return 0.0

        # 🛠️ رفع ایراد شماره ۶: استخراج لنگه‌ها به استثنای دارایی پایه (STOCK)
        # زیرا حجم میلیونی معاملات سهم پایه نباید عمق کم آپشن‌ها را پنهان کند.
        option_contracts = [
            leg.contract for leg in legs if leg.contract and leg.contract.option_type != OptionType.STOCK]

        if not option_contracts:
            return 100.0  # استراتژی‌های صرفاً شامل سهام ریسک لغزش ابزار مشتقه ندارند

        min_volume = min((c.volume for c in option_contracts), default=0)
        min_oi = min((c.open_interest for c in option_contracts), default=0)

        max_spread = 0.0
        for contract in option_contracts:
            if contract.bid > 0 and contract.ask > 0:
                spread = (contract.ask - contract.bid) / \
                    ((contract.bid + contract.ask) / 2)
                max_spread = max(max_spread, spread)

        score = 100.0

        if min_volume < 50:
            score -= 30
        elif min_volume < 200:
            score -= 15

        if min_oi < 20:
            score -= 25
        elif min_oi < 100:
            score -= 12

        if max_spread > 0.15:
            score -= 30
        elif max_spread > 0.10:
            score -= 20
        elif max_spread > 0.05:
            score -= 10

        score -= (len(legs) - 1) * 5

        return max(0.0, round(score, 2))
