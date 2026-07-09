# strategies/matching/pattern_matcher.py
# -*- coding: utf-8 -*-

import logging
from itertools import product, chain
from typing import Iterator, Tuple, Optional, Dict, Any, Iterable, List
import numpy as np

from core.models import OptionContract, StrategyLegPattern, LegDefinition
from core.enums import OptionType, Side
from strategies.matching.contract_index import ContractIndex, StrikeBucket

logger = logging.getLogger("OptionScanner.Strategies.Matching")


class PatternMatcher:
    """
    موتور هوشمند و بدون الیکیشن حافظه (Zero-Allocation) برای تطبیق الگوها.

    سه حالت اجرا در match_all:
    1. strike_equal=True        → single-bucket   : همه لگ‌ها از یک strike (straddle, conversion)
    2. legs_count > 2           → sliding-window  : strikeهای متوالی (iron condor, long_box)
    3. legs_count == 2,
       strike_equal=False       → cross-strike     : همه جفت strikeها (strangle, spread, guts)
    """

    __slots__ = ()

    @staticmethod
    def match_all(
        index: ContractIndex,
        patterns: Tuple[StrategyLegPattern, ...],
        strategy_rules: Optional[Dict[str, Any]] = None,
        min_liquidity_score: float = 30.0,
        contract_scores: Optional[Dict[str, float]] = None,
        underlying_price: Optional[float] = None,
        dedup: bool = False,
    ) -> Iterator[List[LegDefinition]]:
        """تطبیق کاملاً جریانی زنجیره آپشن با الگوها."""
        strategy_rules = strategy_rules or {}
        legs_count = len(patterns)

        if legs_count == 0:
            return

        maturity_mode = strategy_rules.get("maturity_order", "same")
        strike_equal = strategy_rules.get("strike_equal", False)

        if maturity_mode == "same":
            for dte in index.maturities:
                maturity_bucket = index.get_maturity_bucket(dte)
                if maturity_bucket is None:
                    continue

                if strike_equal:
                    # ── حالت ۱: Single-bucket ──────────────────────────────
                    # همه لگ‌ها از یک strike: straddle، strip، strap، conversion
                    for strike in maturity_bucket._sorted_strikes:
                        bucket = maturity_bucket.strikes.get(strike)
                        if bucket is None:
                            continue
                        single_window = [bucket] * legs_count
                        yield from PatternMatcher._process_window_combinations(
                            window=single_window,
                            patterns=patterns,
                            rules=strategy_rules,
                            min_liquidity_score=min_liquidity_score,
                            scores=contract_scores
                        )

                elif legs_count == 2:
                    # ── حالت ۳: Cross-strike cartesian ─────────────────────
                    # دو لگ از هر ترکیب دو strike ممکن: strangle، spread، guts
                    yield from PatternMatcher._match_cross_strike(
                        maturity_bucket=maturity_bucket,
                        patterns=patterns,
                        rules=strategy_rules,
                        min_liquidity_score=min_liquidity_score,
                        scores=contract_scores
                    )

                else:
                    # ── حالت ۲: Sliding-window ─────────────────────────────
                    # چند لگ از strikeهای متوالی: iron condor، long box
                    for strike_window in index.iter_strike_windows(dte, size=legs_count):
                        yield from PatternMatcher._process_window_combinations(
                            window=strike_window,
                            patterns=patterns,
                            rules=strategy_rules,
                            min_liquidity_score=min_liquidity_score,
                            scores=contract_scores
                        )
        else:
            yield from PatternMatcher._match_calendar_spreads(
                index, patterns, strategy_rules, contract_scores, min_liquidity_score
            )

    @staticmethod
    def _match_cross_strike(
        maturity_bucket: Any,
        patterns: Tuple[StrategyLegPattern, ...],
        rules: Dict[str, Any],
        min_liquidity_score: float,
        scores: Optional[Dict[str, float]]
    ) -> Iterator[List[LegDefinition]]:
        """
        ترکیب همه جفت strikeهای (i, j) با i <= j در یک سررسید.
        برای استراتژی‌های ۲ لگی که لگ‌هایشان از strikeهای دور از هم می‌آیند.
        """
        scores = scores or {}
        sorted_strikes = maturity_bucket._sorted_strikes
        n = len(sorted_strikes)

        if n < 1:
            return

        for i in range(n):
            for j in range(i, n):
                strike_i = sorted_strikes[i]
                strike_j = sorted_strikes[j]
                bucket_i = maturity_bucket.strikes.get(strike_i)
                bucket_j = maturity_bucket.strikes.get(strike_j)
                if not bucket_i or not bucket_j:
                    continue

                window = [bucket_i, bucket_j]
                yield from PatternMatcher._process_window_combinations(
                    window=window,
                    patterns=patterns,
                    rules=rules,
                    min_liquidity_score=min_liquidity_score,
                    scores=scores
                )

    @staticmethod
    def _process_window_combinations(
        window: List[StrikeBucket],
        patterns: Tuple[StrategyLegPattern, ...],
        rules: Dict[str, Any],
        min_liquidity_score: float,
        scores: Optional[Dict[str, float]]
    ) -> Iterator[List[LegDefinition]]:
        """
        پردازش ضرب دکارتی تنبل کانتراکت‌ها صرفاً در فضای فیلترشده و محدود پنجره استرایک.
        """
        scores = scores or {}

        def _get_candidates_iter():
            for i, pattern in enumerate(patterns):
                bucket = window[i]

                if pattern.option_type == OptionType.CALL:
                    valid = [c for c in bucket.calls if scores.get(c.ticker, 100.0) >= min_liquidity_score]
                    if not valid:
                        return
                    yield valid

                elif pattern.option_type == OptionType.PUT:
                    valid = [c for c in bucket.puts if scores.get(c.ticker, 100.0) >= min_liquidity_score]
                    if not valid:
                        return
                    yield valid

                else:
                    # STOCK یا ANY — هر دو نوع
                    valid = [c for c in chain(bucket.calls, bucket.puts)
                             if scores.get(c.ticker, 100.0) >= min_liquidity_score]
                    if not valid:
                        return
                    yield valid

        candidate_iters = list(_get_candidates_iter())
        if len(candidate_iters) < len(patterns):
            return

        for combo in product(*candidate_iters):

            if not PatternMatcher._fast_validate_structural_relationships(combo, patterns, rules):
                continue

            matched_legs: List[LegDefinition] = []
            for contract, pattern in zip(combo, patterns):
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

            yield matched_legs

    @staticmethod
    def _fast_validate_structural_relationships(
        combo: Tuple[OptionContract, ...],
        patterns: Tuple[StrategyLegPattern, ...],
        rules: Dict[str, Any]
    ) -> bool:
        """اعتبارسنجی ترتیب و فواصل درصدی استرایک‌ها."""
        last_strike: Optional[float] = None
        strike_order = rules.get("strike_order", "ascending")
        min_gap_pct = rules.get("min_strike_gap_pct", 0.0)
        max_gap_pct = rules.get("max_strike_gap_pct", 999.0)
        strike_equal = rules.get("strike_equal", False)
        tolerance_pct = rules.get("strike_equal_tolerance_pct", 0.005)

        for contract, pattern in zip(combo, patterns):
            if not contract:
                return False

            if strike_order == "ascending":
                if last_strike is not None and contract.strike_price < last_strike:
                    return False
                last_strike = contract.strike_price
            elif strike_order == "descending":
                if last_strike is not None and contract.strike_price > last_strike:
                    return False
                last_strike = contract.strike_price

        # بررسی strike_equal — همه strikeها باید در tolerance باشند
        if strike_equal and len(combo) > 1:
            strikes = [c.strike_price for c in combo]
            base = max(min(strikes), 1.0)
            gap = (max(strikes) - min(strikes)) / base
            if gap > tolerance_pct:
                return False

        # بررسی min/max gap فقط برای strikeهای متفاوت
        if len(combo) > 1:
            strikes = [c.strike_price for c in combo]
            for i in range(len(strikes) - 1):
                base = max(min(strikes[i], strikes[i + 1]), 1.0)
                gap_pct = abs(strikes[i] - strikes[i + 1]) / base
                if min_gap_pct > 0 and gap_pct < min_gap_pct:
                    return False
                if max_gap_pct < 999.0 and gap_pct > max_gap_pct:
                    return False

        return True

    @staticmethod
    def _match_calendar_spreads(
        index: ContractIndex,
        patterns: Tuple[StrategyLegPattern, ...],
        rules: Dict[str, Any],
        scores: Optional[Dict[str, float]],
        min_liquidity: float
    ) -> Iterator[List[LegDefinition]]:
        """توسعه آتی: calendar و diagonal spreads."""
        return
        yield

    @staticmethod
    def extract_batch_vectors(
        valid_matches: Iterable[List[LegDefinition]],
        max_legs: int = 4
    ) -> Dict[str, np.ndarray]:
        """تبدیل جریان پوزیشن‌ها به ماتریس‌های NumPy برای پردازشگر Numba."""
        weights_list = []
        strikes_list = []
        entry_prices_list = []
        option_types_list = []
        sides_list = []
        contract_sizes_list = []

        for legs in valid_matches:
            w = np.zeros(max_legs, dtype=np.float64)
            s = np.zeros(max_legs, dtype=np.float64)
            ep = np.zeros(max_legs, dtype=np.float64)
            ot = np.zeros(max_legs, dtype=np.int32)
            sd = np.zeros(max_legs, dtype=np.int32)
            cs = np.zeros(max_legs, dtype=np.int32)

            for j, leg in enumerate(legs):
                if j >= max_legs:
                    break

                w[j] = leg.weight
                sd[j] = 1 if leg.side == Side.BUY else -1

                contract = leg.contract
                if contract is not None:
                    s[j] = contract.strike_price
                    ep[j] = leg.entry_price
                    o_type = contract.option_type
                    ot[j] = (
                        0 if o_type == OptionType.STOCK else
                        1 if o_type == OptionType.CALL else 2
                    )
                    cs[j] = contract.contract_size
                else:
                    s[j] = 0.0
                    ep[j] = leg.entry_price
                    ot[j] = 0
                    cs[j] = 1

            weights_list.append(w)
            strikes_list.append(s)
            entry_prices_list.append(ep)
            option_types_list.append(ot)
            sides_list.append(sd)
            contract_sizes_list.append(cs)

        if not weights_list:
            return {
                "weights": np.empty((0, max_legs), dtype=np.float64),
                "strikes": np.empty((0, max_legs), dtype=np.float64),
                "entry_prices": np.empty((0, max_legs), dtype=np.float64),
                "option_types": np.empty((0, max_legs), dtype=np.int32),
                "sides": np.empty((0, max_legs), dtype=np.int32),
                "contract_sizes": np.empty((0, max_legs), dtype=np.int32),
            }

        return {
            "weights": np.vstack(weights_list),
            "strikes": np.vstack(strikes_list),
            "entry_prices": np.vstack(entry_prices_list),
            "option_types": np.vstack(option_types_list),
            "sides": np.vstack(sides_list),
            "contract_sizes": np.vstack(contract_sizes_list),
        }
