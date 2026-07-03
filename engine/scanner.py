# engine/scanner.py
# -*- coding: utf-8 -*-

"""
موتور اسکن متمرکز (Scanner Engine) - معماری V5.
هماهنگ با اینترفیس ژنراتورهای جدید (ContractIndex Optimized).
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any, Iterator, Optional

from config import MIN_VOLUME
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
        all_strategies: Dict[str, Any]
    ) -> List[Opportunity]:
        """نسخه با استراتژی‌های ورودی (سازگاری)"""
        return list(self.scan_ticker_stream_with_strategies(ticker, all_strategies))

    def scan_ticker_stream_with_strategies(
        self,
        ticker: str,
        all_strategies: Dict[str, Any]
    ) -> Iterator[Opportunity]:
        """نسخه جریانی با استراتژی‌های ورودی"""
        yield from self._scan_with_strategies(ticker, all_strategies)

    # ============================================================
    # CORE SCANNING LOGIC
    # ============================================================

    def _scan_with_strategies(
        self,
        ticker: str,
        all_strategies: Dict[str, Any]
    ) -> Iterator[Opportunity]:
        """
        پیاده‌سازی مشترک اسکن — خروجی جریانی با استفاده از ContractIndex
        """
        # ۱. دریافت دارایی پایه
        underlying = self.snapshot.get_underlying(ticker)
        if not underlying or getattr(underlying, 'is_frozen', False):
            return

        # ۲. دریافت قراردادها
        contracts = self.snapshot.get_options(ticker)
        if not contracts or len(contracts) < 2:
            return

        logger.info(f"Scanning {ticker}: {len(contracts)} contracts")

        # ۳. ساخت ایندکس (با کش) و محاسبه نقدشوندگی
        contract_index = self._build_index(contracts)
        self._contract_scores = self._calculate_liquidity_scores(contracts)

        # ۴. اسکن با استراتژی‌ها
        get_generator_func = get_generator
        get_stats_attr = getattr

        for strategy_name, strategy_def in all_strategies.items():
            try:
                generator = get_generator_func(strategy_def)
                if generator is None:
                    continue

                # ✅ امضای جدید با index
                opps_iterator = generator.generate(
                    underlying=underlying,
                    index=contract_index,
                    contract_scores=self._contract_scores
                )

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
    # LIQUIDITY SCORING
    # ============================================================

    def _calculate_liquidity_scores(self, contracts: List[OptionContract]) -> Dict[str, float]:
        """
        محاسبه امتیاز نقدشوندگی (پیش‌پردازش یک‌باره).
        ✅ استفاده از get_attr برای کاهش Attribute Lookup
        """
        scores = {}
        get_attr = getattr

        for contract in contracts:
            volume_score = min(contract.volume / MIN_VOLUME,
                               1.0) * 30 if MIN_VOLUME > 0 else 0
            oi_score = min(contract.open_interest / 50, 1.0) * 25

            if contract.bid > 0 and contract.ask > 0:
                mid = (contract.bid + contract.ask) / 2
                spread_score = max(
                    0, (1.0 - ((contract.ask - contract.bid) / mid) / 0.05)) * 25 if mid > 0 else 0
            else:
                spread_score = 0

            bid_vol = get_attr(contract, 'bid_volume', 0) or 0
            ask_vol = get_attr(contract, 'ask_volume', 0) or 0
            depth_score = min(min(bid_vol, ask_vol) / 500, 1.0) * 20

            scores[contract.ticker] = round(
                volume_score + oi_score + spread_score + depth_score, 2
            )

        return scores

    # ============================================================
    # STATS & TELEMETRY
    # ============================================================

    def get_stats(self) -> Dict[str, int]:
        """ارائه آمارهای تجمیعی"""
        return {
            "generated": self._generated_count,
            "filtered": self._filtered_count
        }

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
