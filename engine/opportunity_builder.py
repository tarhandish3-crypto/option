# engine/opportunity_builder.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from core.models import Opportunity, LegDefinition
from core.enums import Side, OptionType
from scoring.liquidity_score import LiquidityScorer
from analytics.margin_calculator import MarginCalculator, MarginResult
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

        # ۶. کپسوله‌سازی و ساخت فرصت معاملاتی با فیلدهای کاملاً تخت
        opp = Opportunity(
            strategy_name=strategy_name,
            underlying_ticker=ticker,
            legs=legs,
            days_to_maturity=days_to_maturity,
            timestamp=datetime.now(),

            # معیارهای مالی و سرمایه‌ای واقعی
            required_margin=required_margin,
            net_premium=total_premium,

            # فیلدهای تخت شده محاسباتی
            max_profit=metadata.get("max_profit", 0.0),
            max_loss=metadata.get("max_loss", 0.0),
            pop=metadata.get("pop", 0.0),
            risk_reward_ratio=metadata.get("risk_reward_ratio", 0.0),
            expected_return_pct=metadata.get("expected_return_pct", 0.0),

            # معیارهای ریسک و عملیات بازار
            liquidity_score=liquidity_score,
            execution_score=execution_score,

            # داده‌های جانبی و یونانی‌ها
            metadata=metadata,
            break_even_points=break_even_points,

            # رتبه و امتیاز نهایی پیش‌فرض
            final_score=0.0,
            rank=0
        )

        return opp

    # ============================================================
    # ✅ متدهای جدید برای ژنراتورهای تخصصی
    # ============================================================

    @staticmethod
    def create_2leg_opportunity(
        strategy_def: Any,
        underlying: Any,
        legs: List[LegDefinition],
        days_to_maturity: int,
        contract_scores: Dict[str, float],
        include_stock: bool = False,
        underlying_price: Optional[float] = None
    ) -> Optional[Opportunity]:
        """
        ساخت فرصت معاملاتی برای استراتژی‌های ۲ لگی

        Args:
            strategy_def: تعریف استراتژی
            underlying: دارایی پایه
            legs: لیست لگ‌ها
            days_to_maturity: روز تا سررسید
            contract_scores: امتیازات نقدشوندگی
            include_stock: آیا شامل سهام است؟
            underlying_price: قیمت دارایی پایه (اختیاری)

        Returns:
            Optional[Opportunity]: فرصت معاملاتی یا None
        """
        if not legs or len(legs) != 2:
            logger.debug("create_2leg_opportunity: نیاز به ۲ لگ دارد")
            return None

        # تنظیم قیمت پایه
        if underlying_price is None:
            underlying_price = underlying.last_price if hasattr(
                underlying, 'last_price') else 0.0

        # دریافت نام استراتژی
        strategy_name = strategy_def.name if hasattr(
            strategy_def, 'name') else "unknown"

        # دریافت تیکر
        ticker = underlying.ticker if hasattr(underlying, 'ticker') else ""

        # ۱. محاسبه کل حق بیمه
        total_premium = OpportunityBuilder._calculate_total_premium(legs)

        # ۲. محاسبه وجه تضمین
        try:
            margin_result = OpportunityBuilder._calculate_required_margin(
                legs, underlying_price, ticker
            )
            required_margin = margin_result.required_margin if margin_result else 0.0
        except Exception as e:
            logger.debug(f"Margin calculation failed: {e}")
            required_margin = 0.0

        # ۳. محاسبه نقدشوندگی
        liquidity_score = OpportunityBuilder._calculate_liquidity_score(legs)

        # ۴. محاسبه امتیاز اجرا
        execution_score = OpportunityBuilder._calculate_execution_score(legs)

        # ۵. ساخت متادیتا
        metadata = OpportunityBuilder._build_leg_metadata(
            legs, contract_scores)

        # ۶. ساخت فرصت
        opp = Opportunity(
            strategy_name=strategy_name,
            underlying_ticker=ticker,
            legs=legs,
            S0_stock=underlying_price,
            days_to_maturity=days_to_maturity,
            net_premium=total_premium,
            required_margin=required_margin,
            liquidity_score=liquidity_score,
            execution_score=execution_score,
            metadata=metadata,
            timestamp=datetime.now()
        )

        return opp

    @staticmethod
    def create_3leg_opportunity(
        strategy_def: Any,
        underlying: Any,
        legs: List[LegDefinition],
        days_to_maturity: int,
        contract_scores: Dict[str, float],
        include_stock: bool = False,
        underlying_price: Optional[float] = None
    ) -> Optional[Opportunity]:
        """
        ساخت فرصت معاملاتی برای استراتژی‌های ۳ لگی
        """
        if not legs or len(legs) != 3:
            logger.debug("create_3leg_opportunity: نیاز به ۳ لگ دارد")
            return None

        return OpportunityBuilder.create_2leg_opportunity(
            strategy_def=strategy_def,
            underlying=underlying,
            legs=legs,
            days_to_maturity=days_to_maturity,
            contract_scores=contract_scores,
            include_stock=include_stock,
            underlying_price=underlying_price
        )

    @staticmethod
    def create_stock_option_opportunity(
        strategy_def: Any,
        underlying: Any,
        option_leg: LegDefinition,
        spot_price: float,
        contract_scores: Dict[str, float]
    ) -> Optional[Opportunity]:
        """
        ساخت فرصت معاملاتی برای استراتژی‌های Stock + Option (Covered Call / Married Put)

        Args:
            strategy_def: تعریف استراتژی
            underlying: دارایی پایه
            option_leg: لگ اختیار معامله
            spot_price: قیمت لحظه‌ای دارایی پایه
            contract_scores: امتیازات نقدشوندگی

        Returns:
            Optional[Opportunity]: فرصت معاملاتی یا None
        """
        from core.models import OptionContract as OC

        # ساخت لگ سهام مجازی
        stock_contract = OC(
            ticker=underlying.ticker,
            name=underlying.name,
            underlying_ticker=underlying.ticker,
            option_type=OptionType.STOCK,
            strike_price=spot_price,
            contract_size=1,
            last_price=spot_price,
            underlying_price=spot_price,
        )

        stock_leg = LegDefinition(
            contract=stock_contract,
            side=Side.BUY,
            ratio=1,
            entry_price=spot_price,
        )

        legs = [stock_leg, option_leg]

        return OpportunityBuilder.create_2leg_opportunity(
            strategy_def=strategy_def,
            underlying=underlying,
            legs=legs,
            days_to_maturity=option_leg.contract.days_to_maturity if option_leg.contract else 0,
            contract_scores=contract_scores,
            include_stock=True,
            underlying_price=spot_price
        )

    # ============================================================
    # PRIVATE HELPERS
    # ============================================================

    @staticmethod
    def _calculate_total_premium(legs: List[LegDefinition]) -> float:
        """
        محاسبه کل ارزش ریالی حق بیمه استراتژی بر اساس فرآیند عرضه و تقاضا و اندازه قرارداد.
        """
        total = 0.0
        for leg in legs:
            contract = leg.contract

            if not contract:
                logger.warning(
                    "لنگه معاملاتی فاقد ابزار کانتراکت کپسوله‌شده است. لنگه نادیده گرفته شد.")
                continue

            # استخراج ضریب قرارداد
            size = getattr(contract, "contract_size", 1) or 1

            # تعیین قیمت لنگه بر اساس عرضه/تقاضا
            if contract.option_type == OptionType.STOCK:
                entry_price = contract.last_price
            else:
                if leg.side == Side.BUY:
                    entry_price = contract.ask if contract.ask > 0 else contract.last_price
                else:
                    entry_price = contract.bid if contract.bid > 0 else contract.last_price

            premium_value = entry_price * size * leg.ratio

            if leg.side == Side.BUY:
                total += premium_value
            else:
                total -= premium_value

        return round(total, 2)

    @staticmethod
    def _calculate_required_margin(
        legs: List[LegDefinition],
        underlying_price: float,
        underlying_symbol: str = None
    ) -> Optional[MarginResult]:
        """
        محاسبه وجه تضمین مورد نیاز استراتژی.
        """
        flags = config.get_feature_flags()
        if not flags.get("calculate_margin", True):
            return None

        try:
            valid_legs = [leg for leg in legs if leg.contract is not None]
            if not valid_legs:
                return None

            return MarginCalculator.calculate_strategy_margin(
                legs=valid_legs,
                underlying_price=underlying_price,
                underlying_symbol=underlying_symbol
            )
        except Exception as e:
            logger.error(f"خطا در محاسبات مارجین ترکیبی استراتژی: {e}")
            return None

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
                scores.append(100.0)
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

        option_contracts = [
            leg.contract for leg in legs if leg.contract and leg.contract.option_type != OptionType.STOCK]

        if not option_contracts:
            return 100.0

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

    @staticmethod
    def _build_leg_metadata(
        legs: List[LegDefinition],
        contract_scores: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        ساخت متادیتا برای لگ‌ها
        """
        metadata = {}
        for idx, leg in enumerate(legs, start=1):
            if not leg.contract:
                continue
            c = leg.contract
            metadata[f"l{idx}_ticker"] = c.ticker
            metadata[f"l{idx}_strike"] = c.strike_price
            metadata[f"l{idx}_option_type"] = c.option_type.value
            metadata[f"l{idx}_score"] = contract_scores.get(c.ticker, 0.0)

        return metadata
