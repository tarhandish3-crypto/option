# strategies/generators/two_leg.py
# -*- coding: utf-8 -*-

"""
این ماژول مسئول تولید و اعتبارسنجی ترکیب‌های دو لگی برای استراتژی‌هایی مانند:
    - Bull Call Spread
    - Bear Put Spread
    - Long Straddle
    - Long Strangle
    - Long Guts
    - و سایر استراتژی‌های دو لگی
"""

from __future__ import annotations

from itertools import combinations
from datetime import datetime
from typing import List, Dict, Optional
import logging

from core.models import OptionContract, UnderlyingAsset, Opportunity, LegDefinition
from core.enums import OptionType, Side
from strategies.base import StrategyDefinition, GeneratorType
from strategies.generators.base import BaseGenerator

logger = logging.getLogger("OptionScanner.Strategies.Generators.TwoLeg")


class TwoLegGenerator(BaseGenerator):
    """
    تولیدکننده استاندارد و مقاوم برای استراتژی‌های دو لگی بورس ایران (تراز شده با لایه پایه V4)
    """

    def __init__(self, strategy_def: StrategyDefinition):
        super().__init__(strategy_def)
        assert strategy_def.generator_type == GeneratorType.TWO_LEG
        assert strategy_def.legs_count == 2, "TwoLegGenerator فقط برای استراتژی‌های ۲ لگی است"

    def generate(
        self,
        underlying: UnderlyingAsset,
        contracts: List[OptionContract],
        contract_scores: Dict[str, float]) -> List[Opportunity]:
        """
        تولید و اعتبارسنجی فرصت‌های معاملاتی ۲ لگی با غنی‌سازی متمرکز متادیتا
        """
        opportunities = []

        # ===== مرحله ۱: بررسی اولیه =====
        if len(contracts) < 2:
            logger.debug(f"{self.strategy_def.name}: Not enough contracts ({len(contracts)})")
            return opportunities

        # ===== مرحله ۲: استخراج الگوی وزنی =====
        leg_def1, leg_def2 = self.strategy_def.weight_pattern

        # ===== مرحله ۳: گروه‌بندی بر اساس سررسید =====
        maturity_groups: Dict[int, List[OptionContract]] = {}
        for contract in contracts:
            maturity_groups.setdefault(contract.days_to_maturity, []).append(contract)

        if not maturity_groups:
            logger.debug(f"{self.strategy_def.name}: No maturity groups found")
            return opportunities

        # ===== مرحله ۴: پردازش هر گروه سررسید =====
        for days_to_maturity, group_contracts in maturity_groups.items():
            if len(group_contracts) < 2:
                continue

            # مرتب‌سازی بر اساس استرایک (صعودی) و سپس نوع (Put اول)
            sorted_contracts = sorted(
                group_contracts,
                key=lambda c: (c.strike_price, 0 if c.option_type == OptionType.PUT else 1))

            # ===== مرحله ۵: تولید ترکیب‌های دوتایی =====
            for c1, c2 in combinations(sorted_contracts, 2):
                
                # ۵-الف: تطابق الگوی وزنی
                legs = self._match_pattern(c1, c2, leg_def1, leg_def2)
                if not legs:
                    continue

                # ۵-ب: اعمال قوانین استرایک
                if not self._apply_leg_strike_rules(legs):
                    continue

                # ۵-ج: ساخت متادیتای اختصاصی این فرزند جهت ادغام با والد
                l1_strike = legs[0].contract.strike_price
                l2_strike = legs[1].contract.strike_price
                strike_distance_pct = abs(l1_strike - l2_strike) / min(l1_strike, l2_strike) if min(l1_strike, l2_strike) > 0 else 0.0

                local_metadata = {
                    "l1_ticker": legs[0].contract.ticker,
                    "l2_ticker": legs[1].contract.ticker,
                    "l1_strike": l1_strike,
                    "l2_strike": l2_strike,
                    "strike_distance_pct": strike_distance_pct,
                }

                # ۵-د: ارجاع فرآیند ساخت به کارخانه لایه پایه (حل قطعی باگ عدم تزریق S0_stock)
                opp = self._create_opportunity(
                    legs=legs,
                    underlying=underlying,
                    days_to_maturity=days_to_maturity,
                    contract_scores=contract_scores,
                    base_metadata=local_metadata
                )

                if opp:
                    opportunities.append(opp)

        logger.info(f"{self.strategy_def.name}: Generated {len(opportunities)} opportunities")
        return opportunities

    def _match_pattern(
        self,
        c1: OptionContract,
        c2: OptionContract,
        leg_def1,
        leg_def2
    ) -> Optional[List[LegDefinition]]:
        """
        تطابق الگوی وزنی با نوع قراردادها و تعیین سمت معامله
        """
        opt_type1 = leg_def1.option_type if hasattr(leg_def1, 'option_type') else leg_def1[0]
        weight1 = leg_def1.weight if hasattr(leg_def1, 'weight') else leg_def1[1]

        opt_type2 = leg_def2.option_type if hasattr(leg_def2, 'option_type') else leg_def2[0]
        weight2 = leg_def2.weight if hasattr(leg_def2, 'weight') else leg_def2[1]

        if isinstance(opt_type1, str):
            opt_type1 = OptionType.PUT if opt_type1.strip().lower() in ["put", "p"] else OptionType.CALL
        if isinstance(opt_type2, str):
            opt_type2 = OptionType.PUT if opt_type2.strip().lower() in ["put", "p"] else OptionType.CALL

        if c1.option_type == opt_type1 and c2.option_type == opt_type2:
            return [
                LegDefinition(contract=c1, side=Side.BUY if weight1 > 0 else Side.SELL, ratio=abs(int(weight1))),
                LegDefinition(contract=c2, side=Side.BUY if weight2 > 0 else Side.SELL, ratio=abs(int(weight2)))
            ]

        if c1.option_type == opt_type2 and c2.option_type == opt_type1:
            return [
                LegDefinition(contract=c2, side=Side.BUY if weight1 > 0 else Side.SELL, ratio=abs(int(weight1))),
                LegDefinition(contract=c1, side=Side.BUY if weight2 > 0 else Side.SELL, ratio=abs(int(weight2)))
            ]

        return None

    def _apply_leg_strike_rules(self, legs: List[LegDefinition]) -> bool:
        """
        اعمال قوانین استرایک بر روی لگ‌های چیده‌شده
        """
        rules = self.strategy_def.rules
        if len(legs) < 2:
            return False

        l1_strike = legs[0].contract.strike_price
        l2_strike = legs[1].contract.strike_price

        if rules.get("strike_equal", False):
            if abs(l1_strike - l2_strike) > 10.0:
                return False

        strike_order = rules.get("strike_order")
        if strike_order == "ascending":
            if l1_strike >= l2_strike:
                return False
        elif strike_order == "descending":
            if l1_strike <= l2_strike:
                return False

        min_gap_pct = rules.get("min_strike_gap_pct", 0.0)
        max_gap_pct = rules.get("max_strike_gap_pct", 1.0)

        if min_gap_pct > 0 or max_gap_pct < 1.0:
            base_strike = min(l1_strike, l2_strike)
            if base_strike > 0:
                gap_pct = abs(l2_strike - l1_strike) / base_strike
                if gap_pct < min_gap_pct or gap_pct > max_gap_pct:
                    return False

        return True