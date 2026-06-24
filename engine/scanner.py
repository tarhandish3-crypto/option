# engine/scanner.py

from __future__ import annotations

import logging
from typing import List

from config import MIN_VOLUME
from core.models import (
    MarketSnapshot,
    Opportunity,
    OptionContract,)

from strategies.core import get_all_strategies
from strategies.generators import get_generator

logger = logging.getLogger("OptionScanner.Engine.TickerScanner")


class Scanner:
    """
    موتور اسکن متمرکز روی یک نماد پایه و استخراج تمام ترکیب‌های مجاز آن
    """
    
    def __init__(self, snapshot: MarketSnapshot):
        self.snapshot = snapshot
        self._contract_scores = {}
    
    def scan_ticker(self, ticker: str) -> List[Opportunity]:
        """
        اسکن کامل زنجیره آپشن یک نماد پایه برای تمام استراتژی‌های فعال سیستم
        
        Args:
            ticker: نماد پایه (مثل "فولاد", "خودرو")
            
        Returns:
            لیست فرصت‌های معاملاتی
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
        
        # 2. دریافت قراردادها با استفاده از کش (O(1))
        contracts = self.snapshot.get_options(ticker)
        if not contracts or len(contracts) < 2:
            logger.debug(f"No valid contracts for {ticker}")
            return []
        
        logger.info(f"Scanning {ticker}: {len(contracts)} contracts")
        
        # 3. پیش‌محاسبه امتیاز نقدشوندگی
        self._contract_scores = self._calculate_liquidity_scores(contracts)
        
        # 4. دریافت همه استراتژی‌های فعال
        all_strategies = get_all_strategies()
        
        if underlying.ticker =='اهرم':
            pass
        for strategy_name, strategy_def in all_strategies.items():
            try:
                # 5. دریافت Generator مناسب
                generator = get_generator(strategy_def)
                if generator is None:
                    logger.debug(f"No generator for {strategy_name}")
                    continue
                
                if strategy_name =='covered_call':
                    pass
                # 6. تولید ترکیب‌ها
                generated_opps = generator.generate(
                    underlying=underlying,
                    contracts=contracts,
                    contract_scores=self._contract_scores)
                
                if generated_opps:
                    opportunities.extend(generated_opps)
                    logger.debug(f"  {strategy_name}: {len(generated_opps)} opportunities")
                    
            except Exception as e:
                logger.error(f"Error generating {strategy_name} on {ticker}: {e}")
        
        logger.info(f"Generated {len(opportunities)} opportunities for {ticker}")
        return opportunities
    
    def _calculate_liquidity_scores(self, contracts: List[OptionContract]) -> dict:
        """محاسبه امتیاز نقدشوندگی قراردادها"""
        scores = {}
        
        for contract in contracts:
            # حجم (0-30)
            volume_score = min(contract.volume / MIN_VOLUME, 1.0) * 30
            
            # Open Interest (0-25)
            oi_score = min(contract.open_interest / 50, 1.0) * 25
            
            # اسپرد (0-25)
            if contract.bid > 0 and contract.ask > 0:
                mid = (contract.bid + contract.ask) / 2
                spread_pct = (contract.ask - contract.bid) / mid
                spread_score = max(0, (1.0 - spread_pct / 0.05)) * 25
            else:
                spread_score = 0
            
            # عمق (0-20)
            depth = min(contract.bid_volume, contract.ask_volume) if contract.bid_volume and contract.ask_volume else 0
            depth_score = min(depth / 500, 1.0) * 20
            
            scores[contract.ticker] = round(volume_score + oi_score + spread_score + depth_score, 2)
        
        return scores
    
    def scan_all_tickers(self) -> List[Opportunity]:
        """اسکن همه نمادهای موجود در snapshot"""
        all_opportunities = []
        
        for ticker in self.snapshot.underlying_assets.keys():
            opportunities = self.scan_ticker(ticker)
            all_opportunities.extend(opportunities)
        
        return all_opportunities