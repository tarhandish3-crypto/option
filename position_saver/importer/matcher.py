# position_saver/importer/matcher.py
# -*- coding: utf-8 -*-

"""
موتور تطبیق FIFO برای جفت کردن BUY و SELL.
"""

import logging
from collections import defaultdict, deque
from datetime import datetime
from typing import List

from position_saver.models import LegType
from position_saver.importer.schemas import TradeRecord, MatchedLot


logger = logging.getLogger("PositionSaver.Importer.Matcher")


def _ts_or_min(t: TradeRecord) -> datetime:
    return t.timestamp if t.timestamp else datetime.min


class FifoMatcher:
    """
    تطبیق‌دهنده‌ی FIFO.

    الگوریتم:
        ۱. هر BUY وارد صف باز می‌شود.
        ۲. هر SELL از ابتدای صف BUY کم می‌کند (FIFO).
        ۳. BUY های باقی‌مانده = lot های باز.
    """

    def __init__(self, method: str = "fifo"):
        self.method = method.lower()
        if self.method not in ("fifo", "lifo"):
            self.method = "fifo"

    def match(self, trades: List[TradeRecord]) -> List[MatchedLot]:
        """تطبیق لیست معاملات و بازگرداندن MatchedLot ها"""
        by_symbol = defaultdict(list)
        for t in trades:
            by_symbol[t.symbol].append(t)

        all_lots: List[MatchedLot] = []

        for symbol, symbol_trades in by_symbol.items():
            symbol_trades.sort(key=_ts_or_min)
            lots = self._match_symbol(symbol, symbol_trades)
            all_lots.extend(lots)

        all_lots.sort(
            key=lambda l: (l.open_timestamp
                           if l.open_timestamp else datetime.min))

        logger.info(
            f"Matched {len(all_lots)} lots "
            f"(closed: {sum(1 for l in all_lots if l.is_closed)}, "
            f"open: {sum(1 for l in all_lots if l.is_open)})")

        return all_lots

    def _match_symbol(
        self, symbol: str, trades: List[TradeRecord]
    ) -> List[MatchedLot]:
        """تطبیق معاملات یک نماد"""
        buy_queue: deque = deque()
        lots: List[MatchedLot] = []

        for trade in trades:
            if trade.side == LegType.BUY:
                buy_queue.append([trade, trade.quantity])
            else:
                self._consume_sell(symbol, trade, buy_queue, lots)

        # BUY های باقی‌مانده = lot های باز
        while buy_queue:
            entry = buy_queue.popleft()
            buy_trade, remaining = entry[0], entry[1]
            if remaining <= 0:
                continue

            if remaining == buy_trade.quantity:
                lots.append(MatchedLot(
                    symbol=symbol,
                    open_trade=buy_trade,
                    close_trade=None,
                ))
            else:
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
        """مصرف یک SELL از صف BUY"""
        remaining_sell = sell_trade.quantity

        while remaining_sell > 0 and buy_queue:
            if self.method == "lifo":
                entry = buy_queue.pop()
            else:
                entry = buy_queue.popleft()

            buy_trade, remaining_buy = entry[0], entry[1]

            if remaining_buy <= 0:
                continue

            match_qty = min(remaining_buy, remaining_sell)

            close_trade = sell_trade.copy_with_quantity(match_qty)

            if match_qty == buy_trade.quantity:
                open_trade = buy_trade
            else:
                open_trade = buy_trade.copy_with_quantity(match_qty)

            lots.append(MatchedLot(
                symbol=symbol,
                open_trade=open_trade,
                close_trade=close_trade,
            ))

            remaining_buy -= match_qty
            remaining_sell -= match_qty

            if remaining_buy > 0:
                if self.method == "lifo":
                    buy_queue.append([buy_trade, remaining_buy])
                else:
                    buy_queue.appendleft([buy_trade, remaining_buy])


__all__ = ["FifoMatcher"]