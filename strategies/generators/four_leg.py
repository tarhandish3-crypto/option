# strategies/generators/four_leg.py
# -*- coding: utf-8 -*-

"""
تولیدکننده جامع استراتژی‌های ۴ لگی (Four-Leg Generator) بورس ایران.
مسئول اسکن، اعتبارسنجی و کپسوله‌سازی استراتژی‌های پیچیده نظیر:
    - Iron Condor
    - Butterfly Spreads (پروانه ۴ لگی)
    - Iron Butterfly
    - Box Spread / Long Box
    - Jade Lizard
    - Double Calendar / Diagonal

کاملاً هماهنگ با معماری V4 و استفاده از PatternMatcher
"""

from __future__ import annotations

import logging
from itertools import combinations
from typing import List, Dict, Any, Set, Tuple, Iterable

from core.models import (
    OptionContract,
    UnderlyingAsset,
    Opportunity,
    LegDefinition,
)
from core.enums import GeneratorType
from strategies.base import StrategyDefinition
from strategies.generators.base import BaseGenerator
from strategies.matching.pattern_matcher import PatternMatcher
from engine.opportunity_builder import OpportunityBuilder

logger = logging.getLogger("OptionScanner.Strategies.Generators.FourLeg")


class FourLegGenerator(BaseGenerator):
    """
    تولیدکننده استاندارد و بهینه استراتژی‌های ۴ لگی بدون توابع هاردکد شده.
    """

    def __init__(self, strategy_def: StrategyDefinition):
        super().__init__(strategy_def)

        if strategy_def.generator_type != GeneratorType.FOUR_LEG:
            raise ValueError(
                f"{strategy_def.name} با FourLegGenerator سازگار نیست."
            )

        if strategy_def.legs_count != 4:
            raise ValueError(
                f"FourLegGenerator نیازمند دقیقاً ۴ لگ معاملاتی است، "
                f"دریافت {strategy_def.legs_count} لگ."
            )

        logger.debug(f"FourLegGenerator initialized for {strategy_def.name}")

    def generate(
        self,
        underlying: UnderlyingAsset,
        contracts: List[OptionContract],
        contract_scores: Dict[str, float],
    ) -> List[Opportunity]:
        """
        تولید همزمان فرصت‌های ۴ لگی با بکارگیری ترکیبات امن و فیلترهای ضربدری پرفورمنس.
        """
        opportunities: List[Opportunity] = []

        if len(contracts) < 4:
            logger.debug(
                f"{self.strategy_def.name}: Not enough contracts ({len(contracts)})"
            )
            return opportunities

        patterns = self.strategy_def.weight_pattern
        rules = self.strategy_def.rules or {}

        seen_keys: Set[Tuple] = set()
        maturity_mode = rules.get("maturity_order", "same")

        # مرحله ۱: تولید کاندیداها به صورت ژنراتور جهت حفظ بهینگی حافظه (RAM)
        candidate_iterables = self._generate_candidates(
            contracts, maturity_mode)

        # انتخاب امن‌ترین قیمت مبنای دارایی پایه
        underlying_price = underlying.close_price or underlying.last_price or 0.0

        # مرحله ۲: پردازش کاندیداها
        for candidate in candidate_iterables:
            candidate_contracts = list(candidate)

            # تطبیق الگو با PatternMatcher مرکزی V4
            matched_sets = PatternMatcher.match_all(
                contracts=candidate_contracts,
                patterns=patterns,
                strategy_rules=rules,
            )

            for matched_legs in matched_sets:
                # اعتبارسنجی استرایک‌ها (شامل تقارن بال‌ها و اینرگپ کندور)
                if not self._validate_strike_gaps(matched_legs, rules):
                    continue

                # جلوگیری از ثبت موقعیت‌های هم‌پوشان و متقارن تکراری
                unique_key = self._build_unique_key(matched_legs)
                if unique_key in seen_keys:
                    continue
                seen_keys.add(unique_key)

                # ساخت متادیتای غنی‌شده
                metadata = self._build_metadata(matched_legs, contract_scores)

                # محاسبه روزهای تا سررسید ترکیبی بر اساس دکترین طول عمر ریسک
                days_to_maturity = self._calculate_days_to_maturity(
                    matched_legs, maturity_mode
                )

                # ساخت فرصت نهایی از طریق بیلدر کارخانه مرکزی
                opp = OpportunityBuilder.create_opportunity(
                    strategy_name=self.strategy_def.name,
                    ticker=underlying.ticker,
                    legs=matched_legs,
                    metrics=metadata,
                    days_to_maturity=days_to_maturity,
                    underlying_price=underlying_price,
                )

                if opp is not None:
                    opportunities.append(opp)

        logger.info(
            "%s: %d four-leg opportunities generated",
            self.strategy_def.name,
            len(opportunities),
        )

        return opportunities

    # ---------------------------------------------------------
    # PRIVATE PRODUCTION HELPERS
    # ---------------------------------------------------------

    def _generate_candidates(
        self,
        contracts: List[OptionContract],
        maturity_mode: str
    ) -> Iterable[Tuple[OptionContract, ...]]:
        """
        تولید کاندیداها به صورت Iterable برای جلوگیری از سربار حافظه RAM بابت لیست‌های بزرگ.
        """
        if maturity_mode == "same":
            maturity_groups: Dict[int, List[OptionContract]] = {}
            for contract in contracts:
                maturity_groups.setdefault(
                    contract.days_to_maturity, []
                ).append(contract)

            for group in maturity_groups.values():
                if len(group) >= 4:
                    yield from combinations(group, 4)
        else:
            # استفاده از ساختار نمایشی مستقیم کامبینیشن بدون کست کردن به لیست
            yield from combinations(contracts, 4)

    def _calculate_days_to_maturity(
        self,
        legs: List[LegDefinition],
        maturity_mode: str
    ) -> int:
        """
        محاسبه روزهای تا سررسید بر اساس نوع آرایش زمانی استراتژی.
        """
        dtes = [
            leg.contract.days_to_maturity
            for leg in legs
            if leg.contract and leg.contract.days_to_maturity > 0
        ]

        if not dtes:
            return 30

        if maturity_mode in ["calendar", "diagonal"]:
            # در پوزیشن‌های تقویمی ناهمزمان، نزدیک‌ترین زمان اعمال ملاک چرخه نقدینگی اولیه است
            return min(dtes)
        else:
            # در استراتژی‌های عمودی هم‌زمان، ماکزیمم طول عمر ریسک ملاک است
            return max(dtes)

    # ---------------------------------------------------------
    # VALIDATION LOGIC
    # ---------------------------------------------------------

    def _validate_strike_gaps(
        self,
        legs: List[LegDefinition],
        rules: Dict[str, Any],
    ) -> bool:
        """
        اعتبارسنجی فواصل استرایک، بررسی تقارن بال‌ها (Symmetry) و شروط فرعی کندور/باترفلای.
        """
        strikes = [
            leg.contract.strike_price
            for leg in legs
            if leg.contract
        ]

        if len(strikes) != 4:
            return False

        sorted_strikes = sorted(strikes)
        base_strike = max(sorted_strikes[0], 1.0)

        # ۱. بررسی تقارن بال‌ها (Butterfly / Iron Butterfly)
        enforce_symmetry = rules.get("enforce_symmetry", False)
        if enforce_symmetry:
            left_wing = sorted_strikes[1] - sorted_strikes[0]
            right_wing = sorted_strikes[3] - sorted_strikes[2]
            tolerance = rules.get(
                "symmetry_tolerance_pct", 0.005) * base_strike

            if abs(left_wing - right_wing) > tolerance:
                return False

        # ۲. بررسی فاصله کلی بیرونی‌ترین استرایک‌ها
        min_gap_pct = rules.get("min_strike_gap_pct", 0.0)
        max_gap_pct = rules.get("max_strike_gap_pct", float("inf"))

        total_gap_pct = (sorted_strikes[-1] - sorted_strikes[0]) / base_strike
        if total_gap_pct < min_gap_pct or total_gap_pct > max_gap_pct:
            return False

        # ۳. بررسی فاصله میانی (ویژه ساختار بدنه Iron Condor)
        inner_gap_pct = (sorted_strikes[2] - sorted_strikes[1]) / base_strike
        min_inner_gap = rules.get("min_inner_gap_pct", 0.0)

        if inner_gap_pct < min_inner_gap:
            return False

        return True

    # ---------------------------------------------------------
    # STATIC CORE HELPERS
    # ---------------------------------------------------------

    @staticmethod
    def _build_unique_key(legs: List[LegDefinition]) -> Tuple:
        """
        تولید کلید هش امضا برای فیلتر ترکیب‌های جابجا شده.
        """
        return tuple(
            sorted(
                (
                    leg.contract.ticker if leg.contract else "STOCK",
                    leg.side.value,
                    leg.ratio,
                )
                for leg in legs
                if leg.contract is not None
            )
        )

    @staticmethod
    def _build_metadata(
        legs: List[LegDefinition],
        contract_scores: Dict[str, float],
    ) -> Dict[str, Any]:
        """
        غنی‌سازی و تخت‌سازی فیلدهای اطلاعاتی لنگه‌ها جهت بهره‌برداری در ماتریس تحلیل سود و زیان.
        """
        metadata: Dict[str, Any] = {}

        for idx, leg in enumerate(legs, start=1):
            if not leg.contract:
                continue

            contract = leg.contract

            metadata[f"l{idx}_ticker"] = contract.ticker
            metadata[f"l{idx}_strike"] = contract.strike_price
            metadata[f"l{idx}_dte"] = contract.days_to_maturity
            metadata[f"l{idx}_option_type"] = contract.option_type.value if contract.option_type else "UNKNOWN"
            metadata[f"l{idx}_side"] = leg.side.value
            metadata[f"l{idx}_ratio"] = leg.ratio
            metadata[f"l{idx}_score"] = contract_scores.get(
                contract.ticker, 0.0)

            # اصلاح فیلد سوددهی بر اساس دکترین صحیح دیتامدل آپشن کانتراکت
            if hasattr(contract, 'moneyness') and contract.moneyness:
                metadata[f"l{idx}_moneyness"] = str(contract.moneyness)

        # استخراج شاخص‌های پهنای باند و تقارن پوزیشن ترکیبی
        strikes = [leg.contract.strike_price for leg in legs if leg.contract]
        if len(strikes) == 4:
            sorted_strikes = sorted(strikes)
            metadata["min_strike"] = sorted_strikes[0]
            metadata["max_strike"] = sorted_strikes[-1]
            metadata["strike_range"] = sorted_strikes[-1] - sorted_strikes[0]
            metadata["inner_gap"] = sorted_strikes[2] - sorted_strikes[1]

            left_w = sorted_strikes[1] - sorted_strikes[0]
            right_w = sorted_strikes[3] - sorted_strikes[2]
            metadata["left_wing"] = left_w
            metadata["right_wing"] = right_w
            metadata["wing_symmetry"] = abs(left_w - right_w)

        # امتیاز میانگین موقعیت
        scores = [contract_scores.get(leg.contract.ticker, 0.0)
                  for leg in legs if leg.contract]
        if scores:
            metadata["avg_score"] = sum(scores) / len(scores)

        return metadata

    def get_strategy_name(self) -> str:
        """دریافت نام استراتژی مبنا"""
        return self.strategy_def.name

    def get_legs_count(self) -> int:
        """دریافت تعداد لنگه‌های تعریف شده"""
        return self.strategy_def.legs_count
