# strategies/matching/fast_filter.py
# -*- coding: utf-8 -*-

"""
فیلتر سریع پیش از PatternMatcher

مشکل: برای iron_condor با ۵۷ قرارداد در یک سررسید:
  C(57,4) = 395,010 ترکیب
  هر ترکیب → permutations(4) = 24 بار → 9,480,240 بررسی
  اکثریت قریب به اتفاق رد می‌شوند چون ۲ Call + ۲ Put ندارند

راه‌حل: قبل از هر چیز بررسی کن آیا این ترکیب اصلاً
ساختار type لازم را دارد یا نه — بدون هیچ allocation.
"""

from __future__ import annotations

from collections import Counter
from typing import List, Tuple

from core.models import OptionContract, StrategyLegPattern
from core.enums import OptionType


def build_required_type_counts(
    patterns: Tuple[StrategyLegPattern, ...]
) -> Counter:
    """
    از روی patterns استراتژی، تعداد مورد نیاز هر نوع قرارداد را استخراج می‌کند.

    مثال iron_condor: {CALL: 2, PUT: 2}
    مثال bull_call_spread: {CALL: 2}
    مثال long_straddle: {CALL: 1, PUT: 1}

    این تابع یک‌بار هنگام init ژنراتور صدا زده می‌شود و نتیجه کش می‌شود.
    """
    counts: Counter = Counter()
    for p in patterns:
        if p.option_type != OptionType.STOCK:
            counts[p.option_type] += p.ratio
    return counts


def fast_type_check(
    contracts: List[OptionContract],
    required: Counter
) -> bool:
    """
    بررسی می‌کند آیا لیست قراردادها حداقل تعداد لازم از هر نوع را دارد.

    پیچیدگی: O(n) روی تعداد قراردادهای ترکیب (معمولاً ۲، ۳، یا ۴)
    هیچ allocation انجام نمی‌دهد — فقط شمارش.

    Returns:
        True اگر ترکیب می‌تواند الگو را پوشش دهد، False اگر غیرممکن است.
    """
    if not required:
        return True

    available: Counter = Counter()
    for c in contracts:
        if c.option_type in required:
            available[c.option_type] += 1
            # early exit: اگر همه شروط برآورده شد زودتر خارج شو
            if all(available[t] >= required[t] for t in required):
                return True

    return all(available[t] >= required[t] for t in required)


def fast_maturity_check(
    contracts: List[OptionContract],
    maturity_mode: str
) -> bool:
    """
    بررسی سریع سازگاری سررسید قراردادها با maturity_mode استراتژی.

    - "same": همه قراردادها باید یک سررسید داشته باشند
    - "calendar" / "diagonal": باید حداقل ۲ سررسید متفاوت وجود داشته باشد
    - غیره: بدون محدودیت (True)
    """
    if maturity_mode == "same":
        # اگر همه یک DTE دارند → True
        first_dte = contracts[0].days_to_maturity
        return all(c.days_to_maturity == first_dte for c in contracts)

    elif maturity_mode in ("calendar", "diagonal"):
        # حداقل دو سررسید متفاوت لازم است
        first_dte = contracts[0].days_to_maturity
        return any(c.days_to_maturity != first_dte for c in contracts)

    return True


def can_match(
    contracts: List[OptionContract],
    required_types: Counter,
    maturity_mode: str
) -> bool:
    """
    ترکیب هر دو چک در یک فراخوانی واحد.
    اول type check (ارزان‌تر) بعد maturity check.
    """
    return (
        fast_type_check(contracts, required_types)
        and fast_maturity_check(contracts, maturity_mode)
    )
