# position_saver/importer/suggest.py
# -*- coding: utf-8 -*-

"""
پیشنهاد نام استراتژی بر اساس ترکیب معاملات.
"""

from typing import List

from position_saver.models import LegType
from position_saver.pnl_calculator import PositionPnLCalculator


def suggest_strategy_name(trades: List) -> str:
    """
    پیشنهاد نام استراتژی — فقط پیشنهاد.

    Args:
        trades: لیست TradeRecord یا OptionLeg

    Returns:
        نام استراتژی یا "" اگر نتوانست
    """
    if not trades:
        return ""

    # تبدیل TradeRecord به OptionLeg سازگار
    legs = []
    for t in trades:
        leg = _trade_to_leg(t)
        if leg is not None:
            legs.append(leg)

    if not legs:
        return ""

    return PositionPnLCalculator.suggest_strategy_name(legs)


def _trade_to_leg(trade):
    """تبدیل TradeRecord به OptionLeg سبک برای پیشنهاد"""
    try:
        from position_saver.models import OptionLeg
        return OptionLeg(
            symbol=trade.symbol,
            is_option=trade.is_option,
            option_kind=trade.option_kind,
            leg_type=trade.side,
            strike_price=trade.strike_price or 0.0,
            contract_size=trade.effective_contract_size,
            quantity=trade.quantity,
            entry_price=trade.price,
        )
    except Exception:
        return None


__all__ = ["suggest_strategy_name"]