# position_saver/importer/engine.py
# -*- coding: utf-8 -*-

"""
موتور اصلی ایمپورت — ارکستراتور.
"""

import logging
from datetime import datetime
from typing import List, Optional

import jdatetime

from position_saver.importer.schemas import (
    TradeRecord, MatchedLot, ImportSettings, ImportResult, ImportBatch,
)
from position_saver.importer.excel_parser import ExcelParser
from position_saver.importer.matcher import FifoMatcher
from position_saver.importer.snapshot_enricher import SnapshotEnricher


logger = logging.getLogger("PositionSaver.Importer.Engine")


class ImportEngine:
    """
    موتور ارکستراتور ایمپورت.

    جریان کار:
        ۱. parse      → فایل اکسل به لیست TradeRecord
        ۲. enrich     → پر کردن از Snapshot
        ۳. match      → تطبیق FIFO به MatchedLot
        ۴. result     → ساخت ImportResult
    """

    def __init__(self, storage=None):
        self.storage = storage
        self.parser = ExcelParser()
        self.enricher = SnapshotEnricher()

    def run(
        self,
        file_path: str,
        broker: str,
        settings: Optional[ImportSettings] = None,
        snapshot=None,
    ) -> ImportResult:
        """
        اجرای کامل ایمپورت.

        Args:
            file_path: مسیر فایل اکسل
            broker: نام کارگزاری
            settings: تنظیمات کاربر
            snapshot: Snapshot بازار (اختیاری)

        Returns:
            ImportResult
        """
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

        # ─── ۳. تفکیک کامل/ناقص ───
        for t in trades:
            if t.is_complete:
                result.complete_trades.append(t)
            else:
                result.incomplete_trades.append(t)

        # ─── ۴. Matcher ───
        try:
            matcher = FifoMatcher(method=settings.match_method)
            lots = matcher.match(trades)
            result.lots = lots
            result.open_lots = [l for l in lots if l.is_open]
            result.closed_lots = [l for l in lots if l.is_closed]
        except Exception as e:
            logger.exception(f"Match failed: {e}")
            result.errors.append(f"خطا در تطبیق: {e}")

        return result

    def create_batch(
        self,
        broker: str,
        source_file: str,
        n_trades: int,
        n_open: int,
        n_closed: int,
        n_needs_review: int,
    ) -> ImportBatch:
        """ساخت شناسنامه‌ی ایمپورت"""
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
        )


__all__ = ["ImportEngine"]