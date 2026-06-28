# strategies/generators/three_leg.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import List, Dict, Optional
from datetime import datetime
import logging

from core.models import OptionContract, UnderlyingAsset, Opportunity, LegDefinition
from core.enums import OptionType, Side
from strategies.base import StrategyDefinition, GeneratorType
from strategies.generators.base import BaseGenerator
from engine.opportunity_builder import OpportunityBuilder

logger = logging.getLogger("OptionScanner.Strategies.Generators.ThreeLeg")


class ThreeLegGenerator(BaseGenerator):
    """
    تولیدکننده استراتژی‌های ۳ لگی بورس ایران (نسخه بهینه و متصل به لایه غنی‌سازی پایه)
    """

    def __init__(self, strategy_def: StrategyDefinition):
        super().__init__(strategy_def)
        assert strategy_def.generator_type == GeneratorType.THREE_LEG
        assert strategy_def.legs_count == 3, "ThreeLegGenerator فقط برای استراتژی‌های ۳ لگی است"

    def generate(
        self,
        underlying: UnderlyingAsset,
        contracts: List[OptionContract],
        contract_scores: Dict[str, float]
    ) -> List[Opportunity]:
        """تولید فرصت‌های ۳ لگی بر اساس یکسان بودن سررسید و استرایک"""
        opportunities = []

        if len(contracts) < 3:
            return opportunities

        # ===== مرحله ۱: استخراج تعاریف الگو =====
        leg_def1, leg_def2, leg_def3 = self.strategy_def.weight_pattern

        # ===== مرحله ۲: گروه‌بندی بر اساس سررسید =====
        maturity_groups: Dict[int, List[OptionContract]] = {}
        for contract in contracts:
            maturity_groups.setdefault(contract.days_to_maturity, []).append(contract)

        # ===== مرحله ۳: پردازش هر گروه سررسید =====
        for days_to_maturity, group_contracts in maturity_groups.items():
            if len(group_contracts) < 2:
                continue

            # گروه‌بندی بر اساس استرایک قیمت
            strike_groups: Dict[float, List[OptionContract]] = {}
            for contract in group_contracts:
                strike_groups.setdefault(contract.strike_price, []).append(contract)

            # ===== مرحله ۴: پردازش هر گروه استرایک =====
            for strike, strike_contracts in strike_groups.items():
                calls = [c for c in strike_contracts if c.option_type == OptionType.CALL]
                puts = [c for c in strike_contracts if c.option_type == OptionType.PUT]

                if not calls or not puts:
                    continue

                call_contract = calls[0]
                put_contract = puts[0]

                strat_name = self.strategy_def.name.lower().strip()

                legs = None
                # ===== حالت الف: Strip (1 Call + 2 Put) =====
                if "strip" in strat_name:
                    legs = self._build_legs_dynamically(
                        [call_contract, put_contract, put_contract],
                        [leg_def1, leg_def2, leg_def3]
                    )

                # ===== حالت ب: Strap (2 Call + 1 Put) =====
                elif "strap" in strat_name:
                    legs = self._build_legs_dynamically(
                        [put_contract, call_contract, call_contract],
                        [leg_def1, leg_def2, leg_def3]
                    )

                # ارجاع فرآیند ساخت و غنی‌سازی متادیتا به متد کارخانه لایه پایه
                if legs:
                    local_metadata = {
                        "volatility_signal": "منصفانه",
                        "l1_ticker": legs[0].contract.ticker if legs[0].contract else "",
                        "l2_ticker": legs[1].contract.ticker if legs[1].contract else "",
                        "l3_ticker": legs[2].contract.ticker if legs[2].contract else "",
                    }
                    
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