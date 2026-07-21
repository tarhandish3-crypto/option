# engine/scanner.py
# -*- coding: utf-8 -*-

"""
موتور اسکن متمرکز (Scanner Engine) - معماری V5.
هماهنگ با اینترفیس ژنراتورهای جدید (ContractIndex Optimized).
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Iterator, Optional

from core.models import MarketSnapshot, Opportunity, OptionContract
from strategies.core import get_all_strategies
from strategies.generators import get_generator
from strategies.matching.contract_index import ContractIndex

logger = logging.getLogger("OptionScanner.Engine.TickerScanner")


class Scanner:
    """
    موتور اسکن متمرکز روی یک نماد پایه که با ContractIndex کار می‌کند.
    مجهز به خروجی جریانی و کش Index.
    """

    __slots__ = ('snapshot', '_contract_scores', '_generated_count',
                 '_filtered_count', '_contract_index')

    def __init__(self, snapshot: MarketSnapshot):
        self.snapshot = snapshot
        self._contract_scores: Dict[str, float] = {}
        self._contract_index: Optional[ContractIndex] = None
        self._generated_count = 0
        self._filtered_count = 0

    def _build_index(self, contracts: List[OptionContract]) -> ContractIndex:
        """ساخت ContractIndex با کش"""
        if self._contract_index is None:
            self._contract_index = ContractIndex(contracts)
        return self._contract_index

    # ============================================================
    # INTERFACE METHODS (Compatibility + Streaming)
    # ============================================================

    def scan_ticker(self, ticker: str) -> List[Opportunity]:
        """اسکن کامل (سازگاری با نسخه‌های قبلی)"""
        return list(self.scan_ticker_stream(ticker))

    def scan_ticker_stream(self, ticker: str) -> Iterator[Opportunity]:
        """اسکن جریانی یک نماد"""
        return self._scan_with_strategies(ticker, get_all_strategies())

    def scan_ticker_with_strategies(
            self,
            ticker: str,
            all_strategies: Dict[str, Any]) -> List[Opportunity]:

        return list(self.scan_ticker_stream_with_strategies(ticker, all_strategies))

    def scan_ticker_stream_with_strategies(
            self,
            ticker: str,
            all_strategies: Dict[str, Any]) -> Iterator[Opportunity]:
        """نسخه جریانی با استراتژی‌های ورودی"""
        yield from self._scan_with_strategies(ticker, all_strategies)

    # ============================================================
    # CORE SCANNING LOGIC
    # ============================================================

    def _scan_with_strategies(
            self,
            ticker: str,
            all_strategies: Dict[str, Any]) -> Iterator[Opportunity]:
        """
        پیاده‌سازی مشترک اسکن — خروجی جریانی با استفاده از ContractIndex
        """
        # ۱. دریافت دارایی پایه
        underlying = self.snapshot.get_underlying_assets(ticker)
        if not underlying or getattr(underlying, 'is_frozen', False):
            return

        # ۲. دریافت قراردادها
        contracts = self.snapshot.get_options_by_underlying(ticker)
        if not contracts or len(contracts) < 2:
            return

        logger.info(f"Scanning {ticker}: {len(contracts)} contracts")

        # ۳. ساخت ایندکس (با کش) و محاسبه نقدشوندگی
        contract_index = self._build_index(contracts)

        # ۴. اسکن با استراتژی‌ها
        get_generator_func = get_generator
        get_stats_attr = getattr

        for strategy_name, strategy_def in all_strategies.items():
            try:
                generator = get_generator_func(strategy_def)
                if generator is None:
                    continue

                # امضای جدید با index
                opps_iterator = generator.generate(
                    underlying=underlying,
                    index=contract_index,
                    contract_scores=self._contract_scores)

                strategy_count = 0
                for opp in opps_iterator:
                    if opp is not None:
                        yield opp
                        strategy_count += 1

                # به‌روزرسانی آمار
                gen_stats = get_stats_attr(
                    generator, 'get_stats', lambda: {})()
                self._generated_count += gen_stats.get(
                    "generated", strategy_count)
                self._filtered_count += gen_stats.get("filtered", 0)

            except Exception as e:
                logger.error(
                    f"Error generating {strategy_name} on {ticker}: {e}", exc_info=True)

    # ============================================================
    # STATS & TELEMETRY
    # ============================================================

    def get_stats(self) -> Dict[str, int]:
        """ارائه آمارهای تجمیعی"""
        return {
            "generated": self._generated_count,
            "filtered": self._filtered_count}

    def reset_stats(self) -> None:
        """بازنشانی آمار"""
        self._generated_count = 0
        self._filtered_count = 0

    def scan_all_tickers(self) -> List[Opportunity]:
        """اسکن ترتیبی تمام نمادها (سازگاری)"""
        return list(self.scan_all_tickers_stream())

    def scan_all_tickers_stream(self) -> Iterator[Opportunity]:
        """اسکن جریانی تمام نمادها"""
        for ticker in self.snapshot.underlying_assets.keys():
            yield from self.scan_ticker_stream(ticker)
