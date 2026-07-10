# strategies/generators/three_leg.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import logging
from typing import Dict, Set, Tuple, Iterator

from core.models import UnderlyingAsset, Opportunity, OptionContract
from core.enums import GeneratorType, OptionType
from strategies.base import StrategyDefinition
from strategies.generators.base import BaseGenerator
from strategies.matching.contract_index import ContractIndex
from strategies.matching.pattern_matcher import PatternMatcher
from engine.opportunity_builder import OpportunityBuilder

logger = logging.getLogger("OptionScanner.Strategies.Generators.ThreeLeg")


class ThreeLegGenerator(BaseGenerator):
    """تولیدکننده استراتژی‌های ۳ لگی (مثل Collar، Conversion)."""

    __slots__ = ('_maturity_mode',)

    def __init__(self, strategy_def: StrategyDefinition):
        super().__init__(strategy_def)
        if strategy_def.generator_type != GeneratorType.THREE_LEG:
            raise ValueError(f"{strategy_def.name} با ThreeLegGenerator سازگار نیست.")
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
        seen_keys: Set[Tuple] = set()

        matched_sets = PatternMatcher.match_all(
            index=index,
            patterns=patterns,
            underlying=underlying,
            strategy_rules=rules,
            contract_scores=contract_scores,
            underlying_price=spot,
        )

        for matched_contracts in matched_sets:
            # dedup بر اساس تیکر و نوع همه کانتراکت‌ها
            key = tuple(
                (c.ticker, c.option_type.value, c.strike_price)
                for c in matched_contracts if c is not None and c.option_type != OptionType.STOCK
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)

            opp = OpportunityBuilder.build_opportunity(
                strategy_def=self.strategy_def,
                underlying=underlying,
                matched_contracts=matched_contracts,
                contract_scores=contract_scores,
                underlying_price=spot,
            )
            if opp is not None:
                self.increment_generated()
                yield opp
