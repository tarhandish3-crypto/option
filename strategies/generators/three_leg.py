# strategies/generators/three_leg.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import logging
from typing import Dict, Any, Set, Tuple, Iterator, List

from core.models import UnderlyingAsset, Opportunity, LegDefinition
from core.enums import OptionType, GeneratorType
from strategies.base import StrategyDefinition
from strategies.generators.base import BaseGenerator
from strategies.matching.contract_index import ContractIndex
from strategies.matching.pattern_matcher import PatternMatcher
from engine.opportunity_builder import OpportunityBuilder

logger = logging.getLogger("OptionScanner.Strategies.Generators.ThreeLeg")


class ThreeLegGenerator(BaseGenerator):
    """
    تولیدکننده نهایی و خطی استراتژی‌های ۳ لگی (Three-Leg Generator).
    طراحی شده با متدولوژی Push-down Filtering، فاقد سورت داینامیک و کاملاً ایمن در حجم معاملات بالا.
    """

    __slots__ = ('_maturity_mode', '_include_stock', '_strategy_name_lower')

    def __init__(self, strategy_def: StrategyDefinition):
        super().__init__(strategy_def)

        if strategy_def.generator_type != GeneratorType.THREE_LEG:
            raise ValueError(
                f"{strategy_def.name} با ThreeLegGenerator سازگار نیست.")

        rules = strategy_def.rules or {}
        self._maturity_mode = rules.get("maturity_order", "same")
        self._include_stock = getattr(strategy_def, 'include_stock', False)
        self._strategy_name_lower = strategy_def.name.lower().strip()

    def generate(
        self,
        underlying: UnderlyingAsset,
        index: ContractIndex,
        contract_scores: Dict[str, float],
    ) -> Iterator[Opportunity]:
        """اسکن فوق‌سریع و جریانی با تکنیک Candidate Planner مینی‌مال شده بدون ریسک ساخت پرموتیشن‌های هرز"""

        base_price = self._get_S0_stock(underlying)
        if base_price <= 0 or index.is_empty:
            return

        rules = self.strategy_def.rules or {}
        min_liq_score = rules.get("min_liquidity_score", 30.0)

        # ⚡ Push-down Filtering با PatternMatcher
        patterns = self.strategy_def.patterns
        matched_sets = PatternMatcher.match_all(
            index=index,
            patterns=patterns,
            strategy_rules=rules,
            min_liquidity_score=min_liq_score,
            contract_scores=contract_scores,
            underlying_price=base_price
        )

        # بهینه‌سازی فضایی حافظه برای دیتای بسیار حجیم
        seen_keys: Set[Tuple[int, ...]] = set()

        for matched_legs in matched_sets:
            # ۳. بهینه‌سازی درجا (In-place Ratio Modification) بدون کپی یا نیو کردن پوزیشن
            if len(matched_legs) == 2 and self._strategy_name_lower in ["strap", "strip"]:
                target_type = OptionType.CALL if self._strategy_name_lower == "strap" else OptionType.PUT
                for leg in matched_legs:
                    if leg.contract and leg.contract.option_type == target_type:
                        leg.ratio = 2

            # ۴. حذف کامپوننت سنگین sorted() و جایگزینی با پیش‌فرض Canonical Ordering الگوها
            # به جای ترکیب رشته‌ها، از شناسه عددی کانتراکت‌ها (یا ترکیبی از متغیرهای عددی ثابت) استفاده می‌کنیم.
            unique_key = self._build_canonical_key(matched_legs)
            if unique_key in seen_keys:
                continue
            seen_keys.add(unique_key)

            self.increment_generated()

            # ۵. استخراج زمان سررسید با گارد محافظتی دارایی پایه (Stock-Safe DTE Guard)
            days_to_maturity = 0
            for leg in matched_legs:
                if leg.contract and leg.contract.option_type != OptionType.STOCK:
                    days_to_maturity = leg.contract.days_to_maturity
                    break

            # ۶. ارسال پوزیشن خالص معاملاتی به کارخانه بیلدر برای محاسبات ریاضی سنگین متاداتا
            opp = OpportunityBuilder.create_3leg_opportunity(
                strategy_def=self.strategy_def,
                underlying=underlying,
                legs=matched_legs,
                days_to_maturity=days_to_maturity,
                underlying_price=base_price,
                contract_scores=contract_scores,
                include_stock=self._include_stock
            )

            if opp is not None:
                yield opp

    # ============================================================
    # HIGH-PERFORMANCE STATIC CALCULATION HELPERS
    # ============================================================

    @staticmethod
    def _build_canonical_key(legs: List[LegDefinition]) -> Tuple[int, ...]:
        """
        🔥 رفع ایراد ۲.۲: حذف کامل متد ()sorted و پردازش رشته‌ها.
        استفاده از ترتیب ذاتی (Canonical) کانتراکت‌ها بر اساس شناسه یکتا یا هش عددی فیلدها.
        """
        # از آنجا که پترن مچر کانتراکت‌ها را با ترتیب مشخصی از ورودی‌های ایندکس خارج می‌کند،
        # ترتیب لنگه‌ها از قبل در لایه مچر استاندارد (Deterministic) شده است.
        return tuple(
            hash((
                leg.contract.ticker,
                leg.contract.strike_price,
                leg.contract.option_type.value,
                leg.side.value,
                leg.ratio
            ))
            for leg in legs if leg.contract
        )
