# strategies/generators/single_leg.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import logging
from typing import Dict, Iterator, Set, Tuple

from core.models import UnderlyingAsset, Opportunity
from core.enums import GeneratorType
from strategies.base import StrategyDefinition
from strategies.generators.base import BaseGenerator
from strategies.matching.contract_index import ContractIndex
from strategies.matching.pattern_matcher import PatternMatcher
from engine.opportunity_builder import OpportunityBuilder

logger = logging.getLogger("OptionScanner.Strategies.Generators.SingleLeg")


class SingleLegGenerator(BaseGenerator):
    """ژنراتور عمومی استراتژی‌های تک‌لگی (Long/Short Call & Put)."""

    __slots__ = ()

    def __init__(self, strategy_def: StrategyDefinition):
        super().__init__(strategy_def)
        if strategy_def.generator_type != GeneratorType.SINGLE_LEG:
            raise ValueError(
                f"{strategy_def.name} با SingleLegGenerator سازگار نیست.")

    def generate(
        self,
        underlying: UnderlyingAsset,
        index: ContractIndex,
        contract_scores: Dict[str, float],) -> Iterator[Opportunity]:
        
        spot = self._get_S0_stock(underlying)
        if spot <= 0 or index.is_empty:
            return

        rules = self.strategy_def.rules or {}
        patterns = self.strategy_def.patterns

        # انطباق کامل با امضای متد پترن‌مچر
        matched_sets = PatternMatcher.match_all(
            index=index,
            patterns=patterns,
            underlying=underlying,
            strategy_rules=rules,
            contract_scores=contract_scores,
            underlying_price=spot,)

        seen: Set[Tuple] = set()

        for matched_contracts in matched_sets:
            # کنترل اینکه حتماً یک لگ خروجی گرفته شده باشد
            if len(matched_contracts) != 1:
                continue

            # استفاده از ساختار کانترکت درون کلاس برای کلید یکتا
            leg = matched_contracts[0]
            c = getattr(leg, 'contract', leg) # بسته به اینکه خروجی لگ‌مدل است یا خود کانترکت
            
            if c is None:
                continue
                
            key = (c.ticker, c.option_type.value, c.strike_price, leg.side.value if hasattr(leg, 'side') else 'BUY')

            if key in seen:
                continue
            seen.add(key)

            # انطباق کامل با امضای متد اپورچونیتی‌بیلدر
            opp = OpportunityBuilder.build_opportunity(
                strategy_def=self.strategy_def,
                underlying=underlying,
                matched_contracts=matched_contracts, # نام متغیر همگام با کل پروژه
                contract_scores=contract_scores,
                underlying_price=spot,)

            if opp is not None:
                self.increment_generated()
                yield opp