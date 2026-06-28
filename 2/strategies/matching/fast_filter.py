# strategies/matching/fast_filter.py
# -*- coding: utf-8 -*-
"""
فیلتر سریع پیش از PatternMatcher برای حذف ترکیبات ناسازگار
بدون ساخت LegDefinition — فقط بررسی ویژگی‌های خام قرارداد.
این فیلتر ۸۰٪+ ترکیب‌های ناسازگار را بدون ساخت LegDefinition رد می‌کند.
"""
from typing import List, Tuple, Dict
from core.models import OptionContract, StrategyLegPattern
from core.enums import OptionType

_CALL = OptionType.CALL
_PUT = OptionType.PUT


def build_pattern_signature(patterns: Tuple[StrategyLegPattern, ...]) -> Tuple[int, int]:
    """
    خلاصه ساختاری: (تعداد Call مورد نیاز، تعداد Put مورد نیاز)
    یک tuple ساده — سریع‌تر از Dict
    """
    calls = sum(1 for p in patterns if p.option_type == _CALL)
    puts = sum(1 for p in patterns if p.option_type == _PUT)
    return (calls, puts)


def passes_type_filter(
    contracts: List[OptionContract],
    sig: Tuple[int, int]
) -> bool:
    """
    آیا این مجموعه قراردادها با امضای استراتژی سازگار است؟
    بدون Counter، بدون Dict — فقط شمارش مستقیم: O(n) بسیار سریع.
    """
    need_calls, need_puts = sig
    calls = 0
    puts = 0
    for c in contracts:
        t = c.option_type
        if t is _CALL:
            calls += 1
            if calls > need_calls:
                return False
        elif t is _PUT:
            puts += 1
            if puts > need_puts:
                return False
    return calls == need_calls and puts == need_puts
