# strategies/generators/four_leg.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import logging
from typing import Dict, Any, Set, Tuple, Iterator, List

from core.models import UnderlyingAsset, Opportunity, LegDefinition
from core.enums import OptionType, Side
from strategies.base import StrategyDefinition
from strategies.generators.base import BaseGenerator
from strategies.matching.contract_index import ContractIndex
from strategies.matching.pattern_matcher import PatternMatcher
from engine.opportunity_builder import OpportunityBuilder

logger = logging.getLogger("OptionScanner.Strategies.Generators.FourLeg")


class FourLegGenerator(BaseGenerator):
    """
    تولیدکننده صنعتی و کاملاً بهینه استراتژی‌های ۴ لگی (Four-Leg Generator).
    مجهز به اسکن خطی جریانی، پشتیبانی از لنگه ترکیبی سهام پایه و متادیتای تنبل.
    """

    __slots__ = ('_maturity_mode', '_include_stock')

    def __init__(self, strategy_def: StrategyDefinition):
        super().__init__(strategy_def)
        if strategy_def.legs_count != 4:
            raise ValueError(
                "FourLegGenerator نیازمند ۴ لگ معاملاتی آپشن است.")

        self._maturity_mode = (strategy_def.rules or {}).get(
            "maturity_order", "same")
        self._include_stock = getattr(strategy_def, 'include_stock', False)

    def generate(
        self,
        underlying: UnderlyingAsset,
        index: ContractIndex,
        contract_scores: Dict[str, float],
    ) -> Iterator[Opportunity]:
        """اسکن ۱۰۰٪ جریانی زنجیره بدون الیکیشن اضافه و فاقد ریسک تداخل (Collision) کلیدها"""

        base_price = self._get_S0_stock(underlying)
        if base_price <= 0:
            return

        patterns = self.strategy_def.patterns
        rules = self.strategy_def.rules or {}
        min_liq_score = rules.get("min_liquidity_score", 30.0)
        seen_keys: Set[Tuple] = set()

        # تطبیق کاملاً جریانی با PatternMatcher بدون لود کل داده‌ها در رم
        matched_sets = PatternMatcher.match_all(
            index=index,
            patterns=patterns,
            strategy_rules=rules,
            min_liquidity_score=min_liq_score,
            contract_scores=contract_scores
        )

        for matched_legs in matched_sets:
            # ۱. اعتبارسنجی سریع فواصل ریاضی استرایک‌ها
            if not self._validate_strike_gaps(matched_legs, rules):
                continue

            # ۲. تزریق پویا و بهینه لگ سهام در صورت نیاز استراتژی (مانند جید لیزارد)
            if self._include_stock:
                matched_legs = self._add_stock_leg(
                    matched_legs, underlying, base_price)

            # ۳. بررسی منحصربه‌فرد بودن موقعیت با هش‌کلید غنی‌شده جهت جلوگیری از حذف فرصت‌های معتبر
            unique_key = self._build_unique_key(matched_legs)
            if unique_key in seen_keys:
                continue
            seen_keys.add(unique_key)

            self.increment_generated()

            # ۴. تولید تنبل (Lazy) متاداتا به صورت خارج از لوپ داغ فقط برای پوزیشن نهایی
            custom_metadata = self._build_metadata_lazy(
                matched_legs, contract_scores)

            days_to_maturity = max(
                leg.contract.days_to_maturity
                for leg in matched_legs
                if leg.contract and leg.contract.option_type != OptionType.STOCK
            )

            # ۵. ساخت فرصت نهایی توسط کارخانه مرکزی سیستم
            opp = OpportunityBuilder.create_opportunity(
                strategy_name=self.strategy_def.name,
                ticker=underlying.ticker,
                legs=matched_legs,
                metrics=custom_metadata,
                days_to_maturity=days_to_maturity,
                underlying_price=base_price,
            )
            if opp is not None:
                yield opp

    # ---------------------------------------------------------
    # VALIDATION & CORE HELPERS
    # ---------------------------------------------------------

    def _validate_strike_gaps(self, legs: List[LegDefinition], rules: Dict[str, Any]) -> bool:
        """اعتبارسنجی فواصل استرایک و بررسی هندسه تقارن بال‌ها بدون ایجاد کپی اضافه"""
        strikes = [
            leg.contract.strike_price for leg in legs if leg.contract and leg.contract.option_type != OptionType.STOCK]
        if len(strikes) != 4:
            return False

        sorted_strikes = sorted(strikes)
        base_strike = max(sorted_strikes[0], 1.0)

        # بررسی تقارن ریاضی بال چپ و راست (مخصوص Iron Condor / Butterfly)
        if rules.get("enforce_symmetry", False):
            left_wing = sorted_strikes[1] - sorted_strikes[0]
            right_wing = sorted_strikes[3] - sorted_strikes[2]
            tolerance = rules.get(
                "symmetry_tolerance_pct", 0.005) * base_strike
            if abs(left_wing - right_wing) > tolerance:
                return False

        # بررسی فیلتر حداقل فاصله به صورت خطی بدون الیکیشن لیست ثانویه
        min_gap = rules.get("min_strike_gap_pct", 0.0) * base_strike
        if min_gap > 0:
            for i in range(len(sorted_strikes) - 1):
                if sorted_strikes[i + 1] - sorted_strikes[i] < min_gap:
                    return False

        return True

    def _add_stock_leg(
        self,
        legs: List[LegDefinition],
        underlying: UnderlyingAsset,
        base_price: float
    ) -> List[LegDefinition]:
        """افزودن لگ دارایی پایه به پوزیشن به شکل کاملاً کپسوله‌شده"""
        from core.models import OptionContract as OC

        stock_contract = OC(
            ticker=underlying.ticker,
            name=underlying.name,
            underlying_ticker=underlying.ticker,
            option_type=OptionType.STOCK,
            strike_price=base_price,
            contract_size=1,
            last_price=base_price,
            underlying_price=base_price,
        )

        stock_leg = LegDefinition(
            contract=stock_contract,
            side=Side.BUY,
            ratio=1,
            entry_price=base_price,
        )

        return [stock_leg] + legs

    @staticmethod
    def _build_unique_key(legs: List[LegDefinition]) -> Tuple:
        """تولید کلید امضای هش منحصربه‌فرد به همراه استرایک و نوع جهت جلوگیری از Collision"""
        return tuple(
            sorted(
                (
                    leg.contract.ticker,
                    leg.contract.strike_price,
                    leg.contract.option_type.value,
                    leg.side.value
                )
                for leg in legs
                if leg.contract and leg.contract.option_type != OptionType.STOCK
            )
        )

    @staticmethod
    def _build_metadata_lazy(legs: List[LegDefinition], contract_scores: Dict[str, float]) -> Dict[str, Any]:
        """ساخت کاملاً بهینه و تنبل متاداتا صرفاً پس از تایید نهایی و خروج موقعیت"""
        metadata: Dict[str, Any] = {}
        strikes = []

        for idx, leg in enumerate(legs, start=1):
            if not leg.contract:
                continue
            c = leg.contract

            if c.option_type != OptionType.STOCK:
                strikes.append(c.strike_price)

            metadata[f"l{idx}_ticker"] = c.ticker
            metadata[f"l{idx}_strike"] = c.strike_price
            metadata[f"l{idx}_option_type"] = c.option_type.value
            metadata[f"l{idx}_score"] = contract_scores.get(c.ticker, 0.0)

        if len(strikes) == 4:
            s_strikes = sorted(strikes)
            metadata["strike_range"] = s_strikes[-1] - s_strikes[0]
            metadata["inner_gap"] = s_strikes[2] - s_strikes[1]

        return metadata
