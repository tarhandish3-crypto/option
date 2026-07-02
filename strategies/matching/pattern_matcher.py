# strategies/matching/pattern_matcher.py
# -*- coding: utf-8 -*-

import logging
from itertools import permutations
from typing import List, Tuple, Optional, Dict, Any
import numpy as np

from core.models import OptionContract, StrategyLegPattern, LegDefinition
from core.enums import OptionType, Side

logger = logging.getLogger("OptionScanner.Strategies.Matching")


class PatternMatcher:
    """
    موتور تطبیق الگوهای استراتژی
    """

    @staticmethod
    def match_all(
        contracts: List[OptionContract],
        patterns: Tuple[StrategyLegPattern, ...],
        strategy_rules: Optional[Dict[str, Any]] = None) -> List[List[LegDefinition]]:
        """
        تطبیق قراردادها با الگوهای استراتژی
        """
        strategy_rules = strategy_rules or {}

        if len(contracts) != len(patterns):
            logger.error(
                f"تعداد قراردادها ({len(contracts)}) با تعداد الگوها ({len(patterns)}) مطابقت ندارد.")
            return []

        valid_matches: List[List[LegDefinition]] = []

        for contract_perm in permutations(contracts):
            is_valid = True
            matched_legs: List[LegDefinition] = []

            for contract, pattern in zip(contract_perm, patterns):
                # تطبیق نوع
                if contract.option_type != pattern.option_type:
                    is_valid = False
                    break

                # تعیین entry_price
                if contract.option_type == OptionType.STOCK:
                    ep = contract.last_price or contract.close_price or 0.0
                elif pattern.side == Side.BUY:
                    ep = contract.ask if contract.ask > 0 else contract.last_price
                else:
                    ep = contract.bid if contract.bid > 0 else contract.last_price

                matched_legs.append(LegDefinition(
                    side=pattern.side,
                    ratio=pattern.ratio,
                    contract=contract,
                    entry_price=ep,
                ))

            if is_valid:
                if PatternMatcher._validate_structural_relationships(
                    matched_legs, patterns, strategy_rules
                ):
                    valid_matches.append(matched_legs)

        return valid_matches

    @staticmethod
    def extract_batch_vectors(
        valid_matches: List[List[LegDefinition]],
        max_legs: int = 4) -> Dict[str, np.ndarray]:
        """
        استخراج برداری داده‌ها برای Numba
        """
        num_strategies = len(valid_matches)

        weights_matrix = np.zeros((num_strategies, max_legs), dtype=np.float64)
        strikes_matrix = np.zeros((num_strategies, max_legs), dtype=np.float64)
        entry_prices_matrix = np.zeros(
            (num_strategies, max_legs), dtype=np.float64)
        option_types_matrix = np.zeros(
            (num_strategies, max_legs), dtype=np.int32)
        sides_matrix = np.zeros((num_strategies, max_legs), dtype=np.int32)
        contract_sizes_matrix = np.zeros(
            (num_strategies, max_legs), dtype=np.int32)

        for i, legs in enumerate(valid_matches):
            for j, leg in enumerate(legs):
                if j >= max_legs:
                    break

                weights_matrix[i, j] = leg.weight
                sides_matrix[i, j] = 1 if leg.side == Side.BUY else -1

                contract = leg.contract
                if contract is not None:
                    strikes_matrix[i, j] = contract.strike_price
                    entry_prices_matrix[i, j] = leg.entry_price

                    ot = contract.option_type
                    option_types_matrix[i, j] = (
                        0 if ot == OptionType.STOCK else
                        1 if ot == OptionType.CALL else 2
                    )
                    contract_sizes_matrix[i, j] = contract.contract_size
                else:
                    strikes_matrix[i, j] = 0.0
                    entry_prices_matrix[i, j] = leg.entry_price
                    option_types_matrix[i, j] = 0
                    contract_sizes_matrix[i, j] = 1

        return {
            "weights": weights_matrix,
            "strikes": strikes_matrix,
            "entry_prices": entry_prices_matrix,
            "option_types": option_types_matrix,
            "sides": sides_matrix,
            "contract_sizes": contract_sizes_matrix}

    @staticmethod
    def _validate_structural_relationships(
        legs: List[LegDefinition],
        patterns: Tuple[StrategyLegPattern, ...],
        rules: Dict[str, Any]) -> bool:
        """
        اعتبارسنجی روابط ساختاری
        """
        strike_groups: Dict[str, float] = {}
        maturity_groups: Dict[str, int] = {}

        for leg, pattern in zip(legs, patterns):
            contract = leg.contract
            if not contract:
                return False

            # گروه‌بندی strike
            if pattern.strike_group:
                g = pattern.strike_group
                if g in strike_groups and abs(strike_groups[g] - contract.strike_price) > 1e-6:
                    return False
                strike_groups[g] = contract.strike_price

            # گروه‌بندی maturity
            if pattern.maturity_group:
                g = pattern.maturity_group
                if g in maturity_groups and maturity_groups[g] != contract.days_to_maturity:
                    return False
                maturity_groups[g] = contract.days_to_maturity

        # بررسی ترتیب strike
        strike_order = rules.get("strike_order", "ascending")
        if strike_order == "ascending":
            strike_values = list(strike_groups.values())
            if strike_values != sorted(strike_values):
                return False

        return True
