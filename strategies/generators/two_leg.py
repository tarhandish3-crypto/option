# strategies/generators/two_leg.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import logging
from typing import Dict, Any, Iterator, List

from core.models import OptionContract, UnderlyingAsset, Opportunity, LegDefinition
from core.enums import OptionType, GeneratorType
from strategies.base import StrategyDefinition
from strategies.generators.base import BaseGenerator
from strategies.matching.contract_index import ContractIndex
from strategies.matching.pattern_matcher import PatternMatcher
from engine.opportunity_builder import OpportunityBuilder

logger = logging.getLogger("OptionScanner.Strategies.Generators.TwoLeg")


class TwoLegGenerator(BaseGenerator):
    """
    تولیدکننده نهایی، صنعتی و ۱۰۰٪ بدون وضعیت (Stateless) استراتژی‌های ۲ لگی.
    پایبند به اصول لایه‌بندی خالص و هدایت جریانی داده‌ها بدون اورهد پردازشی در لوپ داغ.
    """

    __slots__ = ('_maturity_mode', '_include_stock')

    def __init__(self, strategy_def: StrategyDefinition):
        super().__init__(strategy_def)

        if strategy_def.generator_type != GeneratorType.TWO_LEG:
            raise ValueError(f"{strategy_def.name} با TwoLegGenerator سازگار نیست.")

        if strategy_def.legs_count != 2:
            raise ValueError("TwoLegGenerator نیازمند دقیقاً ۲ لگ معاملاتی است.")

        rules = strategy_def.rules or {}
        self._maturity_mode = rules.get("maturity_order", "same")
        self._include_stock = getattr(strategy_def, 'include_stock', False)

    def generate(
        self,
        underlying: UnderlyingAsset,
        index: ContractIndex,  # کانتراکت ایندکس بهینه شده و تزریقی از بیرون
        contract_scores: Dict[str, float],
    ) -> Iterator[Opportunity]:
        """اسکن ۱۰۰٪ جریانی، بدون تخصیص حافظه محلی و کاملاً Stateless"""
        
        base_price = self._get_S0_stock(underlying)
        if base_price <= 0:
            return

        rules = self.strategy_def.rules or {}
        patterns = self.strategy_def.patterns

        # بررسی O(1) نقدینگی و زنده بودن زنجیره جهت Early Abort سریع
        if index.is_empty:
            return

        # فراخوانی جریانی مچر با واگذاری کامل فرآیند Dedup به لایه بومی برای حداکثر سرعت
        matched_sets = PatternMatcher.match_all(
            index=index,
            patterns=patterns,
            strategy_rules=rules,
            contract_scores=contract_scores,
            dedup=True  # اعمال بهینه ددات در مبدا تولید الگوها
        )

        for matched_legs in matched_sets:
            # ۱. اعتبارسنجی درجا و فوق‌سریع فواصل ریاضی استرایک‌ها
            if not self._validate_strike_gaps(matched_legs, rules):
                continue

            # ۲. استخراج زمان سررسید موقعیت ترکیبی با گارد دارایی پایه (Stock-Safe Guard)
            days_to_maturity = 0
            for leg in matched_legs:
                if leg.contract and leg.contract.option_type != OptionType.STOCK:
                    days_to_maturity = leg.contract.days_to_maturity
                    break

            # ۳. تحویل جفت لگ نهایی به کارخانه بیلدر جهت ساخت شیء مالتی‌ترید اپورچونیتی
            opp = OpportunityBuilder.create_2leg_opportunity(
                strategy_def=self.strategy_def,
                underlying=underlying,
                legs=matched_legs,
                days_to_maturity=days_to_maturity,
                contract_scores=contract_scores,
                include_stock=self._include_stock
            )

            if opp is not None:
                self.increment_generated()
                yield opp

    # ============================================================
    # HIGH-PERFORMANCE STATIC HELPERS (NO ALLOCATION)
    # ============================================================

    def _validate_strike_gaps(self, legs: List[LegDefinition], rules: Dict[str, Any]) -> bool:
        """اعتبارسنجی فرکانس بالا و ریاضی فواصل استرایک‌ها بدون کپی حافظه یا چرخاندن لوپ اضافی"""
        if len(legs) != 2 or not legs[0].contract or not legs[1].contract:
            return False

        c1, c2 = legs[0].contract, legs[1].contract
        # در صورت تزریق لگ فیزیکی سهام، کنترل فواصل استرایک گزینه‌ای اختیاری/متروک است
        if c1.option_type == OptionType.STOCK or c2.option_type == OptionType.STOCK:
            return True

        strike1 = c1.strike_price
        strike2 = c2.strike_price
        
        # گارد ریاضی مطلق جهت جلوگیری از خطای تقسیم بر صفر ناشی از دیتای خراب بازار
        base = float(strike1 if strike1 < strike2 else strike2)
        if base <= 0.0:
            base = 1.0

        # الف) کنترل شرط هم‌استرایک بودن پوزیشن‌ها (مانند استرادل‌ها)
        if rules.get("strike_equal", False):
            tolerance_pct = rules.get("strike_equal_tolerance_pct", 0.005)
            if (abs(strike1 - strike2) / base) > tolerance_pct:
                return False

        # ب) کنترل دقیق کران‌های حداقل و حداکثر فواصل مجاز درصدی استرایک‌ها از یکدیگر
        min_gap_pct = rules.get("min_strike_gap_pct", 0.0)
        max_gap_pct = rules.get("max_strike_gap_pct", 999.0)
        gap_pct = abs(strike2 - strike1) / base

        return min_gap_pct <= gap_pct <= max_gap_pct