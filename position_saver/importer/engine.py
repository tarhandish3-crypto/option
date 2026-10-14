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
        try:
            matcher = FifoMatcher(method=settings.match_method)
            lots = matcher.match(trades)
            result.lots = lots
            result.open_lots = [l for l in lots if l.is_open]
            result.closed_lots = [l for l in lots if l.is_closed]
        except Exception as e:
            logger.exception(f"Match failed: {e}")
            result.errors.append(f"خطا در تطبیق: {e}")

        # ─── ۴. انتقال close_reason از FIFO ───
        self._apply_lots_to_trades(lots)

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
        اگر lot باز است ولی expiry گذشته، trade را UNKNOWN نگه دار
        تا کاربر تصمیم بگیرد.
        """
        for lot in lots:
            open_t = lot.open_trade
            if open_t is None:
                continue

            if lot.is_closed:
                # BUY + SELL در batch → آفست
                open_t.close_reason = CLOSE_REASON_OFFSET
                open_t.close_price = lot.close_trade.price
                open_t.close_date = lot.close_trade.raw_date
                open_t.close_trade_ref = lot.close_trade.trade_id
                open_t.user_chosen_reason = False
                open_t.needs_review = False

                # SELL را هم علامت‌گذاری کن
                close_t = lot.close_trade
                if close_t is not None:
                    close_t.close_reason = CLOSE_REASON_OFFSET
                    close_t.user_chosen_reason = False
                    close_t.needs_review = False
            else:
                # BUY باز (بدون SELL)
                if open_t.is_option and open_t.is_expired:
                    # منقضی بدون SELL → نیازمند تصمیم
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
                        # سمت مخالف
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

    # ═══════════════════════════════════════════════
    # ساخت شناسنامه‌ی ایمپورت
    # ═══════════════════════════════════════════════

    def create_batch(
        self,
        broker: str,
        source_file: str,
        n_trades: int,
        n_open: int,
        n_closed: int,
        n_needs_review: int,
        n_duplicates: int = 0,
    ) -> ImportBatch:
        """ساخت ImportBatch"""
        now = datetime.now()
        try:
            jalali = jdatetime.date.today().strftime("%Y/%m/%d")
        except Exception:
            jalali = ""

        return ImportBatch(
            broker=broker,
            source_file=source_file,
            created_at=now.isoformat(),
            import_date_jalali=jalali,
            n_trades=n_trades,
            n_positions_open=n_open,
            n_positions_closed=n_closed,
            n_needs_review=n_needs_review,
            n_duplicates=n_duplicates,
        )


__all__ = ["ImportEngine"]