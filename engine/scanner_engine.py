# engine/scanner_engine.py
# -*- coding: utf-8 -*-

"""
موتور ارکستراتور اسکن زنجیره بازار (ScannerEngine) - معماری V4

این ماژول فرآیند دریافت تصاویر بازار، فیلترینگ اولیه دارایی‌های پایه، توزیع بار روی 
ThreadPoolExecutor به صورت کاملاً Thread-Safe و غنی‌سازی نهایی مدل‌ها با P&L را مدیریت می‌کند.
اصلاحات V4: همگام‌سازی کامل با زنجیره قیمت پایانی بورس ایران و جمع‌آوری آمارهای فیلترینگ ژنراتورها.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import List, Optional, Callable, Union, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import pandas as pd

import config
from core.models import MarketSnapshot, ScanResult, Opportunity
from engine.scanner import Scanner
from analytics.payoff_calculator import enrich_opportunity_with_pnl
from analytics.probabilities_calculator import calculate_strategy_greeks
from strategies.core import get_all_strategies
import config

logger = logging.getLogger("OptionScanner.Engine.ScannerEngine")


def _inject_greeks(opp: Opportunity, spot_price: float) -> None:
    """
    محاسبه یونانی‌های position-level و تزریق به metadata opportunity.
    از calculate_strategy_greeks برای جمع‌بندی یونانی همه لگ‌ها استفاده می‌کند.
    """
    from core.enums import OptionType as OT, Side as SD
    from config import RISK_FREE_RATE, DEFAULT_VOLATILITY

    if not opp.legs or spot_price <= 0:
        return

    legs_input = []
    for leg in opp.legs:
        contract = leg.contract
        if not contract or contract.option_type == OT.STOCK:
            continue
        opt_type_str = 'call' if contract.option_type == OT.CALL else 'put'
        position = 1 if leg.side == SD.BUY else -1
        iv = getattr(contract, 'iv', None) or getattr(
            contract, 'implied_volatility', None) or DEFAULT_VOLATILITY
        legs_input.append({
            'option_type': opt_type_str,
            'strike_price': contract.strike_price,
            'position': position * leg.ratio,
            'iv': float(iv) if iv and iv > 0 else DEFAULT_VOLATILITY,
        })

    if not legs_input:
        return

    # میانگین DTE لگ‌های اختیار
    dte = opp.days_to_maturity or 30
    # میانگین IV لگ‌ها
    avg_iv = sum(l['iv'] for l in legs_input) / len(legs_input)

    # ساخت ساختار ورودی برای calculate_strategy_greeks
    legs_for_greeks = [
        {**l, 'position': l['position']}
        for l in legs_input
    ]

    result = calculate_strategy_greeks(
        legs=legs_for_greeks,
        current_price=spot_price,
        days_to_maturity=dte,
        risk_free_rate=RISK_FREE_RATE,
        volatility=avg_iv,
    )

    opp.metadata.update({
        'delta': result.get('delta', 0.0),
        'gamma': result.get('gamma', 0.0),
        'theta': result.get('theta_daily', 0.0),
        'vega': result.get('vega', 0.0),
        'rho':  result.get('rho', 0.0),
    })


class ScannerEngine:
    """
    موتور ارکستراتور پوزیشن‌یابی و مدیریت موازی اسکن بورس ایران
    """

    def __init__(
            self,
            snapshot: Union[MarketSnapshot, pd.DataFrame],
            filters: Optional[List[Callable]] = None):
        # تبدیل خودکار DataFrame به ساختار داده غنی مرجع پروژه
        if isinstance(snapshot, pd.DataFrame):
            self.snapshot = MarketSnapshot.from_dataframe(snapshot)
        else:
            self.snapshot = snapshot

        # ساخت ایندکس‌های جستجوی سریع در حافظه
        self.snapshot.build_indices()

        self.filters = filters or []

        # بارگذاری پارامترهای پردازش موازی از کانفیگ سیستم
        sys_config = config.get_system_config()
        self.parallel = sys_config.get("parallel_enabled", True)
        self.max_workers = sys_config.get("max_workers", 4)

        # قفل پردازش موازی برای تخصیص امن وضعیت‌ها
        self._stats_lock = Lock()

        # بازنشانی و آماده‌سازی شمارنده‌ها
        self.scanned_count = 0
        self.error_count = 0
        self.total_generated_stats = 0
        self.total_filtered_stats = 0

        logger.info(
            f"ScannerEngine V4 initialized: {len(self.snapshot.option_contracts)} contracts, "
            f"parallel={self.parallel}, workers={self.max_workers}")

    # =====================================================
    # متدهای اصلی اجرای عملیات
    # =====================================================

    def execute_full_scan(self) -> ScanResult:
        """
        اجرای اسکن تمام‌عیار زنجیره اختیارات بازار پس از اعمال پیش‌فیلترها
        """
        start_time = time.time()
        self._reset_stats()

        target_tickers = list(self.snapshot.underlying_assets.keys())
        logger.info(
            f"Starting full market scan for {len(target_tickers)} underlying assets...")

        # اعمال فیلترهای پیش‌پردازش
        target_tickers = self._apply_filters(target_tickers)

        if not target_tickers:
            logger.warning(
                "No underlying tickers passed the preprocessing filters.")
            return self._create_empty_result(start_time)

        # ✅ بارگذاری استراتژی‌ها یک‌بار برای کل scan — نه هر ticker جداگانه
        all_strategies = get_all_strategies()
        logger.info(
            f"Loaded {len(all_strategies)} strategies for this scan cycle.")

        # انتخاب مکانیزم توزیع بار
        if self.parallel and len(target_tickers) > 1:
            logger.info(
                f"Using parallel execution with {self.max_workers} workers.")
            all_opportunities = self._scan_parallel(
                target_tickers, all_strategies)
        else:
            logger.info("Using sequential execution mode.")
            all_opportunities = self._scan_sequential(
                target_tickers, all_strategies)

        return self._create_result(all_opportunities, start_time)

    # =====================================================
    # پیاده‌سازی متدهای فیلترینگ
    # =====================================================

    def _apply_filters(self, tickers: List[str]) -> List[str]:
        """اعمال زنجیره‌ای فیلترهای پیش‌پردازش به صورت وکتورایز شده"""
        for i, filter_func in enumerate(self.filters, 1):
            try:
                before_count = len(tickers)
                tickers_series = pd.Series(tickers)
                filtered_res = filter_func(tickers_series, self.snapshot)

                if isinstance(filtered_res, (pd.Series, pd.DataFrame)):
                    tickers = filtered_res.tolist()
                else:
                    tickers = list(filtered_res)

                logger.info(
                    f"Filter {i} ({filter_func.__name__}): {before_count} -> {len(tickers)} tickers remaining.")
            except Exception as e:
                with self._stats_lock:
                    self.error_count += 1
                logger.error(
                    f"Error applying filter {i}: {e}. Skipping filter step.")
                continue

        return tickers

    # =====================================================
    # مدیریت موازی‌سازی و همزمانی
    # =====================================================

    def _scan_sequential(self, tickers: List[str], all_strategies: Dict[str, Any]) -> List[Opportunity]:
        """اسکن گام‌به‌گام و تک‌تردی نمادها"""
        all_opportunities = []
        for ticker in tickers:
            try:
                opps = self._scan_single_ticker(ticker, all_strategies)
                if opps:
                    all_opportunities.extend(opps)
            except Exception as e:
                with self._stats_lock:
                    self.error_count += 1
                logger.error(f"Error scanning ticker {ticker}: {e}")
        return all_opportunities

    def _scan_parallel(self, tickers: List[str], all_strategies: Dict[str, Any]) -> List[Opportunity]:
        """اسکن کاملاً موازی با as_completed برای پردازش سریع‌تر نتایج"""
        all_opportunities = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ticker = {
                executor.submit(self._scan_single_ticker, ticker, all_strategies): ticker
                for ticker in tickers}

            # ✅ as_completed: نتایج بلافاصله با تکمیل هر future پردازش می‌شوند
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    opps = future.result()
                    if opps:
                        all_opportunities.extend(opps)
                except Exception as e:
                    with self._stats_lock:
                        self.error_count += 1
                    logger.error(
                        f"Error in parallel scan thread for {ticker}: {e}")
        return all_opportunities

    def _scan_single_ticker(self, ticker: str, all_strategies: Dict[str, Any]) -> List[Opportunity]:
        """اسکن تک نماد - کاملاً تردسیف همراه با هماهنگ‌سازی زنجیره قیمت ایران (Fallback)"""
        try:
            opts = self.snapshot.get_options(ticker)
            if not opts or len(opts) < 2:
                return []

            # نمونه‌سازی اختصاصی در سطح ترد جهت حذف هم‌پوشانی اشاره‌گرها
            scanner = Scanner(self.snapshot)
            # استراتژی‌ها از بیرون پاس می‌شوند — بدون re-copy در هر thread
            raw_opportunities = scanner.scan_ticker_with_strategies(
                ticker, all_strategies)

            if not raw_opportunities:
                return []

            underlying = self.snapshot.get_underlying(ticker)

            # استخراج قیمت مرجع (S0) بر اساس دکترین اولویت قیمت پایانی بورس ایران
            s0_stock = 0.0
            if underlying:
                if getattr(underlying, 'close_price', 0) > 0:
                    s0_stock = underlying.close_price
                elif getattr(underlying, 'last_price', 0) > 0:
                    s0_stock = underlying.last_price
                elif getattr(underlying, 'yesterday_price', 0) > 0:
                    s0_stock = underlying.yesterday_price

            # به‌روزرسانی آمارهای حیاتی موتور اسکنر با محاسبات تجمعی ژنراتورها
            scanner_stats = scanner.get_stats() if hasattr(scanner, 'get_stats') else {
                "generated": len(raw_opportunities), "filtered": 0}

            with self._stats_lock:
                self.scanned_count += 1
                self.total_generated_stats += scanner_stats.get(
                    "generated", len(raw_opportunities))
                self.total_filtered_stats += scanner_stats.get("filtered", 0)

            # S0 را روی همه فرصت‌ها تنظیم کن
            if s0_stock > 0:
                for opp in raw_opportunities:
                    opp.S0_stock = s0_stock

            # ✅ enrichment موازی — هر opportunity مستقل است، thread-safe
            enrich_workers = min(len(raw_opportunities), 4)

            def _enrich(opp: Opportunity) -> Opportunity:
                try:
                    opp = enrich_opportunity_with_pnl(opp)
                except Exception as enrich_err:
                    logger.warning(
                        f"Failed to enrich {opp.strategy_name} on {ticker}: {enrich_err}")

                # ✅ محاسبه یونانی‌های position-level اگر flag فعال باشد
                try:
                    if config.get_feature_flags().get("calculate_greeks", True):
                        _inject_greeks(opp, s0_stock)
                except Exception as greek_err:
                    logger.debug(
                        f"Greeks calculation skipped for {opp.strategy_name}: {greek_err}")

                return opp

            if enrich_workers > 1:
                with ThreadPoolExecutor(max_workers=enrich_workers) as enrich_pool:
                    enriched_opportunities = list(
                        enrich_pool.map(_enrich, raw_opportunities))
            else:
                enriched_opportunities = [
                    _enrich(opp) for opp in raw_opportunities]

            return enriched_opportunities

        except Exception as e:
            with self._stats_lock:
                self.error_count += 1
            logger.error(f"Critical error scanning {ticker}: {e}")
            return []

    # =====================================================
    # مدیریت خروجی‌ها و آمارگیری تجمعی
    # =====================================================

    def _reset_stats(self) -> None:
        with self._stats_lock:
            self.scanned_count = 0
            self.error_count = 0
            self.total_generated_stats = 0
            self.total_filtered_stats = 0

    def _create_empty_result(self, start_time: float) -> ScanResult:
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
        duration = (time.time() - start_time) * 1000

        with self._stats_lock:
            scanned = self.scanned_count
            errors = self.error_count
            gen_stats = self.total_generated_stats
            filt_stats = self.total_filtered_stats

        logger.info(
            f"[SUCCESS] Scan completed in {duration:.2f} ms. "
            f"Opportunities: {len(opportunities)} | Scanned Tickers: {scanned} | "
            f"Generator Filtered: {filt_stats} | Errors: {errors}"
        )

        return ScanResult(
            timestamp=datetime.now(),
            total_strategies_scanned=scanned,
            total_combinations_generated=gen_stats,
            total_combinations_filtered=filt_stats,
            opportunities=opportunities,
            execution_time_ms=duration
        )

    def get_summary(self) -> Dict[str, Any]:
        with self._stats_lock:
            return {
                'total_underlyings': len(self.snapshot.underlying_assets),
                'total_options': len(self.snapshot.option_contracts),
                'tickers_scanned': self.scanned_count,
                'total_generated': self.total_generated_stats,
                'total_filtered': self.total_filtered_stats,
                'errors': self.error_count,
                'parallel_enabled': self.parallel,
                'max_workers': self.max_workers,
            }
