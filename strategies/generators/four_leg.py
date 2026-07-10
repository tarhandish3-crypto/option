# strategies/generators/four_leg.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import logging
from typing import Dict, Set, Tuple, Iterator, List, Any

from core.models import UnderlyingAsset, Opportunity, LegDefinition, OptionContract
from core.enums import OptionType
from strategies.base import StrategyDefinition
from strategies.generators.base import BaseGenerator
from strategies.matching.contract_index import ContractIndex
from strategies.matching.pattern_matcher import PatternMatcher
from engine.opportunity_builder import OpportunityBuilder

logger = logging.getLogger("OptionScanner.Strategies.Generators.FourLeg")


class FourLegGenerator(BaseGenerator):
    """تولیدکننده استراتژی‌های ۴ لگی (Iron Condor، Long Box)."""

    __slots__ = ('_maturity_mode',)

    def __init__(self, strategy_def: StrategyDefinition):
        super().__init__(strategy_def)
        if strategy_def.legs_count != 4:
            raise ValueError("FourLegGenerator نیازمند ۴ لگ است.")
        self._maturity_mode = (strategy_def.rules or {}).get("maturity_order", "same")

    def generate(
        self,
        underlying: UnderlyingAsset,
        index: ContractIndex,
        contract_scores: Dict[str, float],
    ) -> Iterator[Opportunity]:
        spot = self._get_S0_stock(underlying)
        if spot <= 0 or index.is_empty:
            return

        rules = self.strategy_def.rules or {}
        patterns = self.strategy_def.patterns
        min_liq_score = rules.get("min_liquidity_score", 30.0)
        seen_keys: Set[Tuple] = set()

        matched_sets = PatternMatcher.match_all(
            index=index,
            patterns=patterns,
            underlying=underlying,
            strategy_rules=rules,
            min_liquidity_score=min_liq_score,
            contract_scores=contract_scores,
            underlying_price=spot,
        )

        for matched_contracts in matched_sets:
            # اعتبارسنجی فواصل استرایک برای ۴ لگی
            if not self._validate_strike_gaps(matched_contracts, rules):
                continue

            # dedup با کلید یکتا
            key = tuple(sorted(
                (c.ticker, c.option_type.value, c.strike_price)
                for c in matched_contracts
                if c is not None and c.option_type != OptionType.STOCK
            ))
            if key in seen_keys:
                continue
            seen_keys.add(key)

            self.increment_generated()

            opp = OpportunityBuilder.build_opportunity(
                strategy_def=self.strategy_def,
                underlying=underlying,
                matched_contracts=matched_contracts,
                contract_scores=contract_scores,
                underlying_price=spot,
            )
            if opp is not None:
                yield opp

    def _validate_strike_gaps(
        self, contracts: List[OptionContract], rules: Dict[str, Any]
    ) -> bool:
        """اعتبارسنجی فواصل و تقارن بال‌ها برای Iron Condor / Long Box."""
        strikes = [
            c.strike_price for c in contracts
            if c is not None and c.option_type != OptionType.STOCK
        ]
        if len(strikes) != 4:
            return False

        s = sorted(strikes)
        base = max(s[0], 1.0)

        if rules.get("enforce_symmetry", False):
            left = s[1] - s[0]
            right = s[3] - s[2]
            tol = rules.get("symmetry_tolerance_pct", 0.005) * base
            if abs(left - right) > tol:
                return False

        min_gap = rules.get("min_strike_gap_pct", 0.0) * base
        if min_gap > 0:
            for i in range(len(s) - 1):
                if s[i + 1] - s[i] < min_gap:
                    return False

        return True
