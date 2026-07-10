# strategies/matching/pattern_matcher.py
# -*- coding: utf-8 -*-

"""
PatternMatcher — تنها منبع تطبیق الگو با کانتراکت‌های بازار.

جریان داده:
  StrategyDefinition.patterns (StrategyLegPattern[]) 
      → PatternMatcher.match_all()
      → Iterator[List[OptionContract]]   ← خروجی خام، بدون Side/EntryPrice
      
OpportunityBuilder سپس با zip کردن contracts و patterns، LegDefinition‌ها را می‌سازد.

سه حالت اجرا:
1. strike_equal=True        → single-bucket   : همه لگ‌ها از یک strike (straddle, conversion)
2. legs_count > 2 (پیوسته) → sliding-window  : strikeهای متوالی (iron condor, long_box)
3. legs_count == 2,
   strike_equal=False       → cross-strike     : همه جفت strikeها (strangle, spread, guts)
"""

import logging
from itertools import product, chain
from typing import Iterator, Tuple, Optional, Dict, Any, Iterable, List
import numpy as np

from core.models import OptionContract, UnderlyingAsset, StrategyLegPattern, LegDefinition
from core.enums import OptionType, Side
from strategies.matching.contract_index import ContractIndex, StrikeBucket

logger = logging.getLogger("OptionScanner.Strategies.Matching")


class PatternMatcher:
    """
    موتور تطبیق الگو — خروجی: لیست OptionContract خام (یک به ازای هر pattern).
    ساخت LegDefinition فقط در OpportunityBuilder انجام می‌شود.
    """

    __slots__ = ()

    @staticmethod
    def match_all(
        index: ContractIndex,
        patterns: Tuple[StrategyLegPattern, ...],
        underlying: Optional[UnderlyingAsset] = None,
        strategy_rules: Optional[Dict[str, Any]] = None,
        min_liquidity_score: float = 30.0,
        contract_scores: Optional[Dict[str, float]] = None,
        underlying_price: Optional[float] = None,
        dedup: bool = False,
    ) -> Iterator[List[OptionContract]]:
        """
        تطبیق جریانی patterns با کانتراکت‌های بازار.
        خروجی: لیست OptionContract خام — یک عنصر به ازای هر pattern.
        برای pattern‌های STOCK یک OptionContract مجازی از underlying ساخته می‌شود.
        """
        strategy_rules = strategy_rules or {}

        # جداسازی patterns آپشن از stock
        option_patterns = [p for p in patterns if p.option_type != OptionType.STOCK]
        stock_patterns = [p for p in patterns if p.option_type == OptionType.STOCK]
        option_count = len(option_patterns)

        if option_count == 0 and not stock_patterns:
            return

        # ساخت OptionContract مجازی برای لگ‌های سهام
        stock_contract: Optional[OptionContract] = None
        if stock_patterns and underlying is not None:
            spot = underlying_price or underlying.last_price or underlying.close_price or 0.0
            if spot > 0:
                stock_contract = OptionContract(
                    ticker=underlying.ticker,
                    name=underlying.name,
                    underlying_ticker=underlying.ticker,
                    option_type=OptionType.STOCK,
                    strike_price=spot,
                    contract_size=1,
                    last_price=spot,
                    close_price=underlying.close_price,
                    underlying_price=spot,
                )

        # اگر فقط لگ stock داریم (غیرمعمول)
        if option_count == 0:
            if stock_contract:
                yield [stock_contract] * len(stock_patterns)
            return

        maturity_mode = strategy_rules.get("maturity_order", "same")
        strike_equal = strategy_rules.get("strike_equal", False)

        # ترتیب ایندکس‌های pattern: stock patterns ابتدا می‌آیند (مطابق با patterns tuple)
        stock_indices = [i for i, p in enumerate(patterns) if p.option_type == OptionType.STOCK]
        option_indices = [i for i, p in enumerate(patterns) if p.option_type != OptionType.STOCK]

        if maturity_mode == "same":
            for dte in index.maturities:
                maturity_bucket = index.get_maturity_bucket(dte)
                if maturity_bucket is None:
                    continue

                if strike_equal:
                    # ── Single-bucket: همه لگ‌های آپشن از یک strike ──
                    for strike in maturity_bucket._sorted_strikes:
                        bucket = maturity_bucket.strikes.get(strike)
                        if bucket is None:
                            continue
                        single_window = [bucket] * option_count
                        for combo in PatternMatcher._process_window(
                            single_window, option_patterns,
                            strategy_rules, min_liquidity_score, contract_scores
                        ):
                            yield PatternMatcher._merge_stock_option(
                                combo, stock_contract, stock_indices, option_indices, len(patterns)
                            )

                elif option_count == 2:
                    # ── Cross-strike: همه جفت strikeهای ممکن ──
                    for combo in PatternMatcher._match_cross_strike(
                        maturity_bucket, option_patterns,
                        strategy_rules, min_liquidity_score, contract_scores
                    ):
                        yield PatternMatcher._merge_stock_option(
                            combo, stock_contract, stock_indices, option_indices, len(patterns)
                        )

                else:
                    # ── Sliding-window: strikeهای متوالی ──
                    for window in PatternMatcher._iter_windows(maturity_bucket, option_count):
                        for combo in PatternMatcher._process_window(
                            window, option_patterns,
                            strategy_rules, min_liquidity_score, contract_scores
                        ):
                            yield PatternMatcher._merge_stock_option(
                                combo, stock_contract, stock_indices, option_indices, len(patterns)
                            )
        else:
            # calendar/diagonal — آینده
            return

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
        stock_indices مشخص می‌کند کدام موقعیت‌ها stock هستند.
        """
        result: List[Optional[OptionContract]] = [None] * total
        for idx, contract in zip(option_indices, option_contracts):
            result[idx] = contract
        for idx in stock_indices:
            result[idx] = stock_contract
        # فیلتر None در صورت وجود (نباید اتفاق بیفتد)
        return [c for c in result if c is not None]

    @staticmethod
    def _iter_windows(
        maturity_bucket: Any,
        size: int,
    ) -> Iterator[List[StrikeBucket]]:
        """پنجره‌های متحرک از strikeهای متوالی."""
        sorted_strikes = maturity_bucket._sorted_strikes
        n = len(sorted_strikes)
        if n < size:
            return
        for i in range(n - size + 1):
            yield [maturity_bucket.strikes[sorted_strikes[i + k]] for k in range(size)]

    @staticmethod
    def _match_cross_strike(
        maturity_bucket: Any,
        option_patterns: List[StrategyLegPattern],
        rules: Dict[str, Any],
        min_liquidity_score: float,
        scores: Optional[Dict[str, float]],
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
                    window, option_patterns, rules, min_liquidity_score, scores
                )

    @staticmethod
    def _process_window(
        window: List[StrikeBucket],
        option_patterns: List[StrategyLegPattern],
        rules: Dict[str, Any],
        min_liquidity_score: float,
        scores: Optional[Dict[str, float]],
    ) -> Iterator[List[OptionContract]]:
        """
        ضرب دکارتی تنبل روی کانتراکت‌های نقدشونده در پنجره.
        خروجی: لیست OptionContract (فقط آپشن، بدون stock).
        """
        scores = scores or {}

        def _candidates():
            for i, pattern in enumerate(option_patterns):
                bucket = window[i]
                if pattern.option_type == OptionType.CALL:
                    valid = [c for c in bucket.calls
                             if scores.get(c.ticker, 100.0) >= min_liquidity_score]
                elif pattern.option_type == OptionType.PUT:
                    valid = [c for c in bucket.puts
                             if scores.get(c.ticker, 100.0) >= min_liquidity_score]
                else:
                    valid = [c for c in chain(bucket.calls, bucket.puts)
                             if scores.get(c.ticker, 100.0) >= min_liquidity_score]
                if not valid:
                    return
                yield valid

        candidate_lists = list(_candidates())
        if len(candidate_lists) < len(option_patterns):
            return

        for combo in product(*candidate_lists):
            if not PatternMatcher._validate_combo(combo, option_patterns, rules):
                continue
            yield list(combo)

    @staticmethod
    def _validate_combo(
        combo: Tuple[OptionContract, ...],
        option_patterns: List[StrategyLegPattern],
        rules: Dict[str, Any],
    ) -> bool:
        """اعتبارسنجی ترتیب و فواصل درصدی استرایک‌ها."""
        strike_order = rules.get("strike_order", "ascending")
        min_gap_pct = rules.get("min_strike_gap_pct", 0.0)
        max_gap_pct = rules.get("max_strike_gap_pct", 999.0)
        strike_equal = rules.get("strike_equal", False)
        tolerance_pct = rules.get("strike_equal_tolerance_pct", 0.005)

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

        if strike_equal and len(combo) > 1:
            strikes = [c.strike_price for c in combo]
            base = max(min(strikes), 1.0)
            if (max(strikes) - min(strikes)) / base > tolerance_pct:
                return False

        if len(combo) > 1:
            strikes = [c.strike_price for c in combo]
            for i in range(len(strikes) - 1):
                base = max(min(strikes[i], strikes[i + 1]), 1.0)
                gap = abs(strikes[i] - strikes[i + 1]) / base
                if min_gap_pct > 0 and gap < min_gap_pct:
                    return False
                if max_gap_pct < 999.0 and gap > max_gap_pct:
                    return False

        return True

    @staticmethod
    def _match_calendar_spreads(
        index: ContractIndex,
        patterns: Tuple[StrategyLegPattern, ...],
        rules: Dict[str, Any],
        scores: Optional[Dict[str, float]],
        min_liquidity: float,) -> Iterator[List[OptionContract]]:
        """توسعه آتی: calendar و diagonal spreads."""
        return
        yield

    @staticmethod
    def extract_batch_vectors(
        valid_matches: Iterable[List[LegDefinition]],
        max_legs: int = 4) -> Dict[str, np.ndarray]:
        """تبدیل جریان LegDefinition‌ها به ماتریس‌های NumPy برای Numba."""
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
                w[j] = leg.weight
                w[j] = float(leg.ratio)
                sd[j] = 1 if leg.side == Side.BUY else -1
                contract = leg.contract
                if contract is not None:
                    s[j] = contract.strike_price
                    ep[j] = leg.entry_price
                    o_type = contract.option_type
                    ot[j] = 0 if o_type == OptionType.STOCK else (1 if o_type == OptionType.CALL else 2)
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

        if not weights_list:
            empty = lambda dt: np.empty((0, max_legs), dtype=dt)
            return {k: empty(np.float64) for k in ("weights", "strikes", "entry_prices")} | \
                   {k: empty(np.int32) for k in ("option_types", "sides", "contract_sizes")}

        return {
            "weights": np.vstack(weights_list),
            "strikes": np.vstack(strikes_list),
            "entry_prices": np.vstack(entry_prices_list),
            "option_types": np.vstack(option_types_list),
            "sides": np.vstack(sides_list),
            "contract_sizes": np.vstack(contract_sizes_list),
        }
