# position_saver/importer/suggest.py
# -*- coding: utf-8 -*-

"""
پیشنهاد نام استراتژی بر اساس ترکیب معاملات.

فقط پیشنهاد — هیچ تصمیم قطعی نمی‌گیرد.
"""

from typing import List

from position_saver.models import LegType, OptionLeg
from position_saver.pnl_calculator import PositionPnLCalculator


def suggest_strategy_name(trades: List) -> str:
    """
    پیشنهاد نام استراتژی از لیست TradeRecord یا OptionLeg.

    Returns:
        نام استراتژی یا "" اگر تشخیص ممکن نبود.
    """
    if not trades:
        return ""

    legs = []
    for t in trades:
        leg = _to_leg(t)
        if leg is not None:
            legs.append(leg)

    if not legs:
        return ""

    try:
        return PositionPnLCalculator.suggest_strategy_name(legs) or ""
    except Exception:
        return ""


def _to_leg(item) -> OptionLeg | None:
    """
    تبدیل هر شیء (TradeRecord یا OptionLeg) به OptionLeg.

    اگر item خودش OptionLeg بود، مستقیم برگردانده می‌شود.
    """
    if item is None:
        return None

    # اگر از قبل OptionLeg است
    if isinstance(item, OptionLeg):
        return item

    # TradeRecord → OptionLeg
    try:
        return OptionLeg(
            symbol=getattr(item, "symbol", ""),
            is_option=getattr(item, "is_option", True),
            option_kind=getattr(item, "option_kind", None),
            leg_type=getattr(item, "side", LegType.BUY),
            strike_price=float(getattr(item, "strike_price", 0) or 0),
            contract_size=int(
                getattr(item, "effective_contract_size", 1000) or 1000),
            quantity=int(getattr(item, "quantity", 0) or 0),
            entry_price=float(getattr(item, "price", 0) or 0),
            expiry_date=getattr(item, "expiry_date", "") or "",
            ins_code=getattr(item, "ins_code", "") or "",
            ins_code_ua=getattr(item, "ins_code_ua", "") or "",
        )
    except Exception:
        return None


__all__ = ["suggest_strategy_name"]