# engine/scanner.py
# -*- coding: utf-8 -*-

"""
موتور اسکن لایه نماد (Scanner) - معماری V4

این ماژول وظیفه دریافت قراردادهای یک نماد پایه، محاسبه ماتریس نقدشوندگی (Liquidity Core) 
و هدایت داده‌ها به سمت ژنراتورهای تخصصی استراتژی را بر عهده دارد.
اصلاحات V4: سازگاری کامل با سیستم آماری تجمعی ScannerEngine و ایمن‌سازی محاسبات ریاضی اسپرد.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Any

from config import MIN_VOLUME
from core.models import MarketSnapshot, Opportunity, OptionContract
from strategies.core import get_all_strategies
from strategies.generators import get_generator

logger = logging.getLogger("OptionScanner.Engine.TickerScanner")


class Scanner:
    """
    موتور اسکن متمرکز روی یک نماد پایه و استخراج تمام ترکیب‌های مجاز آن
    """
    
    def __init__(self, snapshot: MarketSnapshot):
        self.snapshot = snapshot
        self._contract_scores: Dict[str, float] = {}
        
        # شمارنده‌های تجمعی سطح اسکنر برای همگام‌سازی با انجین موازی (V4)
        self._generated_count = 0
        self._filtered_count = 0
    
    def scan_ticker(self, ticker: str) -> List[Opportunity]:
        """
        اسکن کامل زنجیره آپشن یک نماد پایه برای تمام استراتژی‌های فعال سیستم
        """
        opportunities: List[Opportunity] = []
        
        # 1. دریافت دارایی پایه
        underlying = self.snapshot.get_underlying(ticker)
        if not underlying:
            logger.debug(f"Ticker {ticker} not found in snapshot")
            return []
        
        if getattr(underlying, 'is_frozen', False):
            logger.debug(f"Skipping ticker {ticker}: Asset is frozen")
            return []
        
        # 2. دریافت قراردادها با استفاده از کش مرجع (O(1))
        contracts = self.snapshot.get_options(ticker)
        if not contracts or len(contracts) < 2:
            logger.debug(f"No valid contracts for {ticker}")
            return []
        
        logger.info(f"Scanning {ticker}: {len(contracts)} contracts")
        
        # 3. پیش‌محاسبه امتیاز نقدشوندگی زنجیره
        self._contract_scores = self._calculate_liquidity_scores(contracts)
        
        # 4. دریافت همه استراتژی‌های فعال دایره ران‌تایم
        all_strategies = get_all_strategies()

        if underlying.ticker =='اهرم':
            pass
        
        for strategy_name, strategy_def in all_strategies.items():
            try:
                # 5. دریافت Generator تخصصی معادل استراتژی
                generator = get_generator(strategy_def)
                if generator is None:
                    logger.debug(f"No generator for {strategy_name}")
                    continue

                if strategy_name =='covered_call':
                    pass
                
                # 6. تولید ترکیب‌ها با ساختار امتیازدهی
                generated_opps = generator.generate(
                    underlying=underlying,
                    contracts=contracts,
                    contract_scores=self._contract_scores
                )
                
                # استخراج و انباشت آمارهای فیلترینگ داخلی ژنراتور (V4)
                if hasattr(generator, 'get_stats'):
                    gen_stats = generator.get_stats()
                    self._generated_count += gen_stats.get("generated", len(generated_opps) if generated_opps else 0)
                    self._filtered_count += gen_stats.get("filtered", 0)
                else:
                    self._generated_count += len(generated_opps) if generated_opps else 0
                
                if generated_opps:
                    opportunities.extend(generated_opps)
                    logger.debug(f"  {strategy_name}: {len(generated_opps)} opportunities")
                    
            except Exception as e:
                logger.error(f"Error generating {strategy_name} on {ticker}: {e}")
        
        logger.info(f"Generated {len(opportunities)} opportunities for {ticker}")
        return opportunities
    
    def _calculate_liquidity_scores(self, contracts: List[OptionContract]) -> Dict[str, float]:
        """محاسبه ماتریس نقدشوندگی قراردادها با مکانیزم حفاظت از کرش محاسباتی"""
        scores = {}
        
        for contract in contracts:
            # حجم (بازه وزنی 0-30)
            volume_score = min(contract.volume / MIN_VOLUME, 1.0) * 30 if MIN_VOLUME > 0 else 0
            
            # موقعیت‌های باز تعهدی - Open Interest (بازه وزنی 0-25)
            oi_score = min(contract.open_interest / 50, 1.0) * 25
            
            # اسپرد قیمت پیشنهادی خرید و فروش (بازه وزنی 0-25) - ایمن‌سازی در برابر ZeroDivision
            if contract.bid > 0 and contract.ask > 0:
                mid = (contract.bid + contract.ask) / 2
                if mid > 0:
                    spread_pct = (contract.ask - contract.bid) / mid
                    spread_score = max(0, (1.0 - spread_pct / 0.05)) * 25
                else:
                    spread_score = 0
            else:
                spread_score = 0
            
            # عمق دفاتر سفارشات - Order Book Depth (بازه وزنی 0-20)
            bid_vol = getattr(contract, 'bid_volume', 0) or 0
            ask_vol = getattr(contract, 'ask_volume', 0) or 0
            depth = min(bid_vol, ask_vol)
            depth_score = min(depth / 500, 1.0) * 20
            
            scores[contract.ticker] = round(volume_score + oi_score + spread_score + depth_score, 2)
        
        return scores

    def get_stats(self) -> Dict[str, int]:
        """ارائه آمارهای تجمیعی به موتور ارکستراتور بالادستی (ScannerEngine)"""
        return {
            "generated": self._generated_count,
            "filtered": self._filtered_count
        }
    
    def scan_all_tickers(self) -> List[Opportunity]:
        """اسکن ترتیبی پشتیبان برای تمام نمادهای موجود در مارکت اسنپ‌شات"""
        all_opportunities = []
        for ticker in self.snapshot.underlying_assets.keys():
            opportunities = self.scan_ticker(ticker)
            all_opportunities.extend(opportunities)
        return all_opportunities