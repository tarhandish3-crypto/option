# strategies/generators/two_leg.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from itertools import combinations
from typing import List, Dict, Any, Set, Tuple, Iterator

from core.models import (
    OptionContract,
    UnderlyingAsset,
    Opportunity,
    LegDefinition,
)

from strategies.base import (
    StrategyDefinition,
    GeneratorType,
)

from strategies.generators.base import BaseGenerator
from strategies.matching.pattern_matcher import PatternMatcher
from strategies.matching.fast_filter import build_required_type_counts, can_match
from engine.opportunity_builder import OpportunityBuilder

logger = logging.getLogger("OptionScanner.Strategies.Generators.TwoLeg")


class TwoLegGenerator(BaseGenerator):
    """
    تولیدکننده جریانی استراتژی‌های دو لگی بر اساس ساختار اصلی پروژه
    """

    def __init__(self, strategy_def: StrategyDefinition):
        super().__init__(strategy_def)

        if strategy_def.generator_type != GeneratorType.TWO_LEG:
            raise ValueError(
                f"{strategy_def.name} is not compatible with TwoLegGenerator")

        if strategy_def.legs_count != 2:
            raise ValueError("TwoLegGenerator requires exactly 2 legs")

        self._required_types = build_required_type_counts(
            strategy_def.patterns)
        self._maturity_mode = (strategy_def.rules or {}).get(
            "maturity_order", "same")

    def generate(
        self,
        underlying: UnderlyingAsset,
        contracts: List[OptionContract],
        contract_scores: Dict[str, float],
    ) -> Iterator[Opportunity]:
        """
        تولید و yield فرصت‌ها به صورت جریانی برای جلوگیری از گلوگاه حافظه
        """
        if len(contracts) < 2:
            return

        patterns = self.strategy_def.patterns
        rules = self.strategy_def.rules or {}
        seen_keys: Set[Tuple] = set()
        maturity_mode = self._maturity_mode

        # =====================================================
        # تعیین دامنه سررسیدها
        # =====================================================
        if maturity_mode == "same":
            maturity_groups: Dict[int, List[OptionContract]] = {}
            for contract in contracts:
                maturity_groups.setdefault(
                    contract.days_to_maturity, []).append(contract)
            candidate_iterables = []
            for group in maturity_groups.values():
                if len(group) >= 2:
                    candidate_iterables.extend(combinations(group, 2))
        else:
            candidate_iterables = combinations(contracts, 2)

        # =====================================================
        # پردازش و ارسال جریانی کاندیداها
        # =====================================================
        for candidate in candidate_iterables:
            candidate_contracts = list(candidate)

            if not can_match(candidate_contracts, self._required_types, maturity_mode):
                continue

            matched_sets = PatternMatcher.match_all(
                contracts=candidate_contracts,
                patterns=patterns,
                strategy_rules=rules,
            )

            for matched_legs in matched_sets:
                if not self._validate_strike_gap(matched_legs, rules):
                    continue

                unique_key = self._build_unique_key(matched_legs)
                if unique_key in seen_keys:
                    continue

                seen_keys.add(unique_key)
                self.increment_generated()

                metadata = self._build_metadata(matched_legs, contract_scores)
                base_metadata = self._build_base_metadata(metadata)

                dte = max(
                    leg.contract.days_to_maturity
                    for leg in matched_legs
                    if leg.contract
                )

                opp = OpportunityBuilder.create_opportunity(
                    strategy_name=self.strategy_def.name,
                    ticker=underlying.ticker,
                    legs=matched_legs,
                    metrics=base_metadata,
                    days_to_maturity=dte,
                    underlying_price=underlying.close_price,
                )

                if opp is not None:
                    yield opp

    # ---------------------------------------------------------
    # VALIDATION
    # ---------------------------------------------------------

    def _validate_strike_gap(self, legs: List[LegDefinition], rules: Dict[str, Any]) -> bool:
        if len(legs) != 2:
            return False

        strike1 = legs[0].contract.strike_price
        strike2 = legs[1].contract.strike_price

        strike_equal = rules.get("strike_equal", False)
        tolerance_pct = rules.get("strike_equal_tolerance_pct", 0.005)

        if strike_equal:
            base = max(min(strike1, strike2), 1.0)
            diff_pct = abs(strike1 - strike2) / base
            if diff_pct > tolerance_pct:
                return False

        min_gap_pct = rules.get("min_strike_gap_pct", 0.0)
        max_gap_pct = rules.get("max_strike_gap_pct", 999.0)

        base = max(min(strike1, strike2), 1.0)
        gap_pct = abs(strike2 - strike1) / base

        return min_gap_pct <= gap_pct <= max_gap_pct

    # ---------------------------------------------------------
    # HELPERS
    # ---------------------------------------------------------

    @staticmethod
    def _build_unique_key(legs: List[LegDefinition]) -> Tuple:
        return tuple(
            sorted(
                (leg.contract.ticker, leg.side.value, leg.ratio)
                for leg in legs
                if leg.contract
            )
        )

    @staticmethod
    def _build_metadata(legs: List[LegDefinition], contract_scores: Dict[str, float]) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {}
        if len(legs) != 2 or not legs[0].contract or not legs[1].contract:
            return metadata

        c1, c2 = legs[0].contract, legs[1].contract

        metadata["l1_ticker"] = c1.ticker
        metadata["l2_ticker"] = c2.ticker
        metadata["l1_score"] = contract_scores.get(c1.ticker, 0.0)
        metadata["l2_score"] = contract_scores.get(c2.ticker, 0.0)
        metadata["l1_strike"] = c1.strike_price
        metadata["l2_strike"] = c2.strike_price

        base = min(c1.strike_price, c2.strike_price)
        metadata["strike_distance_pct"] = (
            abs(c1.strike_price - c2.strike_price) / base) if base > 0 else 0.0
        metadata["avg_contract_score"] = (
            metadata["l1_score"] + metadata["l2_score"]) / 2.0

        return metadata
