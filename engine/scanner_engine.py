# engine/scanner_engine.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import List, Optional, Callable, Union
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
import pandas as pd

import config
from core.models import MarketSnapshot, ScanResult, Opportunity
from engine.scanner import Scanner
from analytics.payoff_calculator import enrich_opportunity_with_pnl

logger = logging.getLogger("OptionScanner.Engine.ScannerEngine")


class ScannerEngine:
    """
    موتور ارکستراتور اسکن زنجیره بورس

    ویژگی‌ها:
        - دریافت تصویر بازار (MarketSnapshot)
        - اعمال فیلترهای پیش‌پردازش روی نمادها
        - اجرای اسکن به صورت ترتیبی یا موازی
        - جمع‌آوری و گزارش نتایج
        - غنی‌سازی فرصت‌ها با محاسبات P&L
    """

    def __init__(
        self,
        snapshot: Union[MarketSnapshot, pd.DataFrame],
        filters: Optional[List[Callable]] = None
    ):
        """
        Args:
            snapshot: تصویر لحظه‌ای بازار یا DataFrame خام
            filters: لیست توابع فیلتر برای اعمال روی نمادها
        """
        # تبدیل خودکار DataFrame به MarketSnapshot
        if isinstance(snapshot, pd.DataFrame):
            self.snapshot = MarketSnapshot.from_dataframe(snapshot)
        else:
            self.snapshot = snapshot

        # ساخت ایندکس‌ها برای جستجوی سریع
        self.snapshot.build_indices()

        # فیلترها
        self.filters = filters or []

        # بارگذاری تنظیمات از config
        sys_config = config.get_system_config()
        self.parallel = sys_config.get("parallel_enabled", True)
        self.max_workers = sys_config.get("max_workers", 4)

        # ✅ قفل برای شمارنده‌های امن در محیط موازی
        self._stats_lock = Lock()

        # آمارهای اسکن
        self.scanned_count = 0
        self.error_count = 0

        logger.info(
            f"ScannerEngine initialized with {len(self.snapshot.option_contracts)} contracts, "
            f"{len(self.snapshot.underlying_assets)} underlyings, "
            f"parallel={self.parallel}, workers={self.max_workers}"
        )

    # =====================================================
    # متدهای اصلی
    # =====================================================

    def execute_full_scan(self) -> ScanResult:
        """
        اجرای اسکن کامل روی تمام نمادهای موجود پس از فیلترینگ

        Returns:
            ScanResult شامل تمام فرصت‌های کشف شده (غنی‌شده با P&L)
        """
        start_time = time.time()
        self._reset_stats()

        # 1. دریافت لیست نمادها
        target_tickers = list(self.snapshot.underlying_assets.keys())
        logger.info(
            f"Starting full market scan for {len(target_tickers)} underlying assets...")

        # 2. اعمال فیلترها
        target_tickers = self._apply_filters(target_tickers)

        if not target_tickers:
            logger.warning(
                "No underlying tickers passed the preprocessing filters.")
            return self._create_empty_result(start_time)

        # 3. اجرای اسکن
        if self.parallel and len(target_tickers) > 1:
            logger.info(
                f"Using parallel execution with {self.max_workers} workers.")
            all_opportunities = self._scan_parallel(target_tickers)
        else:
            logger.info("Using sequential execution mode.")
            all_opportunities = self._scan_sequential(target_tickers)

        # 4. ساخت نتیجه نهایی
        return self._create_result(all_opportunities, start_time)

    # =====================================================
    # متدهای فیلتر
    # =====================================================

    def _apply_filters(self, tickers: List[str]) -> List[str]:
        """
        اعمال فیلترها روی لیست نمادها

        Args:
            tickers: لیست نمادها

        Returns:
            List[str]: لیست فیلتر شده
        """
        for i, filter_func in enumerate(self.filters, 1):
            try:
                before_count = len(tickers)
                tickers_series = pd.Series(tickers)
                filtered_res = filter_func(tickers_series, self.snapshot)

                if isinstance(filtered_res, (pd.Series, pd.DataFrame)):
                    tickers = filtered_res.tolist()
                else:
                    tickers = list(filtered_res)

                after_count = len(tickers)
                logger.info(
                    f"Filter {i}: {before_count} -> {after_count} tickers remaining.")

            except Exception as e:
                with self._stats_lock:
                    self.error_count += 1
                logger.error(
                    f"Error applying filter {i}: {e}. Skipping this filter step.")
                continue

        return tickers

    # =====================================================
    # متدهای اسکن
    # =====================================================

    def _scan_sequential(self, tickers: List[str]) -> List[Opportunity]:
        """
        اسکن ترتیبی نمادها با غنی‌سازی P&L
        """
        all_opportunities = []

        for ticker in tickers:
            try:
                # ✅ هر ترد یک نمونه Scanner جدید می‌سازد
                opps = self._scan_single_ticker(ticker)
                if opps:
                    all_opportunities.extend(opps)
                    logger.debug(
                        f"Found {len(opps)} opportunities for {ticker}")
            except Exception as e:
                with self._stats_lock:
                    self.error_count += 1
                logger.error(f"Error scanning ticker {ticker}: {e}")

        return all_opportunities

    def _scan_parallel(self, tickers: List[str]) -> List[Opportunity]:
        """
        اسکن موازی نمادها با ایزوله‌سازی کامل و شمارنده‌های امن
        """
        all_opportunities = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ticker = {
                executor.submit(self._scan_single_ticker, ticker): ticker
                for ticker in tickers
            }

            for future in future_to_ticker:
                ticker = future_to_ticker[future]
                try:
                    opps = future.result()
                    if opps:
                        all_opportunities.extend(opps)
                        logger.debug(
                            f"Found {len(opps)} opportunities for {ticker}")
                except Exception as e:
                    with self._stats_lock:
                        self.error_count += 1
                    logger.error(f"Error in parallel scan for {ticker}: {e}")

        return all_opportunities

    def _scan_single_ticker(self, ticker: str) -> List[Opportunity]:
        """
        اسکن یک نماد منفرد - کاملاً ایزوله و Thread-Safe

        ✅ هر بار یک نمونه Scanner جدید ساخته می‌شود
        ✅ شمارنده‌ها با قفل به‌روزرسانی می‌شوند
        ✅ خطاهای غنی‌سازی باعث شکست کل فرآیند نمی‌شوند
        """
        try:
            # بررسی اولیه سریع
            opts = self.snapshot.get_options(ticker)
            if not opts or len(opts) < 2:
                return []

            # ✅ ساخت نمونه مجزا برای هر ترد (Thread-Safe)
            scanner = Scanner(self.snapshot)
            raw_opportunities = scanner.scan_ticker(ticker)

            if not raw_opportunities:
                return []

            # ✅ به‌روزرسانی امن شمارنده
            with self._stats_lock:
                self.scanned_count += 1

            # ✅ غنی‌سازی فرصت‌ها با P&L (با مدیریت خطا)
            enriched_opportunities = []
            for opp in raw_opportunities:
                try:
                    # تنظیم S0_stock از snapshot
                    underlying = self.snapshot.get_underlying(ticker)
                    if underlying and underlying.last_price > 0:
                        opp.S0_stock = underlying.last_price

                    # غنی‌سازی با P&L
                    enriched_opp = enrich_opportunity_with_pnl(opp)
                    enriched_opportunities.append(enriched_opp)
                except Exception as enrich_err:
                    logger.warning(
                        f"Failed to enrich opportunity {opp.strategy_name} on {ticker}: {enrich_err}"
                    )
                    # در صورت خطا، فرصت خام را نگه می‌داریم
                    enriched_opportunities.append(opp)

            logger.debug(
                f"Enriched {len(enriched_opportunities)} opportunities for {ticker}")
            return enriched_opportunities

        except Exception as e:
            with self._stats_lock:
                self.error_count += 1
            logger.error(f"Error scanning {ticker}: {e}")
            return []

    # =====================================================
    # متدهای کمکی
    # =====================================================

    def _reset_stats(self) -> None:
        """بازنشانی آمارها با قفل"""
        with self._stats_lock:
            self.scanned_count = 0
            self.error_count = 0

    def _create_empty_result(self, start_time: float) -> ScanResult:
        """
        ایجاد نتیجه خالی برای زمانی که هیچ نمادی باقی نمی‌ماند
        """
        duration = (time.time() - start_time) * 1000
        return ScanResult(
            timestamp=datetime.now(),
            total_strategies_scanned=0,
            total_combinations_generated=0,
            total_combinations_filtered=0,
            opportunities=[],
            execution_time_ms=duration
        )

    def _create_result(self, opportunities: List[Opportunity], start_time: float) -> ScanResult:
        """
        ایجاد نتیجه نهایی اسکن
        """
        duration = (time.time() - start_time) * 1000

        with self._stats_lock:
            scanned = self.scanned_count
            errors = self.error_count

        logger.info(
            f"[SUCCESS] Full market scan completed in {duration:.2f} ms. "
            f"Found {len(opportunities)} opportunities, "
            f"scanned {scanned} tickers, "
            f"errors: {errors}"
        )

        return ScanResult(
            timestamp=datetime.now(),
            total_strategies_scanned=scanned,
            total_combinations_generated=len(opportunities),
            total_combinations_filtered=0,
            opportunities=opportunities,
            execution_time_ms=duration
        )

    def get_summary(self) -> dict:
        """
        دریافت خلاصه آمار اسکنر (با قفل)
        """
        with self._stats_lock:
            scanned = self.scanned_count
            errors = self.error_count

        return {
            'total_underlyings': len(self.snapshot.underlying_assets),
            'total_options': len(self.snapshot.option_contracts),
            'tickers_scanned': scanned,
            'errors': errors,
            'parallel_enabled': self.parallel,
            'max_workers': self.max_workers,
            'filters_count': len(self.filters),
        }
