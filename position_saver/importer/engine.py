# position_saver/importer/engine.py
# -*- coding: utf-8 -*-

"""
موتور اصلی ایمپورت — ارکستراتور + تشخیص تکراری.
"""

import logging
from datetime import datetime
from typing import List, Optional, Tuple

import jdatetime

from position_saver.importer.schemas import (
    TradeRecord, MatchedLot, ImportSettings, ImportResult, ImportBatch,
    CLOSE_REASON_OFFSET, CLOSE_REASON_OPEN, CLOSE_REASON_UNKNOWN,
)
from position_saver.importer.excel_parser import ExcelParser
from position_saver.importer.matcher import FifoMatcher
from position_saver.importer.snapshot_enricher import SnapshotEnricher


logger = logging.getLogger("PositionSaver.Importer.Engine")


class ImportEngine:
    """
    موتور ارکستراتور ایمپورت.

    جریان کار:
        ۱. parse      → فایل اکسل به TradeRecord
        ۲. enrich     → Snapshot + SYMBOL_MAP
        ۳. match      → FIFO به MatchedLot
        ۴. apply_lots → انتقال close_reason از FIFO به trades
        ۵. split      → تفکیک کامل/ناقص/آماده
        ۶. detect_dup → بررسی تکراری با storage
    """

    def __init__(self, storage=None):
        self.storage = storage
        self.parser = ExcelParser()
        self.enricher = SnapshotEnricher()

    # ═══════════════════════════════════════════════
    # API اصلی
    # ═══════════════════════════════════════════════

    def run(
        self,
        file_path: str,
        broker: str,
        settings: Optional[ImportSettings] = None,
        snapshot=None,
    ) -> ImportResult:
        """اجرای کامل ایمپورت"""
        if settings is None:
            settings = ImportSettings()

        result = ImportResult()

        # ─── ۱. پارس ───
        try:
            trades = self.parser.parse(
                file_path, broker=broker, settings=settings)
        except Exception as e:
            logger.exception(f"Parse failed: {e}")
            result.errors.append(f"خطا در پارس فایل: {e}")
            return result

        if not trades:
            result.warnings.append("هیچ معامله‌ای در فایل یافت نشد")
            return result

        result.trades = trades

        # ─── ۲. Enrichment ───
        try:
            self.enricher.enrich(trades, snapshot)
        except Exception as e:
            logger.exception(f"Enrich failed: {e}")
            result.warnings.append(f"خطا در Enrichment: {e}")

        # ─── ۳. Matcher ───
        # ✅ FIX BUG: مقدار اولیه امن برای lots
        lots: List[MatchedLot] = []
        try:
            matcher = FifoMatcher(method=settings.match_method)
            lots = matcher.match(trades)
            result.lots = lots
            result.open_lots = [l for l in lots if l.is_open]
            result.closed_lots = [l for l in lots if l.is_closed]
        except Exception as e:
            logger.exception(f"Match failed: {e}")
            result.errors.append(f"خطا در تطبیق: {e}")
            # lots همان [] می‌ماند

        # ─── ۴. انتقال close_reason از FIFO ───
        # ✅ FIX BUG: چک خالی نبودن lots
        if lots:
            try:
                self._apply_lots_to_trades(lots)
            except Exception as e:
                logger.exception(f"Apply lots failed: {e}")
                result.warnings.append(
                    f"خطا در انتقال close_reason: {e}")

        # ─── ۵. تفکیک کامل/ناقص ───
        for t in trades:
            if t.is_complete:
                result.complete_trades.append(t)
            else:
                result.incomplete_trades.append(t)

        return result

    # ═══════════════════════════════════════════════
    # اعمال نتیجه‌ی FIFO روی trades
    # ═══════════════════════════════════════════════

    def _apply_lots_to_trades(self, lots: List[MatchedLot]):
        """
        اگر lot بسته است، trade باز را به‌عنوان OFFSET علامت بزن.

        ✅ FIX BUG:
            - close_price و close_date روی SELL جفت‌شده هم ست می‌شود
            - flag is_offset_closer برای SELL جفت‌شده
            - BUY با چند SELL جزئی: close_price از میانگین وزنی
        """
        # گروه‌بندی lots بر اساس open_trade.trade_id
        # تا برای BUY که چند SELL دارد، میانگین وزنی محاسبه شود
        buy_lots: dict = {}
        for lot in lots:
            open_t = lot.open_trade
            if open_t is None:
                continue
            tid = open_t.trade_id
            if tid not in buy_lots:
                buy_lots[tid] = []
            buy_lots[tid].append(lot)

        for tid, group_lots in buy_lots.items():
            if not group_lots:
                continue

            open_t = group_lots[0].open_trade

            # جمع‌آوری SELLهای جفت‌شده
            closed_lots = [l for l in group_lots if l.is_closed]
            open_remaining = [l for l in group_lots if l.is_open]

            if closed_lots:
                # ─── BUY جفت‌شده ───
                open_t.close_reason = CLOSE_REASON_OFFSET
                open_t.needs_review = False
                open_t.user_chosen_reason = False

                # میانگین وزنی close_price
                total_qty = 0
                total_value = 0.0
                for lot in closed_lots:
                    q = lot.close_trade.quantity
                    total_qty += q
                    total_value += lot.close_trade.price * q

                if total_qty > 0:
                    avg_price = total_value / total_qty
                    open_t.close_price = avg_price

                    # آخرین close_date از آخرین SELL
                    last_close = closed_lots[-1].close_trade
                    open_t.close_date = last_close.raw_date
                    open_t.close_trade_ref = last_close.trade_id

                # ─── علامت‌گذاری SELLهای جفت‌شده ───
                for lot in closed_lots:
                    close_t = lot.close_trade
                    if close_t is None:
                        continue

                    # ✅ FIX: close_price و close_date روی SELL هم
                    close_t.close_reason = CLOSE_REASON_OFFSET
                    close_t.close_price = close_t.price
                    close_t.close_date = close_t.raw_date
                    close_t.user_chosen_reason = False
                    close_t.needs_review = False
                    # ✅ FIX: flag جدید
                    close_t.is_offset_closer = True

            # ─── BUY باقی‌مانده (باز) ───
            if open_remaining:
                # اگر BUY قبلاً به OFFSET علامت خورده، فقط
                # close_reason را دوباره ست نمی‌کنیم
                if open_t.close_reason != CLOSE_REASON_OFFSET:
                    if open_t.is_option and open_t.is_expired:
                        open_t.close_reason = CLOSE_REASON_UNKNOWN
                    else:
                        open_t.close_reason = CLOSE_REASON_OPEN

    # ═══════════════════════════════════════════════
    # تشخیص تکراری
    # ═══════════════════════════════════════════════

    def detect_duplicates(
        self,
        trades: List[TradeRecord],
    ) -> Tuple[List[TradeRecord], List[TradeRecord]]:
        """
        تشخیص تکراری‌ها بر اساس storage موجود.

        کلید یکتایی: (symbol, date, time, side)

        Returns:
            (unique_trades, duplicate_trades)
        """
        if self.storage is None:
            return trades, []

        try:
            existing_positions = self.storage.load_positions()
        except Exception as e:
            logger.warning(f"Load positions failed: {e}")
            return trades, []

        # ساخت set از کلیدهای موجود
        existing_keys = set()
        for pos in existing_positions:
            for leg in pos.legs:
                key = (
                    leg.symbol,
                    leg.open_date,
                    leg.open_time,
                    leg.leg_type.value,
                )
                existing_keys.add(key)

                # اگر لگ بسته شده، SELL هم ثبت شده
                if leg.close_price is not None:
                    close_key = (
                        leg.symbol,
                        leg.close_date,
                        leg.close_time,
                        "sell" if leg.leg_type.value == "buy" else "buy",
                    )
                    existing_keys.add(close_key)

        unique: List[TradeRecord] = []
        duplicates: List[TradeRecord] = []

        for t in trades:
            if t.duplicate_key in existing_keys:
                duplicates.append(t)
            else:
                unique.append(t)

        logger.info(
            f"Duplicate check: {len(unique)} unique, "
            f"{len(duplicates)} duplicates")

        return unique, duplicates


__all__ = ["ImportEngine"]