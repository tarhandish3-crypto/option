# engine/opportunity_builder.py
# -*- coding: utf-8 -*-

"""
OpportunityBuilder — تنها منبع ساخت LegDefinition‌ها و شیء Opportunity.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from core.models import Opportunity, LegDefinition, OptionContract, UnderlyingAsset
from core.enums import Side, OptionType
from scoring.liquidity_score import LiquidityScorer
from analytics.margin_calculator import MarginCalculator, MarginResult
import config

logger = logging.getLogger("OptionScanner.Engine.OpportunityBuilder")


class OpportunityBuilder:
    """
    کارخانه واحد ساخت Opportunity از contracts خام + strategy patterns.
    هیچ لگی در جای دیگری ساخته نمی‌شود.
    """

    @staticmethod
    def build_opportunity(
        strategy_def: Any,
        underlying: UnderlyingAsset,
        matched_contracts: List[OptionContract],
        contract_scores: Dict[str, float],
        underlying_price: Optional[float] = None,) -> Optional[Opportunity]:
        """
        متد واحد ساخت Opportunity.

        پارامترها:
        - strategy_def:      تعریف استراتژی (شامل patterns با Side، ratio)
        - underlying:        دارایی پایه
        - matched_contracts: لیست OptionContract خام از PatternMatcher
                             (یک به ازای هر pattern، به همان ترتیب)
        - contract_scores:   امتیاز نقدشوندگی کانتراکت‌ها
        - underlying_price:  قیمت پایه (اگر None، از underlying گرفته می‌شود)

        خروجی:
        - Opportunity با legs منسجم، بدون هیچ تکراری
        """
        patterns = strategy_def.patterns
        if not matched_contracts or len(matched_contracts) != len(patterns):
            logger.debug(
                f"build_opportunity: mismatch contracts={len(matched_contracts)} "
                f"patterns={len(patterns)} for {strategy_def.name}"
            )
            return None

        spot = underlying_price
        if spot is None or spot <= 0:
            spot = underlying.last_price if underlying.last_price > 0 else underlying.close_price

        # ── ساخت LegDefinitions — تنها منبع ──────────────────────────────
        legs: List[LegDefinition] = []
        days_to_maturity = 0

        for contract, pattern in zip(matched_contracts, patterns):
            # محاسبه entry_price بر اساس جهت معامله
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
                entry_price=ep,
            ))

            # DTE از اولین لگ آپشن واقعی
            if days_to_maturity == 0 and contract.option_type != OptionType.STOCK:
                days_to_maturity = contract.days_to_maturity

        # ── محاسبات مالی ─────────────────────────────────────────────────
        total_premium = OpportunityBuilder._calculate_total_premium(legs)

        try:
            margin_result = OpportunityBuilder._calculate_required_margin(
                legs, spot, underlying.ticker
            )
            if margin_result is None:
                required_margin = 0.0
            elif hasattr(margin_result, 'required_margin'):
                required_margin = float(margin_result.required_margin)
            else:
                required_margin = float(margin_result)
        except Exception as e:
            logger.debug(f"Margin calculation failed for {strategy_def.name}: {e}")
            required_margin = 0.0

        liquidity_score = OpportunityBuilder._calculate_liquidity_score(legs)
        execution_score = OpportunityBuilder._calculate_execution_score(legs)
        metadata = OpportunityBuilder._build_leg_metadata(legs, contract_scores)

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
            timestamp=datetime.now(),)

    # ──────────────────────────────────────────────────────────────────────
    # متد legacy برای سازگاری با FourLegGenerator (create_opportunity)
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def create_opportunity(
        strategy_name: str,
        ticker: str,
        legs: List[LegDefinition],
        days_to_maturity: int,
        metrics: Optional[Dict[str, Any]] = None,
        underlying_price: float = 0.0,
        break_even_points: Optional[List[float]] = None,) -> Optional[Opportunity]:
        """Legacy — فقط توسط FourLegGenerator استفاده می‌شود. در آینده حذف خواهد شد."""
        metadata = metrics or {}
        total_premium = OpportunityBuilder._calculate_total_premium(legs)

        margin_result = OpportunityBuilder._calculate_required_margin(legs, underlying_price)
        if margin_result is None:
            required_margin = 0.0
        elif hasattr(margin_result, 'required_margin'):
            required_margin = float(margin_result.required_margin)
        else:
            required_margin = float(margin_result)

        liquidity_score = OpportunityBuilder._calculate_liquidity_score(legs)
        execution_score = OpportunityBuilder._calculate_execution_score(legs)

        if break_even_points is None:
            break_even_points = metadata.get("break_even_points", [])

        return Opportunity(
            strategy_name=strategy_name,
            underlying_ticker=ticker,
            legs=legs,
            days_to_maturity=days_to_maturity,
            timestamp=datetime.now(),
            required_margin=required_margin,
            net_premium=total_premium,
            max_profit=metadata.get("max_profit", 0.0),
            max_loss=metadata.get("max_loss", 0.0),
            pop=metadata.get("pop", 0.0),
            risk_reward_ratio=metadata.get("risk_reward_ratio", 0.0),
            expected_return_pct=metadata.get("expected_return_pct", 0.0),
            liquidity_score=liquidity_score,
            execution_score=execution_score,
            metadata=metadata,
            break_even_points=break_even_points,
            final_score=0.0,
            rank=0,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _calculate_total_premium(legs: List[LegDefinition]) -> float:
        total = 0.0
        for leg in legs:
            contract = leg.contract
            if not contract:
                continue
            size = getattr(contract, "contract_size", 1) or 1
            if contract.option_type == OptionType.STOCK:
                ep = contract.last_price
            elif leg.side == Side.BUY:
                ep = contract.ask if contract.ask > 0 else contract.last_price
            else:
                ep = contract.bid if contract.bid > 0 else contract.last_price
            value = ep * size * leg.ratio
            total += value if leg.side == Side.BUY else -value
        return round(total, 2)

    @staticmethod
    def _calculate_required_margin(
        legs: List[LegDefinition],
        underlying_price: float,
        underlying_symbol: Optional[str] = None,) -> Optional[MarginResult]:
        flags = config.get_feature_flags()
        if not flags.get("calculate_margin", True):
            return None
        try:
            valid_legs = [leg for leg in legs if leg.contract is not None]
            if not valid_legs:
                return None
            return MarginCalculator.calculate_strategy_margin(
                legs=valid_legs,
                underlying_price=underlying_price,
                underlying_symbol=underlying_symbol,
            )
        except Exception as e:
            logger.error(f"Margin calculation error: {e}")
            return None

    @staticmethod
    def _calculate_liquidity_score(legs: List[LegDefinition]) -> float:
        if not legs:
            return 0.0
        scores = []
        for leg in legs:
            c = leg.contract
            if not c:
                continue
            if c.option_type == OptionType.STOCK:
                scores.append(100.0)
            else:
                scores.append(LiquidityScorer.score_single_contract(c))
        if not scores:
            return 0.0
        return round((min(scores) * 0.70) + ((sum(scores) / len(scores)) * 0.30), 2)

    @staticmethod
    def _calculate_execution_score(legs: List[LegDefinition]) -> float:
        if not legs:
            return 0.0
        option_contracts = [
            leg.contract for leg in legs
            if leg.contract and leg.contract.option_type != OptionType.STOCK
        ]
        if not option_contracts:
            return 100.0

        min_volume = min((c.volume for c in option_contracts), default=0)
        min_oi = min((c.open_interest for c in option_contracts), default=0)
        max_spread = 0.0
        for c in option_contracts:
            if c.bid > 0 and c.ask > 0:
                mid = (c.bid + c.ask) / 2
                max_spread = max(max_spread, (c.ask - c.bid) / mid)

        score = 100.0
        if min_volume < 50:
            score -= 30
        elif min_volume < 200:
            score -= 15
        if min_oi < 20:
            score -= 25
        elif min_oi < 100:
            score -= 12
        if max_spread > 0.15:
            score -= 30
        elif max_spread > 0.10:
            score -= 20
        elif max_spread > 0.05:
            score -= 10
        score -= (len(legs) - 1) * 5
        return max(0.0, round(score, 2))

    @staticmethod
    def _build_leg_metadata(
        legs: List[LegDefinition],
        contract_scores: Dict[str, float],) -> Dict[str, Any]:
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
