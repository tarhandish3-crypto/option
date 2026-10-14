# position_saver/importer/matcher.py
# -*- coding: utf-8 -*-

"""
موتور تطبیق FIFO/LIFO برای جفت کردن BUY و SELL.

خروجی: لیست MatchedLot
    - lot بسته: BUY + SELL
    - lot باز: فقط BUY
"""

import logging
from collections import defaultdict, deque
from datetime import datetime
from typing import List

from position_saver.models import LegType
from position_saver.importer.schemas import (
    TradeRecord, MatchedLot,
    CLOSE_REASON_OFFSET,
)


logger = logging.getLogger("PositionSaver.Importer.Matcher")


def _ts_or_min(t: TradeRecord) -> datetime:
    """کلید مرتب‌سازی: timestamp یا min"""
    return t.timestamp if t.timestamp else datetime.min


class FifoMatcher:
    """
    تطبیق‌دهنده‌ی FIFO/LIFO.

    الگوریتم:
        ۱. هر BUY وارد صف باز می‌شود (با مقدار باقی‌مانده)
        ۲. هر SELL از صف BUY مصرف می‌کند:
           - FIFO: از ابتدای صف
           - LIFO: از انتهای صف
        ۳. BUY های باقی‌مانده در صف = lot های باز
        ۴. برای هر lot بسته، close_trade.raw_date/time ذخیره می‌شود

    نکته:
        - Partial Match پشتیبانی می‌شود.
        - وقتی یک SELL چند BUY را می‌بندد، برای هر کدام یک lot جدا می‌سازد.
    """

    def __init__(self, method: str = "fifo"):
        self.method = method.lower()
        if self.method not in ("fifo", "lifo"):
            self.method = "fifo"

    # ═══════════════════════════════════════════════
    # API اصلی
    # ═══════════════════════════════════════════════

    def match(self, trades: List[TradeRecord]) -> List[MatchedLot]:
        """
        تطبیق لیست معاملات و بازگرداندن MatchedLot ها.

        Args:
            trades: لیست مرتب‌شده‌ی TradeRecord

        Returns:
            List[MatchedLot] مرتب‌شده بر اساس open_timestamp
        """
        # ─── گروه‌بندی بر اساس نماد ───
        by_symbol = defaultdict(list)
        for t in trades:
            by_symbol[t.symbol].append(t)

        all_lots: List[MatchedLot] = []

        # ─── پردازش هر نماد ───
        for symbol, symbol_trades in by_symbol.items():
            symbol_trades.sort(key=_ts_or_min)
            lots = self._match_symbol(symbol, symbol_trades)
            all_lots.extend(lots)

        # ─── مرتب‌سازی نهایی ───
        all_lots.sort(
            key=lambda l: (l.open_timestamp
                           if l.open_timestamp else datetime.min))

        n_closed = sum(1 for l in all_lots if l.is_closed)
        n_open = sum(1 for l in all_lots if l.is_open)
        logger.info(
            f"Matched {len(all_lots)} lots "
            f"(closed: {n_closed}, open: {n_open})")

        return all_lots

    # ═══════════════════════════════════════════════
    # داخلی
    # ═══════════════════════════════════════════════

    def _match_symbol(
        self, symbol: str, trades: List[TradeRecord]
    ) -> List[MatchedLot]:
        """تطبیق معاملات یک نماد"""
        # صف BUY باز: هر عنصر [trade, remaining_qty]
        buy_queue: deque = deque()
        lots: List[MatchedLot] = []

        for trade in trades:
            if trade.side == LegType.BUY:
                buy_queue.append([trade, trade.quantity])
            else:
                self._consume_sell(symbol, trade, buy_queue, lots)

        # ─── BUY های باقی‌مانده = lot های باز ───
        while buy_queue:
            entry = buy_queue.popleft()
            buy_trade, remaining = entry[0], entry[1]
            if remaining <= 0:
                continue

            if remaining == buy_trade.quantity:
                # کامل باز
                lots.append(MatchedLot(
                    symbol=symbol,
                    open_trade=buy_trade,
                    close_trade=None,
                ))
            else:
                # بخشی بسته شده، باقی‌مانده باز
                remaining_trade = buy_trade.copy_with_quantity(remaining)
                lots.append(MatchedLot(
                    symbol=symbol,
                    open_trade=remaining_trade,
                    close_trade=None,
                ))

        return lots

    def _consume_sell(
        self,
        symbol: str,
        sell_trade: TradeRecord,
        buy_queue: deque,
        lots: List[MatchedLot],
    ):
        """
        مصرف یک SELL از صف BUY.

        برای هر BUY که بخشی از آن بسته می‌شود، یک lot می‌سازد.
        """
        remaining_sell = sell_trade.quantity

        while remaining_sell > 0 and buy_queue:
            # انتخاب از ابتدا (FIFO) یا انتها (LIFO)
            if self.method == "lifo":
                entry = buy_queue.pop()
            else:
                entry = buy_queue.popleft()

            buy_trade, remaining_buy = entry[0], entry[1]

            if remaining_buy <= 0:
                continue

            match_qty = min(remaining_buy, remaining_sell)

            # ─── نسخه‌ی SELL با تعداد متناظر ───
            close_trade = sell_trade.copy_with_quantity(match_qty)
            self._inherit_close_metadata(close_trade, sell_trade)

            # ─── نسخه‌ی BUY با تعداد متناظر ───
            if match_qty == buy_trade.quantity:
                open_trade = buy_trade
            else:
                open_trade = buy_trade.copy_with_quantity(match_qty)
                self._inherit_open_metadata(open_trade, buy_trade)

            # ─── ساخت lot ───
            lots.append(MatchedLot(
                symbol=symbol,
                open_trade=open_trade,
                close_trade=close_trade,
            ))

            # ─── کاهش مقادیر ───
            remaining_buy -= match_qty
            remaining_sell -= match_qty

            # ─── برگرداندن BUY باقی‌مانده به صف ───
            if remaining_buy > 0:
                if self.method == "lifo":
                    buy_queue.append([buy_trade, remaining_buy])
                else:
                    buy_queue.appendleft([buy_trade, remaining_buy])

    # ═══════════════════════════════════════════════
    # انتقال متادیتا (به‌جای کپی صرف)
    # ═══════════════════════════════════════════════

    @staticmethod
    def _inherit_close_metadata(new_trade: TradeRecord,
                                 original: TradeRecord):
        """
        انتقال فیلدهای متادیتا از SELL اصلی به نسخه‌ی بریده.
        """
        # فیلدهای شناسایی
        new_trade.symbol = original.symbol
        new_trade.side = original.side
        new_trade.raw_date = original.raw_date
        new_trade.raw_time = original.raw_time
        new_trade.timestamp = original.timestamp
        new_trade.raw_status = original.raw_status
        new_trade.broker = original.broker
        # متادیتای Snapshot
        new_trade.strike_price = original.strike_price
        new_trade.expiry_date = original.expiry_date
        new_trade.contract_size = original.contract_size
        new_trade.option_kind = original.option_kind
        new_trade.underlying_symbol = original.underlying_symbol
        new_trade.ins_code = original.ins_code
        new_trade.ins_code_ua = original.ins_code_ua
        # وضعیت بستن
        new_trade.close_reason = original.close_reason or CLOSE_REASON_OFFSET
        new_trade.user_chosen_reason = original.user_chosen_reason
        new_trade.needs_review = original.needs_review

    @staticmethod
    def _inherit_open_metadata(new_trade: TradeRecord,
                               original: TradeRecord):
        """
        انتقال فیلدهای متادیتا از BUY اصلی به نسخه‌ی بریده.
        """
        new_trade.symbol = original.symbol
        new_trade.side = original.side
        new_trade.raw_date = original.raw_date
        new_trade.raw_time = original.raw_time
        new_trade.timestamp = original.timestamp
        new_trade.raw_status = original.raw_status
        new_trade.broker = original.broker
        # متادیتای Snapshot
        new_trade.strike_price = original.strike_price
        new_trade.expiry_date = original.expiry_date
        new_trade.contract_size = original.contract_size
        new_trade.option_kind = original.option_kind
        new_trade.underlying_symbol = original.underlying_symbol
        new_trade.ins_code = original.ins_code
        new_trade.ins_code_ua = original.ins_code_ua
        # وضعیت بستن (از BUY اصلی)
        new_trade.close_reason = original.close_reason
        new_trade.user_chosen_reason = original.user_chosen_reason
        new_trade.needs_review = original.needs_review


__all__ = ["FifoMatcher"]