# engine/scanner.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import logging
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import numpy as np

import config
from core.models import MarketSnapshot, ScanResult, Opportunity, OptionContract, UnderlyingAsset, LegDefinition
from core.enums import Side, OptionType
from strategies.core import get_all_strategies
from strategies.generators import get_generator
from analytics.payoff_calculator import IranMarketPayoffCalculator
from analytics.margin_calculator import MarginCalculator
from analytics.probabilities_calculator import calculate_strategy_greeks
from scoring.liquidity_score import LiquidityScorer
from strategies.matching.contract_index import ContractIndex

logger = logging.getLogger("OptionScanner.Engine.Scanner")


# ============================================================
# بخش ۱: ساخت فرصت (Opportunity Builder)
# ============================================================

class OpportunityBuilder:
    """ساخت Opportunity از کانتراکت‌های تطبیق‌شده"""

    @staticmethod
    def build(
        strategy_def: Any,
        underlying: UnderlyingAsset,
        matched_contracts: List[OptionContract],
        contract_scores: Dict[str, float],
        spot_price: float,
    ) -> Optional[Opportunity]:
        """ساخت فرصت معاملاتی از کانتراکت‌های تطبیق‌شده"""
        patterns = strategy_def.patterns
        if not matched_contracts or len(matched_contracts) != len(patterns):
            return None

        # ── ساخت LegDefinitions ──────────────────────────────────────────
        legs: List[LegDefinition] = []
        days_to_maturity = 0

        for contract, pattern in zip(matched_contracts, patterns):
            if contract.option_type == OptionType.STOCK:
                ep = contract.last_price or spot_price
            elif pattern.side == Side.BUY:
                ep = contract.ask if contract.ask > 0 else contract.last_price
            else:
                ep = contract.bid if contract.bid > 0 else contract.last_price

            legs.append(LegDefinition(
                side=pattern.side,
                ratio=pattern.ratio,
                contract=contract,
                entry_price=ep,
            ))

            if days_to_maturity == 0 and contract.option_type != OptionType.STOCK:
                days_to_maturity = contract.days_to_maturity

        # ── محاسبات مارجین ───────────────────────────────────────────────
        try:
            margin_result = MarginCalculator.calculate_strategy_margin(
                legs=legs,
                underlying_price=spot_price,
                underlying_symbol=underlying.ticker
            )
            required_margin = margin_result.required_margin if margin_result else 0.0
        except Exception:
            required_margin = 0.0

        # ── محاسبات P&L ──────────────────────────────────────────────────
        price_levels = np.array([], dtype=float)
        try:
            price_levels = config.get_price_levels(spot_price)
            payoff = IranMarketPayoffCalculator.calculate_payoff(
                legs=legs,
                spot_price=spot_price,
                price_levels=price_levels,
                required_margin=required_margin,
            )
            returns_pct = payoff.returns_pct
            max_profit = payoff.max_profit or 0.0
            max_loss = payoff.max_loss or 0.0
            break_even = payoff.break_even_points or []
            net_premium = payoff.net_premium or 0.0
        except Exception as e:
            logger.error(f"Payoff calculation failed: {e}")
            returns_pct = np.array([], dtype=float)
            max_profit = 0.0
            max_loss = 0.0
            break_even = []
            net_premium = 0.0

        # ── امتیازدهی ──────────────────────────────────────────────────────
        liquidity_score = LiquidityScorer.score_strategy(legs, contract_scores)
        execution_score = LiquidityScorer.calculate_execution_score(legs)

        # ── متادیتا ──────────────────────────────────────────────────────
        metadata = OpportunityBuilder._leg_metadata(legs, contract_scores)
        metadata['price_levels'] = price_levels.tolist() if len(
            price_levels) > 0 else []

        return Opportunity(
            strategy_name=strategy_def.name,
            underlying_ticker=underlying.ticker,
            legs=legs,
            S0_stock=spot_price,
            days_to_maturity=days_to_maturity,
            net_premium=net_premium,
            required_margin=required_margin,
            liquidity_score=liquidity_score,
            execution_score=execution_score,
            metadata=metadata,
            returns_monthly_pct=returns_pct,
            max_profit=max_profit,
            max_loss=max_loss,
            break_even_points=break_even,
            timestamp=datetime.now(),
        )

    @staticmethod
    def _leg_metadata(legs: List[LegDefinition], contract_scores: Dict[str, float]) -> Dict[str, Any]:
        metadata = {}
        for idx, leg in enumerate(legs, start=1):
            if not leg.contract:
                continue
            c = leg.contract
            metadata[f"l{idx}_ticker"] = c.ticker
            metadata[f"l{idx}_strike"] = c.strike_price
            metadata[f"l{idx}_option_type"] = c.option_type.value
            metadata[f"l{idx}_score"] = contract_scores.get(c.ticker, 0.0)
        return metadata


# ============================================================
# بخش ۲: تزریق یونانی‌ها
# ============================================================

def _inject_greeks(opp: Opportunity, spot_price: float) -> None:
    """محاسبه و تزریق یونانی‌ها به metadata"""
    from core.enums import OptionType as OT, Side as SD
    from config import RISK_FREE_RATE, DEFAULT_VOLATILITY

    if not opp.legs or spot_price <= 0:
        return

    legs_for_greeks = []
    total_iv = 0.0
    valid_count = 0

    for leg in opp.legs:
        contract = leg.contract
        if not contract or contract.option_type == OT.STOCK:
            continue

        iv = getattr(contract, 'iv', None) or getattr(
            contract, 'implied_volatility', None) or DEFAULT_VOLATILITY
        iv_float = float(iv) if iv and iv > 0 else DEFAULT_VOLATILITY

        total_iv += iv_float
        valid_count += 1

        legs_for_greeks.append({
            'option_type': 'call' if contract.option_type == OT.CALL else 'put',
            'strike_price': contract.strike_price,
            'position': (1 if leg.side == SD.BUY else -1) * leg.ratio,
            'iv': iv_float
        })

    if not legs_for_greeks:
        return

    avg_iv = total_iv / valid_count if valid_count > 0 else DEFAULT_VOLATILITY

    result = calculate_strategy_greeks(
        legs=legs_for_greeks,
        current_price=spot_price,
        days_to_maturity=opp.days_to_maturity or 30,
        risk_free_rate=RISK_FREE_RATE,
        volatility=avg_iv,
    )

    opp.metadata.update({
        'delta': result.get('delta', 0.0),
        'gamma': result.get('gamma', 0.0),
        'theta': result.get('theta_daily', 0.0),
        'vega': result.get('vega', 0.0),
        'rho': result.get('rho', 0.0),
    })


# ============================================================
# بخش ۳: اسکنر بازار
# ============================================================

class MarketScanner:
    """موتور یکپارچه اسکن بازار و ساخت Opportunities"""

    def __init__(self, snapshot: MarketSnapshot, parallel: bool = True, max_workers: int = 4):
        self.snapshot = snapshot
        self.parallel = parallel
        self.max_workers = max_workers
        self._lock = Lock()
        self._stats = {"scanned": 0, "errors": 0}

    def scan_market(self) -> ScanResult:
        """اسکن کامل بازار"""
        start_time = time.time()
        tickers = list(self.snapshot.underlying_assets.keys())
        all_strategies = get_all_strategies()

        if self.parallel and len(tickers) > 1:
            opportunities = self._scan_parallel(tickers, all_strategies)
        else:
            opportunities = self._scan_sequential(tickers, all_strategies)

        return self._create_result(opportunities, start_time)

    def _scan_sequential(self, tickers: List[str], strategies: Dict) -> List[Opportunity]:
        all_opps = []
        for ticker in tickers:
            opps = list(self._scan_ticker(ticker, strategies))
            if opps:
                all_opps.extend(opps)
        return all_opps

    def _scan_parallel(self, tickers: List[str], strategies: Dict) -> List[Opportunity]:
        all_opps = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(
                self._scan_ticker, ticker, strategies): ticker for ticker in tickers}
            for future in as_completed(futures):
                try:
                    opps = future.result()
                    if opps:
                        all_opps.extend(opps)
                except Exception as e:
                    logger.error(f"Parallel scan error: {e}")
        return all_opps

    def _scan_ticker(self, ticker: str, strategies: Dict) -> List[Opportunity]:
        """اسکن یک نماد"""
        try:
            underlying = self.snapshot.get_underlying_assets(ticker)
            if not underlying or getattr(underlying, 'is_frozen', False):
                return []

            contracts = self.snapshot.get_options_by_underlying(ticker)
            if not contracts or len(contracts) < 2:
                return []

            spot_price = getattr(underlying, 'last_price', 0.0)
            if spot_price <= 0:
                return []

            # پیش‌محاسبه نقدشوندگی
            contract_scores = LiquidityScorer.pre_score_contracts(contracts)

            # فیلتر اولیه
            min_liq = config.get_feature_flags().get("min_liquidity_threshold")
            liquid_contracts = [
                c for c in contracts
                if contract_scores.get(c.ticker, 0.0) >= min_liq]

            if not liquid_contracts:
                return []

            logger.info(
                f"Scanning {ticker}: {len(liquid_contracts)} liquid contracts")

            enriched = []
            index = ContractIndex(liquid_contracts)

            for strategy_name, strategy_def in strategies.items():
                generator = get_generator(strategy_def)
                if generator is None:
                    continue

                try:
                    for matched_contracts in generator.generate(
                        underlying, index, contract_scores
                    ):
                        opp = OpportunityBuilder.build(
                            strategy_def=strategy_def,
                            underlying=underlying,
                            matched_contracts=matched_contracts,
                            contract_scores=contract_scores,
                            spot_price=spot_price,
                        )
                        if opp is not None:
                            # تزریق یونانی‌ها
                            if config.get_feature_flags().get("calculate_greeks", True):
                                _inject_greeks(opp, spot_price)
                            enriched.append(opp)
                except Exception as e:
                    logger.error(f"Error in {strategy_name}: {e}")

            with self._lock:
                self._stats["scanned"] += 1

            return enriched

        except Exception as e:
            with self._lock:
                self._stats["errors"] += 1
            logger.error(f"Error scanning {ticker}: {e}")
            return []

    def _create_result(self, opportunities: List[Opportunity], start_time: float) -> ScanResult:
        duration = (time.time() - start_time) * 1000
        return ScanResult(
            timestamp=datetime.now(),
            total_strategies_scanned=self._stats["scanned"],
            opportunities=opportunities,
            execution_time_ms=duration
        )


# ============================================================
# API سطح بالا
# ============================================================

def scan_market(snapshot: MarketSnapshot, parallel: bool = True, max_workers: int = 4) -> ScanResult:
    """API ساده برای اسکن بازار"""
    scanner = MarketScanner(snapshot, parallel=parallel,
                            max_workers=max_workers)
    return scanner.scan_market()
