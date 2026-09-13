# strategies/matching/pattern_matcher.py
# -*- coding: utf-8 -*-

"""
PatternMatcher — تنها منبع تطبیق الگو با کانتراکت‌های بازار.
"""

import logging
from itertools import product, chain
from typing import Iterator, Tuple, Optional, Dict, Any, Iterable, List
import numpy as np

from core.models import (
    OptionContract,
    UnderlyingAsset,
    StrategyLegPattern,
    LegDefinition,)
from core.enums import OptionType, Side
from strategies.matching.contract_index import ContractIndex, StrikeBucket

logger = logging.getLogger("OptionScanner.Strategies.Matching")


class PatternMatcher:
    """
    موتور تطبیق الگو — خروجی: لیست OptionContract خام (یک به ازای هر pattern).

    ساخت LegDefinition فقط در OpportunityBuilder انجام می‌شود.
    """

    __slots__ = ()

    # =========================================================================
    # PUBLIC ENTRYPOINT
    # =========================================================================

    @staticmethod
    def match_all(
        index: ContractIndex,
        patterns: Tuple[StrategyLegPattern, ...],
        underlying: Optional[UnderlyingAsset] = None,
        strategy_rules: Optional[Dict[str, Any]] = None,
        min_liquidity_score: float = 30.0,
        contract_scores: Optional[Dict[str, float]] = None,
        underlying_price: Optional[float] = None,
        dedup: bool = False,) -> Iterator[List[OptionContract]]:
        """
        تطبیق جریانی patterns با کانتراکت‌های بازار
        """
        strategy_rules = strategy_rules or {}
        contract_scores = contract_scores or {}

        # ── نرمال‌سازی underlying_price ──────────────────────────────────
        if underlying_price is None or underlying_price <= 0:
            if underlying is not None:
                underlying_price = (
                    getattr(underlying, "last_price", 0) or
                    getattr(underlying, "close_price", 0) or
                    getattr(underlying, "yesterday_price", 0) or
                    0.0
                )
            else:
                underlying_price = 0.0

        # ── جداسازی patterns آپشن از سهام ────────────────────────────────
        option_patterns = [
            p for p in patterns if p.option_type != OptionType.STOCK
        ]
        stock_patterns = [
            p for p in patterns if p.option_type == OptionType.STOCK
        ]
        option_count = len(option_patterns)

        if option_count == 0 and not stock_patterns:
            return

        # ── ساخت OptionContract مجازی برای لگ‌های سهام ──────────────────
        stock_contract: Optional[OptionContract] = None
        if stock_patterns:
            if underlying is None or underlying_price <= 0:
                logger.debug(
                    "Strategy has stock leg but no valid underlying price; skipping"
                )
                return

            stock_contract = OptionContract(
                ticker=underlying.ticker,
                name=underlying.name,
                underlying_ticker=underlying.ticker,
                option_type=OptionType.STOCK,
                strike_price=underlying_price,
                contract_size=1,
                last_price=underlying_price,
                close_price=getattr(underlying, "close_price", underlying_price),
                underlying_price=underlying_price,
            )

        # ── اگر فقط لگ سهام داریم ────────────────────────────────────────
        if option_count == 0:
            if stock_contract:
                yield [stock_contract] * len(stock_patterns)
            return

        # ── استخراج ترتیب ایندکس‌ها ─────────────────────────────────────
        stock_indices = [
            i for i, p in enumerate(patterns) if p.option_type == OptionType.STOCK
        ]
        option_indices = [
            i for i, p in enumerate(patterns) if p.option_type != OptionType.STOCK
        ]

        # ── شاخه‌بندی اصلی ─────────────────────────────────────────────
        maturity_mode = strategy_rules.get("maturity_order", "same")

        if maturity_mode == "same":
            yield from PatternMatcher._match_same_maturity(
                index=index,
                option_patterns=option_patterns,
                option_count=option_count,
                stock_contract=stock_contract,
                stock_indices=stock_indices,
                option_indices=option_indices,
                total_patterns=len(patterns),
                strategy_rules=strategy_rules,
                min_liquidity_score=min_liquidity_score,
                contract_scores=contract_scores,
                underlying_price=underlying_price,
            )
        else:
            # calendar/diagonal
            yield from PatternMatcher._match_different_maturity(
                index=index,
                option_patterns=option_patterns,
                option_count=option_count,
                stock_contract=stock_contract,
                stock_indices=stock_indices,
                option_indices=option_indices,
                total_patterns=len(patterns),
                strategy_rules=strategy_rules,
                min_liquidity_score=min_liquidity_score,
                contract_scores=contract_scores,
                underlying_price=underlying_price,
            )

    # =========================================================================
    # SAME-MATURITY BRANCH
    # =========================================================================

    @staticmethod
    def _match_same_maturity(
        index: ContractIndex,
        option_patterns: List[StrategyLegPattern],
        option_count: int,
        stock_contract: Optional[OptionContract],
        stock_indices: List[int],
        option_indices: List[int],
        total_patterns: int,
        strategy_rules: Dict[str, Any],
        min_liquidity_score: float,
        contract_scores: Dict[str, float],
        underlying_price: float,
    ) -> Iterator[List[OptionContract]]:
        """تطبیق استراتژی‌هایی که همه لگ‌ها در یک سررسید قرار دارند."""
        strike_equal = strategy_rules.get("strike_equal", False)

        for dte in index.maturities:
            maturity_bucket = index.get_maturity_bucket(dte)
            if maturity_bucket is None:
                continue

            # ── حالت ۱: تک لگی ────────────────────────────────────────
            if option_count == 1:
                for strike in maturity_bucket._sorted_strikes:
                    bucket = maturity_bucket.strikes.get(strike)
                    if bucket is None:
                        continue

                    for combo in PatternMatcher._process_window(
                        [bucket], option_patterns,
                        strategy_rules, min_liquidity_score,
                        contract_scores, underlying_price,
                    ):
                        yield PatternMatcher._merge_stock_option(
                            combo, stock_contract, stock_indices,
                            option_indices, total_patterns,
                        )
                continue  # به DTE بعدی

            # ── حالت ۲: strike_equal (straddle, conversion, strap, strip) ──
            if strike_equal:
                for strike in maturity_bucket._sorted_strikes:
                    bucket = maturity_bucket.strikes.get(strike)
                    if bucket is None:
                        continue

                    single_window = [bucket] * option_count
                    for combo in PatternMatcher._process_window(
                        single_window, option_patterns,
                        strategy_rules, min_liquidity_score,
                        contract_scores, underlying_price,
                    ):
                        yield PatternMatcher._merge_stock_option(
                            combo, stock_contract, stock_indices,
                            option_indices, total_patterns,
                        )

            # ── حالت ۳: دو لگی cross-strike (spreads, strangle, guts) ──
            elif option_count == 2:
                for combo in PatternMatcher._match_cross_strike(
                    maturity_bucket, option_patterns,
                    strategy_rules, min_liquidity_score,
                    contract_scores, underlying_price,
                ):
                    yield PatternMatcher._merge_stock_option(
                        combo, stock_contract, stock_indices,
                        option_indices, total_patterns,
                    )

            # ── حالت ۴: چند لگی sliding-window (iron_condor, long_box) ──
            else:
                for window in PatternMatcher._iter_windows(
                    maturity_bucket, option_count
                ):
                    for combo in PatternMatcher._process_window(
                        window, option_patterns,
                        strategy_rules, min_liquidity_score,
                        contract_scores, underlying_price,
                    ):
                        yield PatternMatcher._merge_stock_option(
                            combo, stock_contract, stock_indices,
                            option_indices, total_patterns,
                        )

    # =========================================================================
    # DIFFERENT-MATURITY BRANCH (Calendar / Diagonal)
    # =========================================================================

    @staticmethod
    def _match_different_maturity(
        index: ContractIndex,
        option_patterns: List[StrategyLegPattern],
        option_count: int,
        stock_contract: Optional[OptionContract],
        stock_indices: List[int],
        option_indices: List[int],
        total_patterns: int,
        strategy_rules: Dict[str, Any],
        min_liquidity_score: float,
        contract_scores: Dict[str, float],
        underlying_price: float,
    ) -> Iterator[List[OptionContract]]:
        """تطبیق استراتژی‌هایی که لگ‌ها در سررسیدهای متفاوت قرار دارند."""
        for combo in PatternMatcher._match_calendar_spreads(
            index, option_patterns, strategy_rules,
            min_liquidity_score, contract_scores, underlying_price,
        ):
            yield PatternMatcher._merge_stock_option(
                combo, stock_contract, stock_indices,
                option_indices, total_patterns,
            )

    # =========================================================================
    # MERGE STOCK + OPTION
    # =========================================================================

    @staticmethod
    def _merge_stock_option(
        option_contracts: List[OptionContract],
        stock_contract: Optional[OptionContract],
        stock_indices: List[int],
        option_indices: List[int],
        total: int,
    ) -> List[OptionContract]:
        """
        بازسازی لیست نهایی به ترتیب اصلی patterns.

        stock_indices نشان می‌دهد کدام موقعیت‌ها سهام هستند.
        option_indices نشان می‌دهد کدام موقعیت‌ها آپشن هستند.
        """
        result: List[Optional[OptionContract]] = [None] * total

        for idx, contract in zip(option_indices, option_contracts):
            result[idx] = contract

        for idx in stock_indices:
            result[idx] = stock_contract

        # فیلتر None در صورت وجود
        return [c for c in result if c is not None]

    # =========================================================================
    # WINDOW ITERATORS
    # =========================================================================

    @staticmethod
    def _iter_windows(
        maturity_bucket: Any,
        size: int,
    ) -> Iterator[List[StrikeBucket]]:
        """پنجره‌های متحرک از strike‌های متوالی."""
        sorted_strikes = maturity_bucket._sorted_strikes
        n = len(sorted_strikes)

        if n < size:
            return

        for i in range(n - size + 1):
            yield [
                maturity_bucket.strikes[sorted_strikes[i + k]]
                for k in range(size)
            ]

    # =========================================================================
    # CROSS-STRIKE (۲ لگی)
    # =========================================================================

    @staticmethod
    def _match_cross_strike(
        maturity_bucket: Any,
        option_patterns: List[StrategyLegPattern],
        rules: Dict[str, Any],
        min_liquidity_score: float,
        scores: Optional[Dict[str, float]],
        underlying_price: Optional[float] = None,
    ) -> Iterator[List[OptionContract]]:
        """ترکیب cartesian روی همه جفت strikeها برای استراتژی‌های ۲ لگی."""
        sorted_strikes = maturity_bucket._sorted_strikes
        n = len(sorted_strikes)
        if n < 1:
            return

        for i in range(n):
            for j in range(i, n):
                bucket_i = maturity_bucket.strikes.get(sorted_strikes[i])
                bucket_j = maturity_bucket.strikes.get(sorted_strikes[j])
                if not bucket_i or not bucket_j:
                    continue

                window = [bucket_i, bucket_j]
                yield from PatternMatcher._process_window(
                    window, option_patterns, rules,
                    min_liquidity_score, scores, underlying_price,
                )

    # =========================================================================
    # WINDOW PROCESSING
    # =========================================================================

    @staticmethod
    def _process_window(
        window: List[StrikeBucket],
        option_patterns: List[StrategyLegPattern],
        rules: Dict[str, Any],
        min_liquidity_score: float,
        scores: Optional[Dict[str, float]],
        underlying_price: Optional[float] = None,
    ) -> Iterator[List[OptionContract]]:
        """
        ضرب دکارتی تنبل روی کانتراکت‌های نقدشونده در پنجره.

        خروجی: لیست OptionContract (فقط آپشن، بدون سهام).
        """
        scores = scores or {}

        def _is_liquid(c: OptionContract) -> bool:
            return scores.get(c.ticker, 100.0) >= min_liquidity_score

        def _candidates():
            for i, pattern in enumerate(option_patterns):
                # اگر window کوتاه‌تر از patterns است، آخرین bucket را تکرار کن
                bucket_idx = i if i < len(window) else len(window) - 1
                bucket = window[bucket_idx]

                if pattern.option_type == OptionType.CALL:
                    valid = [c for c in bucket.calls if _is_liquid(c)]
                elif pattern.option_type == OptionType.PUT:
                    valid = [c for c in bucket.puts if _is_liquid(c)]
                else:
                    valid = [c for c in chain(bucket.calls, bucket.puts) if _is_liquid(c)]

                if not valid:
                    return
                yield valid

        candidate_lists = list(_candidates())
        if len(candidate_lists) < len(option_patterns):
            return

        for combo in product(*candidate_lists):
            if not PatternMatcher._validate_combo(
                combo, option_patterns, rules, underlying_price
            ):
                continue
            yield list(combo)

    # =========================================================================
    # COMBO VALIDATION
    # =========================================================================

    @staticmethod
    def _validate_combo(
        combo: Tuple[OptionContract, ...],
        option_patterns: List[StrategyLegPattern],
        rules: Dict[str, Any],
        underlying_price: Optional[float] = None,
    ) -> bool:
        """اعتبارسنجی ترتیب و فواصل درصدی استرایک‌ها."""
        strike_order = rules.get("strike_order", "ascending")
        min_gap_pct = rules.get("min_strike_gap_pct", 0.0)
        max_gap_pct = rules.get("max_strike_gap_pct", 999.0)
        strike_equal = rules.get("strike_equal", False)
        tolerance_pct = rules.get("strike_equal_tolerance_pct", 0.005)

        # ── بررسی ترتیب strikes ──────────────────────────────────
        last_strike: Optional[float] = None
        for contract in combo:
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

        # ── بررسی برابری strikes (Calendar) ──────────────────────
        if strike_equal and len(combo) > 1:
            strikes = [c.strike_price for c in combo]
            base = max(min(strikes), 1.0)
            if (max(strikes) - min(strikes)) / base > tolerance_pct:
                return False

        # ── بررسی فواصل بین strikes ──────────────────────────────
        if len(combo) > 1:
            strikes = [c.strike_price for c in combo]
            for i in range(len(strikes) - 1):
                base = max(min(strikes[i], strikes[i + 1]), 1.0)
                gap = abs(strikes[i] - strikes[i + 1]) / base
                if min_gap_pct > 0 and gap < min_gap_pct:
                    return False
                if max_gap_pct < 999.0 and gap > max_gap_pct:
                    return False

        # ── بررسی فاصله داخلی (Iron Condor) ──────────────────────
        min_inner_gap_pct = rules.get("min_inner_gap_pct", 0.0)
        if min_inner_gap_pct > 0 and len(combo) >= 4:
            strikes_sorted = sorted(c.strike_price for c in combo)
            # مبنای درصد: underlying_price اگر معتبر باشد، وگرنه پایین‌ترین strike
            if underlying_price and underlying_price > 0:
                base = underlying_price
            else:
                base = max(strikes_sorted[0], 1.0)
            inner_gap = strikes_sorted[2] - strikes_sorted[1]
            if inner_gap < min_inner_gap_pct * base:
                return False

        # ── بررسی strike_above_spot (Covered Call) ───────────────
        strike_above_spot = rules.get("strike_above_spot", False)
        if strike_above_spot and underlying_price and underlying_price > 0:
            for c in combo:
                if c.strike_price < underlying_price:
                    return False

        return True

    # =========================================================================
    # CALENDAR / DIAGONAL SPREADS
    # =========================================================================

    @staticmethod
    def _match_calendar_spreads(
        index: ContractIndex,
        option_patterns: List[StrategyLegPattern],
        rules: Dict[str, Any],
        min_liquidity_score: float,
        scores: Optional[Dict[str, float]],
        underlying_price: Optional[float] = None,
    ) -> Iterator[List[OptionContract]]:
        """تطبیق Calendar و Diagonal Spreads (سررسیدهای متفاوت)."""
        scores = scores or {}

        # ── اعتبارسنجی ورودی ────────────────────────────────────
        if len(option_patterns) < 2:
            logger.debug("Calendar spreads require at least 2 option legs")
            return

        if len(option_patterns) > 2:
            logger.warning(
                f"Calendar spreads with {len(option_patterns)} legs "
                f"are not supported yet (only 2 legs supported)"
            )
            return

        if index.is_empty:
            return

        # ── استخراج قواعد با مقداردهی ایمن ───────────────────────
        strike_equal = rules.get("strike_equal", True)

        min_dte_gap = rules.get("min_dte_gap_days")
        if min_dte_gap is None:
            min_dte_gap = 7

        max_dte_gap = rules.get("max_dte_gap_days")
        if max_dte_gap is None:
            max_dte_gap = 365

        far_first = rules.get("far_maturity_first", False)

        # ── استخراج DTEهای مرتب‌شده ──────────────────────────────
        sorted_dtes = sorted(index.maturities)
        if len(sorted_dtes) < 2:
            logger.debug("Calendar spreads require at least 2 maturities")
            return

        # ── حلقه روی ترکیب DTEها ─────────────────────────────────
        for i, dte_near in enumerate(sorted_dtes):
            for j in range(i + 1, len(sorted_dtes)):
                dte_far = sorted_dtes[j]

                dte_gap = dte_far - dte_near
                if dte_gap < min_dte_gap:
                    continue
                if dte_gap > max_dte_gap:
                    continue

                near_bucket = index.get_maturity_bucket(dte_near)
                far_bucket = index.get_maturity_bucket(dte_far)
                if not near_bucket or not far_bucket:
                    continue

                # ── تعیین ترتیب بر اساس rules ────────────────────
                if far_first:
                    first_bucket, second_bucket = far_bucket, near_bucket
                else:
                    first_bucket, second_bucket = near_bucket, far_bucket

                # ── حالت ۱: Calendar (strike_equal=True) ─────────
                if strike_equal:
                    yield from PatternMatcher._match_calendar_equal_strike(
                        first_bucket, second_bucket,
                        option_patterns, rules,
                        min_liquidity_score, scores,
                        underlying_price,
                    )
                # ── حالت ۲: Diagonal (strike_equal=False) ────────
                else:
                    yield from PatternMatcher._match_diagonal_cross_strike(
                        first_bucket, second_bucket,
                        option_patterns, rules,
                        min_liquidity_score, scores,
                        underlying_price,
                    )

    @staticmethod
    def _match_calendar_equal_strike(
        first_bucket: Any,
        second_bucket: Any,
        option_patterns: List[StrategyLegPattern],
        rules: Dict[str, Any],
        min_liquidity_score: float,
        scores: Dict[str, float],
        underlying_price: Optional[float] = None,
    ) -> Iterator[List[OptionContract]]:
        """
        تطبیق Calendar Spread با strike یکسان.
        """
        first_strikes = set(first_bucket._sorted_strikes)
        second_strikes = set(second_bucket._sorted_strikes)
        common_strikes = sorted(first_strikes & second_strikes)

        if not common_strikes:
            return

        # ── آماده‌سازی قواعد مخصوص Calendar ─────────────────────
        # در Calendar، فاصله strikes همیشه صفر است، پس
        # min_strike_gap_pct و max_strike_gap_pct بی‌معنی هستند.
        calendar_rules = dict(rules)
        calendar_rules["strike_equal"] = True
        calendar_rules["min_strike_gap_pct"] = 0.0
        calendar_rules["max_strike_gap_pct"] = 999.0
        calendar_rules["strike_order"] = "any"

        for strike in common_strikes:
            first_strike_bucket = first_bucket.strikes.get(strike)
            second_strike_bucket = second_bucket.strikes.get(strike)

            if not first_strike_bucket or not second_strike_bucket:
                continue

            window = [first_strike_bucket, second_strike_bucket]

            yield from PatternMatcher._process_window(
                window, option_patterns, calendar_rules,
                min_liquidity_score, scores, underlying_price,
            )

    @staticmethod
    def _match_diagonal_cross_strike(
        first_bucket: Any,
        second_bucket: Any,
        option_patterns: List[StrategyLegPattern],
        rules: Dict[str, Any],
        min_liquidity_score: float,
        scores: Dict[str, float],
        underlying_price: Optional[float] = None,) -> Iterator[List[OptionContract]]:
        """
        تطبیق Diagonal Spread با strike متفاوت.
        """
        first_strikes = first_bucket._sorted_strikes
        second_strikes = second_bucket._sorted_strikes

        if not first_strikes or not second_strikes:
            return

        strike_order = rules.get("strike_order", "ascending")

        for strike_a in first_strikes:
            for strike_b in second_strikes:
                # در Diagonal، strike‌ها متفاوت هستند اما ترتیب مهم است
                if strike_order == "ascending" and strike_a > strike_b:
                    continue
                if strike_order == "descending" and strike_a < strike_b:
                    continue

                first_strike_bucket = first_bucket.strikes.get(strike_a)
                second_strike_bucket = second_bucket.strikes.get(strike_b)

                if not first_strike_bucket or not second_strike_bucket:
                    continue

                window = [first_strike_bucket, second_strike_bucket]

                yield from PatternMatcher._process_window(
                    window, option_patterns, rules,
                    min_liquidity_score, scores, underlying_price,
                )

    # =========================================================================
    # BATCH VECTORS (For Numba)
    # =========================================================================

    @staticmethod
    def extract_batch_vectors(
        valid_matches: Iterable[List[LegDefinition]],
        max_legs: int = 4,) -> Dict[str, np.ndarray]:
        """
        تبدیل جریان LegDefinition‌ها به ماتریس‌های NumPy برای Numba.

        """
        weights_list, strikes_list, entry_prices_list = [], [], []
        option_types_list, sides_list, contract_sizes_list = [], [], []

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

                # وزن با علامت از سمت لگ
                w[j] = float(leg.ratio)
                sd[j] = 1 if leg.side == Side.BUY else -1

                contract = leg.contract
                if contract is not None:
                    s[j] = contract.strike_price
                    ep[j] = leg.entry_price
                    o_type = contract.option_type
                    ot[j] = (
                        0 if o_type == OptionType.STOCK
                        else (1 if o_type == OptionType.CALL else 2)
                    )
                    cs[j] = contract.contract_size
                else:
                    ot[j] = 0
                    cs[j] = 1

            weights_list.append(w)
            strikes_list.append(s)
            entry_prices_list.append(ep)
            option_types_list.append(ot)
            sides_list.append(sd)
            contract_sizes_list.append(cs)

        # ── حالت خالی ─────────────────────────────────────────────
        if not weights_list:
            def empty(dt):
                return np.empty((0, max_legs), dtype=dt)

            return {
                "weights": empty(np.float64),
                "strikes": empty(np.float64),
                "entry_prices": empty(np.float64),
                "option_types": empty(np.int32),
                "sides": empty(np.int32),
                "contract_sizes": empty(np.int32),
            }

        # ── حالت عادی ─────────────────────────────────────────────
        return {
            "weights": np.vstack(weights_list),
            "strikes": np.vstack(strikes_list),
            "entry_prices": np.vstack(entry_prices_list),
            "option_types": np.vstack(option_types_list),
            "sides": np.vstack(sides_list),
            "contract_sizes": np.vstack(contract_sizes_list),
        }