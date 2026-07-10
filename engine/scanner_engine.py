# engine/scanner_engine.py
# -*- coding: utf-8 -*-


from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import List, Optional, Callable, Dict, Any, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import pandas as pd

import config
from core.models import MarketSnapshot, ScanResult, Opportunity
from engine.scanner import Scanner
from analytics.probabilities_calculator import calculate_strategy_greeks
from strategies.core import get_all_strategies

logger = logging.getLogger("OptionScanner.Engine.ScannerEngine")


def _inject_greeks(opp: Opportunity, spot_price: float) -> None:
    """محاسبه یونانی‌ها با بهینه‌سازی تخصیص حافظه و استفاده از متغیرهای محلی."""
    from core.enums import OptionType as OT, Side as SD
    from config import RISK_FREE_RATE, DEFAULT_VOLATILITY

    if not opp.legs or spot_price <= 0:
        return

    legs_for_greeks = []
    total_iv = 0.0
    valid_legs_count = 0

    for leg in opp.legs:
        contract = leg.contract
        if not contract or contract.option_type == OT.STOCK:
            continue

        iv = getattr(contract, 'iv', None) or getattr(
            contract, 'implied_volatility', None) or DEFAULT_VOLATILITY
        iv_float = float(iv) if iv and iv > 0 else DEFAULT_VOLATILITY

        total_iv += iv_float
        valid_legs_count += 1

        legs_for_greeks.append({
            'option_type': 'call' if contract.option_type == OT.CALL else 'put',
            'strike_price': contract.strike_price,
            'position': (1 if leg.side == SD.BUY else -1) * leg.ratio,
            'iv': iv_float
        })

    if not legs_for_greeks:
        return

    avg_iv = total_iv / valid_legs_count if valid_legs_count > 0 else DEFAULT_VOLATILITY

    result = calculate_strategy_greeks(
        legs=legs_for_greeks,
        current_price=spot_price,
        days_to_maturity=opp.days_to_maturity or 30,
        risk_free_rate=RISK_FREE_RATE,
        volatility=avg_iv,)

    meta = opp.metadata
    meta.update({
        'delta': result.get('delta', 0.0),
        'gamma': result.get('gamma', 0.0),
        'theta': result.get('theta_daily', 0.0),
        'vega': result.get('vega', 0.0),
        'rho': result.get('rho', 0.0), })


class ScannerEngine:
    __slots__ = (
        'snapshot', 'filters', 'parallel', 'max_workers',
        '_stats_lock', 'scanned_count', 'error_count',
        'total_generated_stats', 'total_filtered_stats')

    def __init__(self, snapshot: Union[MarketSnapshot, pd.DataFrame], filters: Optional[List[Callable]] = None):
        self.snapshot = MarketSnapshot.from_dataframe(
            snapshot) if isinstance(snapshot, pd.DataFrame) else snapshot
        self.snapshot.build_indices()
        self.filters = filters or []

        sys_config = config.get_system_config()
        self.parallel = sys_config.get("parallel_enabled", True)
        self.max_workers = sys_config.get("max_workers", 4)
        self._stats_lock = Lock()

        self.scanned_count = 0
        self.error_count = 0
        self.total_generated_stats = 0
        self.total_filtered_stats = 0

    def execute_full_scan(self) -> ScanResult:
        """اجرای اسکن کامل بازار با مدیریت آمارگیری دقیق."""
        start_time = time.time()
        self._reset_stats()

        target_tickers = list(self.snapshot.underlying_assets.keys())
        all_strategies = get_all_strategies()

        if self.parallel and len(target_tickers) > 1:
            all_opportunities = self._scan_parallel(
                target_tickers, all_strategies)
        else:
            all_opportunities = self._scan_sequential(
                target_tickers, all_strategies)

        return self._create_result(all_opportunities, start_time)

    def _scan_sequential(self, tickers: List[str], all_strategies: Dict[str, Any]) -> List[Opportunity]:
        all_opportunities = []
        for ticker in tickers:
            opps = self._scan_single_ticker(ticker, all_strategies)
            if opps:
                all_opportunities.extend(opps)
        return all_opportunities

    def _scan_parallel(self, tickers: List[str], all_strategies: Dict[str, Any]) -> List[Opportunity]:
        all_opportunities = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ticker = {executor.submit(
                self._scan_single_ticker, ticker, all_strategies): ticker for ticker in tickers}
            for future in as_completed(future_to_ticker):
                opps = future.result()
                if opps:
                    all_opportunities.extend(opps)
        return all_opportunities

    def _scan_single_ticker(self, ticker: str, all_strategies: Dict[str, Any]) -> List[Opportunity]:
        try:
            opts = self.snapshot.get_options_by_underlying(ticker)
            if not opts or len(opts) < 2:
                return []

            scanner = Scanner(self.snapshot)
            raw_opportunities = scanner.scan_ticker_with_strategies(
                ticker, all_strategies)

            if not raw_opportunities:
                return []

            underlying = self.snapshot.get_underlying_assets(ticker)
            s0_stock = getattr(underlying, 'last_price')

            if s0_stock > 0:
                price_levels = config.get_price_levels(s0_stock)
                self.snapshot.price_levels = price_levels

            scanner_stats = scanner.get_stats()
            with self._stats_lock:
                self.scanned_count += 1
                self.total_generated_stats += scanner_stats.get(
                    "generated", len(raw_opportunities))
                self.total_filtered_stats += scanner_stats.get("filtered", 0)

            enriched_opportunities = []

            # فلگ فعال بودن یا عدم فعال بودن محاسبه یونانی ها
            calculate_greeks_flag = config.get_feature_flags().get("calculate_greeks")

            for opp in raw_opportunities:
                if s0_stock > 0:
                    opp.S0_stock = s0_stock

                meta = opp.metadata
                if hasattr(opp, 'returns_monthly_pct') and opp.returns_monthly_pct is not None:
                    returns_list = opp.returns_monthly_pct.tolist() if hasattr(
                        opp.returns_monthly_pct, 'tolist') else list(opp.returns_monthly_pct)
                    meta.update({
                        'returns_monthly_pct': returns_list,
                        'net_profits_closed': returns_list})

                meta.update({
                    'max_profit': opp.max_profit,
                    'max_loss': opp.max_loss,
                    'break_even_points': opp.break_even_points,
                    'net_premium': opp.net_premium
                })

                # تزریق یونانی‌ها در صورت فعال بودن فلگ سیستم
                if calculate_greeks_flag:
                    _inject_greeks(opp, s0_stock)

                enriched_opportunities.append(opp)

            return enriched_opportunities

        except Exception as e:
            with self._stats_lock:
                self.error_count += 1
            logger.error(
                f"Critical error scanning {ticker}: {e}", exc_info=True)
            return []

    def _reset_stats(self) -> None:
        with self._stats_lock:
            self.scanned_count = 0
            self.error_count = 0
            self.total_generated_stats = 0
            self.total_filtered_stats = 0

    def _create_result(self, opportunities: List[Opportunity], start_time: float) -> ScanResult:
        duration = (time.time() - start_time) * 1000
        with self._stats_lock:
            return ScanResult(
                timestamp=datetime.now(),
                total_strategies_scanned=self.scanned_count,
                total_combinations_generated=self.total_generated_stats,
                total_combinations_filtered=self.total_filtered_stats,
                opportunities=opportunities,
                execution_time_ms=duration
            )
