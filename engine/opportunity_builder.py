# engine/opportunity_builder.py
# -*- coding: utf-8 -*-

"""
OpportunityBuilder — هماهنگ‌کننده و کارخانه واحد ساخت شیء Opportunity.
کد کاملاً بازنویسی شده و فاقد هرگونه محاسبات فرعی، مارجین یا اسکورینگ داخلی است.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
import numpy as np

from core.models import Opportunity, LegDefinition, OptionContract, UnderlyingAsset
from core.enums import Side, OptionType
from scoring.liquidity_score import LiquidityScorer
from analytics.margin_calculator import MarginCalculator
from analytics.payoff_calculator import IranMarketPayoffCalculator
import config

logger = logging.getLogger("OptionScanner.Engine.OpportunityBuilder")


class OpportunityBuilder:
    """
    کارخانه واحد ساخت Opportunity از contracts خام + strategy patterns.
    دارای صفر منطق محاسباتی داخلی (تزریق کامل وظایف به ماژول‌های تخصصی analytics).
    """

    @staticmethod
    def build_opportunity(
            strategy_def: Any,
            underlying: UnderlyingAsset,
            matched_contracts: List[OptionContract],
            contract_scores: Dict[str, float],
            underlying_price: Optional[float] = None) -> Optional[Opportunity]:

        patterns = strategy_def.patterns
        if not matched_contracts or len(matched_contracts) != len(patterns):
            logger.debug(
                f"build_opportunity: mismatch contracts={len(matched_contracts)} "
                f"patterns={len(patterns)} for {strategy_def.name}")
            return None

        spot = underlying_price
        if spot is None or spot <= 0:
            spot = underlying.last_price if underlying.last_price > 0 else underlying.close_price

        # ── ۱. ساخت ساختار پایه LegDefinitions (تنها وظیفه ساختاری بیلدر) ─────────────────
        legs: List[LegDefinition] = []
        days_to_maturity = 0

        for contract, pattern in zip(matched_contracts, patterns):
            if contract.option_type == OptionType.STOCK:
                ep = contract.last_price or spot
            elif pattern.side == Side.BUY:
                ep = contract.ask if contract.ask > 0 else contract.last_price
            else:
                ep = contract.bid if contract.bid > 0 else contract.last_price

            legs.append(LegDefinition(
                side=pattern.side,
                ratio=pattern.ratio,
                contract=contract,
                entry_price=ep, ))

            if contract.option_type != OptionType.STOCK:
                days_to_maturity = contract.days_to_maturity

        metadata = OpportunityBuilder._build_leg_metadata(legs, contract_scores)

        # ── ۲. واگذاری مطلق محاسبات مارجین به ماژول تخصصی ─────────────────────────
        required_margin = 0.0
        flags = config.get_feature_flags()
        if flags.get("calculate_margin"):
            try:
                valid_legs = [leg for leg in legs if leg.contract is not None]
                if valid_legs:
                    margin_result = MarginCalculator.calculate_strategy_margin(
                        legs=valid_legs,
                        underlying_price=spot,
                        underlying_symbol=underlying.ticker,)
                    required_margin = float(margin_result.required_margin) if hasattr(margin_result, 'required_margin') else float(margin_result or 0.0)
            except Exception as e:
                logger.debug(f"Margin calculation failed via MarginCalculator: {e}")

        # ── ۳. واگذاری نمره‌دهی نقدشوندگی و اجرا به ماژول تخصصی scoring ──────────────────
        liquidity_score = LiquidityScorer.score_strategy(legs, contract_scores)
        execution_score = LiquidityScorer.execution_score(legs)

        # ── ۴. واگذاری مطلق محاسبات P&L و سود ماهانه به ماژول تخصصی ───────────────
        try:
            price_levels = config.get_price_levels(spot)

            payoff = IranMarketPayoffCalculator.calculate_payoff(
                legs=legs, 
                spot_price=spot,
                price_levels=price_levels,
                required_margin=required_margin,
                days_to_maturity=days_to_maturity)

            returns_pct = payoff.returns_pct
            max_profit = payoff.max_profit if payoff.max_profit is not None else 0.0
            max_loss = payoff.max_loss if payoff.max_loss is not None else 0.0
            break_even = payoff.break_even_points
            total_premium = payoff.net_premium  
            metadata['price_levels'] = price_levels
            
        except Exception as e:
            logger.error(f"Payoff calculation failed via PayoffCalculator for {strategy_def.name}: {e}")
            returns_pct = np.array([], dtype=float)
            max_profit, max_loss, total_premium = 0.0, 0.0, 0.0
            break_even = []
            metadata['price_levels'] = []

        # ── ۵. ساخت خروجی نهایی ───────────────────────────────────────────────────
        return Opportunity(
            strategy_name=strategy_def.name,
            underlying_ticker=underlying.ticker,
            legs=legs,
            S0_stock=spot,
            days_to_maturity=days_to_maturity,
            net_premium=total_premium,
            required_margin=required_margin,
            liquidity_score=liquidity_score,
            execution_score=execution_score,
            metadata=metadata,
            returns_monthly_pct=returns_pct,
            max_profit=max_profit,
            max_loss=max_loss,
            break_even_points=break_even,
            timestamp=datetime.now(), )

    # ──────────────────────────────────────────────────────────────────────
    # متد اصلاح‌شده سازگاری با FourLegGenerator (بدون توابع کمکی منسوخ شده)
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def create_opportunity(
            strategy_name: str,
            ticker: str,
            legs: List[LegDefinition],
            days_to_maturity: int,
            metrics: Optional[Dict[str, Any]] = None,
            underlying_price: float = 0.0,
            break_even_points: Optional[List[float]] = None, ) -> Optional[Opportunity]:
        """Legacy — اصلاح‌شده بر پایه Single Source of Truth جهت تامین نیازمندی ژنراتورها"""
        metadata = metrics or {}
        spot = underlying_price

        # محاسبات مارجین از طریق ماژول تخصصی مرجع
        required_margin = 0.0
        try:
            valid_legs = [leg for leg in legs if leg.contract is not None]
            if valid_legs and spot > 0:
                margin_result = MarginCalculator.calculate_strategy_margin(
                    legs=valid_legs, underlying_price=spot, underlying_symbol=ticker)
                required_margin = float(margin_result.required_margin) if hasattr(margin_result, 'required_margin') else float(margin_result or 0.0)
        except Exception as e:
            logger.debug(f"Legacy create_opportunity margin failed: {e}")

        # ارجاع محاسبات پی‌آف و پرمیوم به مرجع تخصصی برداری بورس ایران
        try:
            price_levels = config.get_price_levels(spot)
            payoff = IranMarketPayoffCalculator.calculate_payoff(
                legs=legs, spot_price=spot,
                price_levels=price_levels,
                required_margin=required_margin)
            
            total_premium = payoff.net_premium
            returns_pct = payoff.returns_pct
            derived_break_even = payoff.break_even_points
        except Exception:
            total_premium = 0.0
            returns_pct = np.array([], dtype=float)
            derived_break_even = []

        # امتیازدهی نقدشوندگی استاندارد بدون متدهای لوکال منسوخ‌شده
        liquidity_score = LiquidityScorer.score_strategy(legs, {})

        if break_even_points is None:
            break_even_points = derived_break_even if derived_break_even else metadata.get("break_even_points", [])

        return Opportunity(
            strategy_name=strategy_name,
            underlying_ticker=ticker,
            legs=legs,
            days_to_maturity=days_to_maturity,
            timestamp=datetime.now(),
            required_margin=required_margin,
            net_premium=total_premium,
            max_profit=metadata.get("max_profit", float(np.max(returns_pct)) if len(returns_pct) > 0 else 0.0),
            max_loss=metadata.get("max_loss", float(np.min(returns_pct)) if len(returns_pct) > 0 else 0.0),
            pop=metadata.get("pop", 0.0),
            risk_reward_ratio=metadata.get("risk_reward_ratio", 0.0),
            expected_return_pct=metadata.get("expected_return_pct", 0.0),
            liquidity_score=liquidity_score,
            metadata=metadata,
            returns_monthly_pct=returns_pct,
            break_even_points=break_even_points,
            final_score=0.0,
            rank=0, )

    @staticmethod
    def _build_leg_metadata(legs: List[LegDefinition], contract_scores: Dict[str, float]) -> Dict[str, Any]:
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