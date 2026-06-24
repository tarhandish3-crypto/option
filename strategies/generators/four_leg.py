# strategies/generators/four_leg.py
# -*- coding: utf-8 -*-

"""
تولیدکننده استراتژی‌های ۴ لگی (Four-Leg Generator) متصل به خط لوله داده لایه پایه
"""

from __future__ import annotations

from typing import List, Dict, Optional
from datetime import datetime
import logging

from core.models import OptionContract, UnderlyingAsset, Opportunity, LegDefinition
from core.enums import OptionType, Side
from strategies.base import StrategyDefinition, GeneratorType
from strategies.generators.base import BaseGenerator

logger = logging.getLogger("OptionScanner.Strategies.Generators.FourLeg")


class FourLegGenerator(BaseGenerator):
    """
    تولیدکننده استراتژی‌های ۴ لگی بورس ایران
    """

    def __init__(self, strategy_def: StrategyDefinition):
        super().__init__(strategy_def)
        assert strategy_def.generator_type == GeneratorType.FOUR_LEG
        assert strategy_def.legs_count == 4, "FourLegGenerator فقط برای استراتژی‌های ۴ لگی است"

    def generate(
        self,
        underlying: UnderlyingAsset,
        contracts: List[OptionContract],
        contract_scores: Dict[str, float]
    ) -> List[Opportunity]:
        """تولید فرصت‌های ۴ لگی و هماهنگ‌سازی با متد کارخانه والد"""
        opportunities = []

        if len(contracts) < 4:
            return opportunities

        leg_defs = self.strategy_def.weight_pattern

        # ===== مرحله ۱: گروه‌بندی بر اساس سررسید =====
        maturity_groups: Dict[int, List[OptionContract]] = {}
        for contract in contracts:
            maturity_groups.setdefault(contract.days_to_maturity, []).append(contract)

        if not maturity_groups:
            logger.debug(f"{self.strategy_def.name}: No maturity groups found")
            return opportunities

        # ===== مرحله ۲: پردازش هر گروه سررسید =====
        for days_to_maturity, group_contracts in maturity_groups.items():
            if len(group_contracts) < 4:
                continue

            calls = [c for c in group_contracts if c.option_type == OptionType.CALL]
            puts = [c for c in group_contracts if c.option_type == OptionType.PUT]

            strat_name = self.strategy_def.name.lower().strip()

            if "iron_condor" in strat_name:
                opportunities.extend(self._generate_iron_condor(
                    calls, puts, underlying, days_to_maturity, contract_scores, leg_defs
                ))

            elif "long_box" in strat_name:
                opportunities.extend(self._generate_long_box(
                    calls, puts, underlying, days_to_maturity, contract_scores, leg_defs
                ))

        logger.info(f"{self.strategy_def.name}: Generated {len(opportunities)} opportunities")
        return opportunities

    def _generate_iron_condor(
        self,
        calls: List[OptionContract],
        puts: List[OptionContract],
        underlying: UnderlyingAsset,
        days_to_maturity: int,
        contract_scores: Dict[str, float],
        leg_defs: list
    ) -> List[Opportunity]:
        """تولید Iron Condor: put_low < put_high < call_low < call_high"""
        opportunities = []

        if len(puts) < 2 or len(calls) < 2:
            return opportunities

        puts_sorted = sorted(puts, key=lambda c: c.strike_price)
        calls_sorted = sorted(calls, key=lambda c: c.strike_price)

        for i in range(len(puts_sorted) - 1):
            for j in range(i + 1, len(puts_sorted)):
                put_low = puts_sorted[i]
                put_high = puts_sorted[j]

                for k in range(len(calls_sorted) - 1):
                    for l in range(k + 1, len(calls_sorted)):
                        call_low = calls_sorted[k]
                        call_high = calls_sorted[l]

                        if put_high.strike_price < call_low.strike_price:
                            legs = self._build_legs_dynamically(
                                [put_low, put_high, call_low, call_high],
                                leg_defs
                            )
                            if legs:
                                local_metadata = {
                                    "volatility_signal": "منصفانه",
                                    "l1_ticker": legs[0].contract.ticker,
                                    "l2_ticker": legs[1].contract.ticker,
                                    "l3_ticker": legs[2].contract.ticker,
                                    "l4_ticker": legs[3].contract.ticker,
                                }
                                # فراخوانی والد جهت غنی‌سازی فیلدهای درصدی و تزریق S0_stock
                                opp = self._create_opportunity(
                                    legs=legs,
                                    underlying=underlying,
                                    days_to_maturity=days_to_maturity,
                                    contract_scores=contract_scores,
                                    base_metadata=local_metadata
                                )
                                if opp:
                                    opportunities.append(opp)

        return opportunities

    def _generate_long_box(
        self,
        calls: List[OptionContract],
        puts: List[OptionContract],
        underlying: UnderlyingAsset,
        days_to_maturity: int,
        contract_scores: Dict[str, float],
        leg_defs: list
    ) -> List[Opportunity]:
        """تولید Long Box با نگاشت بهینه استرایک‌ها"""
        opportunities = []

        if len(calls) < 2 or len(puts) < 2:
            return opportunities

        put_map: Dict[float, List[OptionContract]] = {}
        for p in puts:
            put_map.setdefault(round(p.strike_price, 1), []).append(p)

        calls_sorted = sorted(calls, key=lambda c: c.strike_price)

        for i in range(len(calls_sorted) - 1):
            for j in range(i + 1, len(calls_sorted)):
                c1 = calls_sorted[i]
                c2 = calls_sorted[j]

                put_at_k1 = put_map.get(round(c1.strike_price, 1), [])
                put_at_k2 = put_map.get(round(c2.strike_price, 1), [])

                for p1 in put_at_k1:
                    for p2 in put_at_k2:
                        legs = self._build_legs_dynamically(
                            [c1, p1, c2, p2],
                            leg_defs
                        )
                        if legs:
                            local_metadata = {
                                "volatility_signal": "منصفانه",
                                "l1_ticker": legs[0].contract.ticker,
                                "l2_ticker": legs[1].contract.ticker,
                                "l3_ticker": legs[2].contract.ticker,
                                "l4_ticker": legs[3].contract.ticker,
                            }
                            # فراخوانی والد جهت اعمال مدل کپسوله‌سازی صحیح هسته
                            opp = self._create_opportunity(
                                legs=legs,
                                underlying=underlying,
                                days_to_maturity=days_to_maturity,
                                contract_scores=contract_scores,
                                base_metadata=local_metadata
                            )
                            if opp:
                                opportunities.append(opp)

        return opportunities

    def _build_legs_dynamically(
        self,
        current_contracts: List[OptionContract],
        leg_defs: list
    ) -> Optional[List[LegDefinition]]:
        """ساخت داینامیک لگ‌ها بر اساس مطابقت نوع Enum بدون وابستگی به ترتیب"""
        matched_legs = []
        remaining_contracts = list(current_contracts)

        for leg_def in leg_defs:
            opt_type = leg_def.option_type if hasattr(leg_def, 'option_type') else leg_def[0]
            weight = leg_def.weight if hasattr(leg_def, 'weight') else leg_def[1]

            if isinstance(opt_type, str):
                opt_type = OptionType.PUT if opt_type.strip().lower() in ["put", "p"] else OptionType.CALL

            found_contract = None
            for c in remaining_contracts:
                if c.option_type == opt_type:
                    found_contract = c
                    break

            if found_contract:
                remaining_contracts.remove(found_contract)
                matched_legs.append(
                    LegDefinition(
                        contract=found_contract,
                        side=Side.BUY if weight > 0 else Side.SELL,
                        ratio=abs(int(weight))
                    )
                )
            else:
                return None

        return matched_legs