# position_saver/importer/net_position.py
# -*- coding: utf-8 -*-

"""
محاسبه‌ی موقعیت خالص از ترتیب معاملات یک نماد.

کاربرد:
    نمایش ترتیب زمانی معاملات + جفت‌یابی BUY-SELL + وضعیت نهایی

هیچ تصمیم خودکاری گرفته نمی‌شود — فقط اطلاعات نمایش داده می‌شود.
"""

from dataclasses import dataclass, field
from collections import deque
from typing import List, Optional, Dict
from datetime import datetime

from position_saver.models import LegType
from position_saver.importer.schemas import TradeRecord


# ═══════════════════════════════════════════════════
# Match Info
# ═══════════════════════════════════════════════════

@dataclass
class MatchInfo:
    """نتیجه‌ی جفت‌یابی یک trade"""
    trade: TradeRecord
    status: str = "open"        # "open" | "matched_buy" | "matched_sell"
                                # | "open_buy" | "orphan_sell"
    matched_with: List[str] = field(default_factory=list)
    matched_quantity: int = 0
    remaining_quantity: int = 0


@dataclass
class NetPositionResult:
    """نتیجه‌ی محاسبه‌ی موقعیت خالص"""
    symbol: str = ""
    method: str = "fifo"
    matches: List[MatchInfo] = field(default_factory=list)
    open_buys: int = 0
    open_sells: int = 0
    total_trades: int = 0
    matched_trades: int = 0
    net_position: int = 0
    summary_text: str = ""


# ═══════════════════════════════════════════════════
# محاسبه‌ی موقعیت خالص
# ═══════════════════════════════════════════════════

def compute_net_position(
    trades: List[TradeRecord],
    method: str = "fifo",
) -> NetPositionResult:
    """
    محاسبه‌ی موقعیت خالص برای یک نماد با ترتیب زمانی.

    Args:
        trades: لیست trades یک نماد
        method: "fifo" یا "lifo"

    Returns:
        NetPositionResult
    """
    result = NetPositionResult(
        method=method.lower(),
        total_trades=len(trades),
    )

    if not trades:
        result.summary_text = "هیچ معامله‌ای یافت نشد"
        return result

    # مرتب‌سازی زمانی
    sorted_trades = sorted(
        trades,
        key=lambda t: t.timestamp if t.timestamp else datetime.min
    )

    result.symbol = sorted_trades[0].symbol

    # صف BUY های باز
    buy_queue: deque = deque()

    # ساخت match info برای هر trade
    match_map: Dict[str, MatchInfo] = {}
    for t in sorted_trades:
        match_map[t.trade_id] = MatchInfo(
            trade=t,
            remaining_quantity=t.quantity,
        )

    # ─── پردازش ───
    for trade in sorted_trades:
        info = match_map[trade.trade_id]

        if trade.side == LegType.BUY:
            buy_queue.append([trade, trade.quantity])
        else:
            sell_remaining = trade.quantity

            while sell_remaining > 0 and buy_queue:
                if method == "lifo":
                    entry = buy_queue.pop()
                else:
                    entry = buy_queue.popleft()

                buy_trade, buy_remaining = entry[0], entry[1]

                if buy_remaining <= 0:
                    continue

                match_qty = min(buy_remaining, sell_remaining)

                info.status = "matched_sell"
                info.matched_with.append(buy_trade.trade_id)
                info.matched_quantity += match_qty
                info.remaining_quantity -= match_qty

                buy_info = match_map[buy_trade.trade_id]
                buy_info.status = "matched_buy"
                buy_info.matched_with.append(trade.trade_id)
                buy_info.matched_quantity += match_qty
                buy_info.remaining_quantity -= match_qty

                buy_remaining -= match_qty
                sell_remaining -= match_qty

                if buy_remaining > 0:
                    if method == "lifo":
                        buy_queue.append([buy_trade, buy_remaining])
                    else:
                        buy_queue.appendleft(
                            [buy_trade, buy_remaining])

            if sell_remaining > 0:
                info.status = "orphan_sell"
                info.remaining_quantity = sell_remaining

        result.matches.append(info)

    # ─── BUY های باز باقی‌مانده ───
    for entry in buy_queue:
        buy_trade, remaining = entry[0], entry[1]
        if remaining <= 0:
            continue
        info = match_map[buy_trade.trade_id]
        info.remaining_quantity = remaining
        if info.matched_quantity == 0:
            info.status = "open_buy"

    # ─── آمار ───
    open_buys = 0
    open_sells = 0
    matched = 0

    for info in result.matches:
        if info.status in ("matched_buy", "matched_sell"):
            matched += 1
        elif info.status == "open_buy":
            open_buys += info.remaining_quantity
        elif info.status == "orphan_sell":
            open_sells += info.remaining_quantity
        elif info.status == "open":
            if info.trade.side == LegType.BUY:
                open_buys += info.remaining_quantity
                info.status = "open_buy"
            else:
                open_sells += info.remaining_quantity
                info.status = "orphan_sell"

    result.open_buys = open_buys
    result.open_sells = open_sells
    result.matched_trades = matched
    result.net_position = open_buys - open_sells
    result.summary_text = _build_summary(result)

    return result


def _build_summary(r: NetPositionResult) -> str:
    """ساخت متن خلاصه"""
    parts = []
    parts.append(f"معاملات کل: {r.total_trades}")
    parts.append(f"جفت‌شده: {r.matched_trades}")

    if r.open_buys > 0:
        parts.append(f"BUY باز: {r.open_buys}")
    if r.open_sells > 0:
        parts.append(f"SELL بدون BUY: {r.open_sells}")

    if r.net_position == 0 and r.open_buys == 0 and r.open_sells == 0:
        parts.append("موقعیت: 🟢 کاملاً بسته")
    elif r.net_position > 0:
        parts.append(f"موقعیت: 🟢 {r.net_position} باز (Long)")
    elif r.net_position < 0:
        parts.append(f"موقعیت: 🔴 {abs(r.net_position)} باز (Short)")
    else:
        parts.append("موقعیت: ⚠️ ناهمگون")

    return " | ".join(parts)


# ═══════════════════════════════════════════════════
# گروه‌بندی trades بر اساس نماد
# ═══════════════════════════════════════════════════

def group_by_symbol(trades: List[TradeRecord]) -> Dict[str, List[TradeRecord]]:
    """گروه‌بندی trades بر اساس نماد"""
    result: Dict[str, List[TradeRecord]] = {}
    for t in trades:
        result.setdefault(t.symbol, []).append(t)
    return result


__all__ = [
    "MatchInfo",
    "NetPositionResult",
    "compute_net_position",
    "group_by_symbol",
]