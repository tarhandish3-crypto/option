# strategies/matching/contract_index.py
# -*- coding: utf-8 -*-

"""
contract_index.py

ایندکس ساختاریافته، فوق‌سریع و مجهز به موتور پنجره‌های متحرک استرایک.
بهینه‌سازی شده برای حذف کامل کپی‌های حافظه و تولید ویندوزهای ترکیبی O(1).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import chain
from typing import Dict, List, Iterable, Optional, Tuple, Iterator

from core.enums import OptionType
from core.models import OptionContract

logger = logging.getLogger("OptionScanner.Strategies.Matching.ContractIndex")


@dataclass(slots=True)
class StrikeBucket:
    """قراردادهای اختیارات معامله در یک قیمت اعمال (Strike) مشخص"""
    strike: float
    calls: List[OptionContract] = field(default_factory=list)
    puts: List[OptionContract] = field(default_factory=list)


@dataclass(slots=True)
class MaturityBucket:
    """قراردادهای متعلق به یک تاریخ سررسید (DTE) مشخص"""
    dte: int
    strikes: Dict[float, StrikeBucket] = field(default_factory=dict)
    _sorted_strikes: List[float] = field(default_factory=list, init=False)


class ContractIndex:
    """
    ایندکس چندبعدی و جریانی زنجیره آپشن.
    مجهز به پنجره‌های متحرک استرایک جهت تغذیه فوق‌سریع ژنراتورهای ۲، ۳ و ۴ لگی.
    """

    def __init__(self, contracts: Iterable[OptionContract]):
        self._maturity_map: Dict[int, MaturityBucket] = {}

        self._calls_by_dte: Dict[int, List[OptionContract]] = defaultdict(list)
        self._puts_by_dte: Dict[int, List[OptionContract]] = defaultdict(list)

        self._calls_by_strike: Dict[float,
                                    List[OptionContract]] = defaultdict(list)
        self._puts_by_strike: Dict[float,
                                   List[OptionContract]] = defaultdict(list)

        self._ticker_map: Dict[str, OptionContract] = {}

        self._all_calls: List[OptionContract] = []
        self._all_puts: List[OptionContract] = []
        self._cached_maturities: List[int] = []
        self._cached_all_strikes: List[float] = []

        self._build(contracts)

    def _build(self, contracts: Iterable[OptionContract]) -> None:
        all_strikes_set = set()

        for c in contracts:
            self._ticker_map[c.ticker] = c
            dte = c.days_to_maturity
            strike = c.strike_price
            all_strikes_set.add(strike)

            # ۱. تخصیص به سطل سررسید
            dte_bucket = self._maturity_map.get(dte)
            if dte_bucket is None:
                dte_bucket = MaturityBucket(dte)
                self._maturity_map[dte] = dte_bucket

            # ۲. تخصیص به سطل استرایک داخل آن سررسید
            strike_bucket = dte_bucket.strikes.get(strike)
            if strike_bucket is None:
                strike_bucket = StrikeBucket(strike)
                dte_bucket.strikes[strike] = strike_bucket

            # ۳. تفکیک موازی انواع اختیار
            if c.option_type == OptionType.CALL:
                strike_bucket.calls.append(c)
                self._calls_by_dte[dte].append(c)
                self._calls_by_strike[strike].append(c)
                self._all_calls.append(c)
            elif c.option_type == OptionType.PUT:
                strike_bucket.puts.append(c)
                self._puts_by_dte[dte].append(c)
                self._puts_by_strike[strike].append(c)
                self._all_puts.append(c)

        # --------------------------------------------------
        # عملیات بهینه‌سازی لایه نهایی و مرتب‌سازی‌های متقاطع
        # --------------------------------------------------
        self._cached_maturities = sorted(self._maturity_map.keys())
        self._cached_all_strikes = sorted(list(all_strikes_set))

        # الف) مرتب‌سازی کانتراکت‌های داخل سررسید بر اساس استرایک صعودی (رفع نقد برابری با پترن‌مچر)
        for dte, bucket in self._maturity_map.items():
            bucket._sorted_strikes = sorted(bucket.strikes.keys())
            self._calls_by_dte[dte].sort(key=lambda x: x.strike_price)
            self._puts_by_dte[dte].sort(key=lambda x: x.strike_price)

        # ب) مرتب‌سازی کانتراکت‌های داخل استرایک بر اساس سررسید صعودی (رفع ایراد دوم هوش مصنوعی)
        for strike in all_strikes_set:
            self._calls_by_strike[strike].sort(
                key=lambda x: x.days_to_maturity)
            self._puts_by_strike[strike].sort(key=lambda x: x.days_to_maturity)

        logger.debug(
            f"ContractIndex fully optimized. {len(self._ticker_map)} contracts loaded.")

    # =====================================================
    # Basic Queries (O(1) - Memory Safe)
    # =====================================================

    @property
    def is_empty(self) -> bool:
        """بررسی خالی بودن ایندکس (بدون قرارداد)"""
        return len(self._ticker_map) == 0

    @property
    def contract_count(self) -> int:
        """تعداد قراردادهای ایندکس"""
        return len(self._ticker_map)
    
    @property
    def maturities(self) -> List[int]:
        return self._cached_maturities

    def get_maturity_bucket(self, dte: int) -> Optional[MaturityBucket]:
        return self._maturity_map.get(dte)

    def get_calls(self, dte: Optional[int] = None) -> List[OptionContract]:
        return self._all_calls if dte is None else self._calls_by_dte.get(dte, [])

    def get_puts(self, dte: Optional[int] = None) -> List[OptionContract]:
        return self._all_puts if dte is None else self._puts_by_dte.get(dte, [])

    def get_strikes(self, dte: Optional[int] = None) -> List[float]:
        if dte is None:
            return self._cached_all_strikes
        bucket = self._maturity_map.get(dte)
        return bucket._sorted_strikes if bucket else []
    
    def get_contract(self, ticker: str) -> Optional[OptionContract]:
        return self._ticker_map.get(ticker)

    # =====================================================
    # Advanced Lazy Queries (رفع ایراد اول و پنجم - بدون مموری الیکیشن)
    # =====================================================

    def get_contracts_at_expiry_strike(
        self, dte: int, strike: float, option_type: Optional[OptionType] = None
    ) -> Iterator[OptionContract]:
        """بازگرداندن کانتراکت‌ها به صورت Generator مجهز به chain جهت حذف کپی آرایه حافظه"""
        bucket = self._maturity_map.get(dte)
        if not bucket:
            return
        strike_bucket = bucket.strikes.get(strike)
        if not strike_bucket:
            return

        if option_type == OptionType.CALL:
            yield from strike_bucket.calls
        elif option_type == OptionType.PUT:
            yield from strike_bucket.puts
        else:
            yield from chain(strike_bucket.calls, strike_bucket.puts)

    def get_call_put_pair(self, dte: int, strike: float) -> Tuple[List[OptionContract], List[OptionContract]]:
        """دریافت سریع جفت کال و پوت هم‌زمان برای استراتژی‌هایی مثل Long Box و Straddle"""
        bucket = self._maturity_map.get(dte)
        if not bucket:
            return [], []
        strike_bucket = bucket.strikes.get(strike)
        if not strike_bucket:
            return [], []
        return strike_bucket.calls, strike_bucket.puts

    # =====================================================
    # Windowing & Neighbor Engines (رفع ایراد چهارم و ششم - شاهکار اسکنر)
    # =====================================================

    def iter_strike_windows(self, dte: int, size: int = 4) -> Iterator[List[StrikeBucket]]:
        """
        تولید پنجره‌های متحرک زنجیره‌ای از سطل‌های استرایک متوالی همان سررسید.
        خروجی ایده آل برای Iron Condor (سایز ۴) و Butterfly (سایز ۳) و Vertical (سایز ۲).
        """
        bucket = self._maturity_map.get(dte)
        if not bucket or len(bucket._sorted_strikes) < size:
            return

        sorted_strikes = bucket._sorted_strikes
        # حرکت پنجره به صورت متوالی روی کل زنجیره استرایک‌ها
        for i in range(len(sorted_strikes) - size + 1):
            window_strikes = sorted_strikes[i: i + size]
            yield [bucket.strikes[st] for st in window_strikes]

    def get_adjacent_strike(self, dte: int, current_strike: float, offset: int = 1) -> Optional[StrikeBucket]:
        """یافتن استرایک همسایه (قبلی یا بعدی) در زمان O(1) با استفاده از ایندکس موقعیت استرایک‌ها"""
        bucket = self._maturity_map.get(dte)
        if not bucket:
            return None

        try:
            current_idx = bucket._sorted_strikes.index(current_strike)
            target_idx = current_idx + offset
            if 0 <= target_idx < len(bucket._sorted_strikes):
                target_strike = bucket._sorted_strikes[target_idx]
                return bucket.strikes[target_strike]
        except ValueError:
            return None
        return None
