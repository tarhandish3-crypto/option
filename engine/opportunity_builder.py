# engine/opportunity_builder.py
# -*- coding: utf-8 -*-

"""
OpportunityBuilder — هماهنگ‌کننده و کارخانه واحد ساخت شیء Opportunity.
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
from data.volatility_provider import get_volatility
import config

logger = logging.getLogger("OptionScanner.Engine.OpportunityBuilder")


# ═══════════════════════════════════════════════════════════════
# ثابت‌های محاسباتی
# ═══════════════════════════════════════════════════════════════

_DEFAULT_SIGMA = 0.30      # برای M_risk
_DEFAULT_HV_60 = 0.30
_DEFAULT_VQ = 5.0
_T_DISPLAY_EPSILON = 0.02
_DAYS_IN_YEAR = 365


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

        # پیدا کردن اندازه قرارداد معتبر آپشن‌های موجود در استراتژی جهت نرمال‌سازی سهم پایه
        base_option_size = 1000
        for leg in legs:
            if leg.contract and leg.contract.option_type != OptionType.STOCK:
                if leg.contract.contract_size > 0:
                    base_option_size = leg.contract.contract_size
                    break

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
                    required_margin = float(margin_result.required_margin) if hasattr(
                        margin_result, 'required_margin') else float(margin_result or 0.0)
            except Exception as e:
                logger.debug(
                    f"Margin calculation failed via MarginCalculator: {e}")

        # ── ۳. واگذاری نمره‌دهی نقدشوندگی و اجرا به ماژول تخصصی scoring ──────────────────
        liquidity_score = LiquidityScorer.score_strategy(legs, contract_scores)
        execution_score = LiquidityScorer.execution_score(legs)

        # ── ۴. واگذاری مطلق محاسبات P&L و سود ماهانه به ماژول تخصصی ───────────────
        payoff = None
        returns_pct = np.array([], dtype=float)
        max_profit = 0.0
        max_loss = 0.0
        break_even: List[float] = []
        total_premium = 0.0

        try:
            price_levels = config.get_price_levels(spot)

            payoff = IranMarketPayoffCalculator.calculate_payoff(
                legs=legs,
                spot_price=spot,
                price_levels=price_levels,
                required_margin=required_margin,
                days_to_maturity=days_to_maturity,
                base_option_size=base_option_size)

            returns_pct = payoff.returns_pct
            max_profit = payoff.max_profit if payoff.max_profit is not None else 0.0
            max_loss = payoff.max_loss if payoff.max_loss is not None else 0.0
            break_even = payoff.break_even_points
            total_premium = payoff.net_premium

        except Exception as e:
            logger.error(
                f"Payoff calculation failed via PayoffCalculator for {strategy_def.name}: {e}")

        # ── ۵. استخراج داده‌های VQ از Historical_Volatility.xlsx ──────────────
        vol_data = get_volatility(underlying.ticker)

        hv_60 = float(vol_data.get("HV_60", _DEFAULT_HV_60))
        vq = float(vol_data.get("VolatilityQualityScore", _DEFAULT_VQ))

        # ── ۶. محاسبه‌ی R30، M30، raw_margin، M_risk ────────────────────────
        R30, M30, raw_margin = OpportunityBuilder._calculate_r30_m30(
            payoff=payoff,
            break_even=break_even,
            spot=spot,
            days=days_to_maturity,
        )

        M_risk = OpportunityBuilder._calculate_m_risk(
            raw_margin=raw_margin,
            days=days_to_maturity,
            hv_60=hv_60,
        )

        # ── ۷. ساخت metadata نهایی ──────────────────────────────────────
        metadata: Dict[str, Any] = {
            # ─── داده‌های پایه برای امتیازدهی ───
            "R30": R30,
            "M30": M30,
            "raw_margin_percent": raw_margin,
            "M_risk": M_risk,
            "risk_reward_ratio": 0.0,   # ← بعداً توسط RiskEngine پر می‌شود
            # ─── داده‌های VQ (از Historical_Volatility.xlsx) ───
            "HV_60": hv_60,
            "VQ": vq,
            "LongTrend": vol_data.get("LongTrend", 0.0),
            "Alpha": vol_data.get("Alpha", 0.0),
            "RSI_14": vol_data.get("RSI_14", 50.0),
            "RecoveryStrength": vol_data.get("RecoveryStrength", 0.0),
            "TechnicalDecline": vol_data.get("TechnicalDecline", 0.0),
            "BuyerStrength": vol_data.get("BuyerStrength", 0.0),
            # ─── داده‌های کمکی ───
            "HV_20": vol_data.get("HV_20", 0.30),
            "HV_120": vol_data.get("HV_120", 0.30),
            "RelativeReturn_1Y": vol_data.get("RelativeReturn_1Y", 0.0),
            "SupportProximity": vol_data.get("SupportProximity", 0.0),
            "ResistanceProximity": vol_data.get("ResistanceProximity", 0.0),
        }

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
    # محاسبات کمکی
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _calculate_r30_m30(
            payoff: Any,
            break_even: List[float],
            spot: float,
            days: int,
    ) -> tuple[float, float, float]:
        """
        محاسبه‌ی R30 (سود ماهانه)، M30 (حاشیه امنیت ماهانه)، و raw_margin_percent.

        ⚠️ نکته‌ی مهم: R30 باید از returns_pct (آرایه‌ی بازدهی ماهانه) استخراج شود،
        نه از max_profit (که ریال است و نه درصد).

        Args:
            payoff: خروجی PayoffCalculator
            break_even: لیست نقاط سربه‌سر
            spot: قیمت فعلی سهم پایه
            days: روز تا سررسید

        Returns:
            (R30, M30, raw_margin)
        """
        R30 = 0.0
        M30 = 0.0
        raw_margin = 0.0

        if payoff is None or days <= 0:
            return 0.0, 0.0, 0.0

        # ── R30: از returns_pct (که در payoff_calculator محاسبه شده) ──
        returns_arr = getattr(payoff, 'returns_pct', None)
        if returns_arr is not None and len(returns_arr) > 0:
            try:
                returns_arr = np.asarray(returns_arr, dtype=float)
                positive = returns_arr[returns_arr > 0]
                if len(positive) > 0:
                    R30 = float(np.max(positive))
                else:
                    R30 = float(np.max(returns_arr))
            except (ValueError, TypeError):
                R30 = 0.0

        # ── raw_margin و M30: از نزدیک‌ترین break-even ──
        if break_even and spot > 0:
            try:
                # فاصله‌ی نسبی از spot به نزدیک‌ترین break-even
                distances = []
                for be in break_even:
                    if be is None:
                        continue
                    try:
                        be_val = float(be)
                        distances.append(abs(be_val - spot) / spot)
                    except (ValueError, TypeError):
                        continue

                if distances:
                    raw_margin = min(distances) * 100  # تبدیل به درصد
                    time_factor = (days / 30.0) ** 0.5
                    M30 = raw_margin / time_factor if time_factor > 0 else 0.0
            except Exception as e:
                logger.debug(f"M30 calculation failed: {e}")

        return (
            round(R30, 2),
            round(M30, 2),
            round(raw_margin, 2),
        )

    @staticmethod
    def _calculate_m_risk(
            raw_margin: float,
            days: int,
            hv_60: float,
    ) -> float:
        """
        محاسبه‌ی M_risk (Z-Score).

        فرمول:
            M_risk = (raw_margin / 100) / (sigma × sqrt(T/365))
        """
        if days <= 0:
            return 0.0

        sigma = float(hv_60) if hv_60 and hv_60 > 0 else _DEFAULT_SIGMA
        sigma = max(0.05, min(sigma, 2.0))

        days_safe = max(float(days), _T_DISPLAY_EPSILON)
        raw_fraction = raw_margin / 100.0
        denom = sigma * (days_safe / _DAYS_IN_YEAR) ** 0.5

        if denom <= 0:
            return 0.0

        return round(raw_fraction / denom, 4)

    # ──────────────────────────────────────────────────────────────────────
    # متد اصلاح‌شده سازگاری با FourLegGenerator
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
        metadata = dict(metrics or {})
        spot = underlying_price

        # محاسبات مارجین از طریق ماژول تخصصی مرجع
        required_margin = 0.0
        try:
            valid_legs = [leg for leg in legs if leg.contract is not None]
            if valid_legs and spot > 0:
                margin_result = MarginCalculator.calculate_strategy_margin(
                    legs=valid_legs, underlying_price=spot, underlying_symbol=ticker)
                required_margin = float(margin_result.required_margin) if hasattr(
                    margin_result, 'required_margin') else float(margin_result or 0.0)
        except Exception as e:
            logger.debug(f"Legacy create_opportunity margin failed: {e}")

        # استخراج داینامیک base_option_size برای هماهنگی کامل متد لگاسی با ماژول محاسبات
        base_option_size = 1000
        for leg in legs:
            if leg.contract and leg.contract.option_type != OptionType.STOCK:
                if leg.contract.contract_size > 0:
                    base_option_size = leg.contract.contract_size
                    break

        # ارجاع محاسبات پی‌آف و پرمیوم به مرجع تخصصی برداری
        payoff = None
        total_premium = 0.0
        returns_pct = np.array([], dtype=float)
        derived_break_even = []

        try:
            price_levels = config.get_price_levels(spot)
            payoff = IranMarketPayoffCalculator.calculate_payoff(
                legs=legs,
                spot_price=spot,
                price_levels=price_levels,
                required_margin=required_margin,
                days_to_maturity=days_to_maturity,
                base_option_size=base_option_size)

            total_premium = payoff.net_premium
            returns_pct = payoff.returns_pct
            derived_break_even = payoff.break_even_points
        except Exception as e:
            logger.debug(f"Legacy create_opportunity payoff failed: {e}")

        # امتیازدهی نقدشوندگی
        liquidity_score = LiquidityScorer.score_strategy(legs, {})

        final_be = break_even_points if break_even_points is not None else derived_break_even

        # ── استخراج VQ (نکته‌ی مهم: در متد legacy هم باید VQ تزریق شود) ──
        vol_data = get_volatility(ticker)
        hv_60 = float(vol_data.get("HV_60", _DEFAULT_HV_60))
        vq = float(vol_data.get("VolatilityQualityScore", _DEFAULT_VQ))

        # ── محاسبه‌ی R30، M30، raw_margin، M_risk ──
        R30, M30, raw_margin = OpportunityBuilder._calculate_r30_m30(
            payoff=payoff,
            break_even=final_be,
            spot=spot,
            days=days_to_maturity,
        )

        M_risk = OpportunityBuilder._calculate_m_risk(
            raw_margin=raw_margin,
            days=days_to_maturity,
            hv_60=hv_60,
        )

        # ── تکمیل metadata ──
        metadata.update({
            "R30": R30,
            "M30": M30,
            "raw_margin_percent": raw_margin,
            "M_risk": M_risk,
            "HV_60": hv_60,
            "VQ": vq,
            "LongTrend": vol_data.get("LongTrend", 0.0),
            "Alpha": vol_data.get("Alpha", 0.0),
            "RSI_14": vol_data.get("RSI_14", 50.0),
            "RecoveryStrength": vol_data.get("RecoveryStrength", 0.0),
            "TechnicalDecline": vol_data.get("TechnicalDecline", 0.0),
            "BuyerStrength": vol_data.get("BuyerStrength", 0.0),
        })

        return Opportunity(
            strategy_name=strategy_name,
            underlying_ticker=ticker,
            legs=legs,
            days_to_maturity=days_to_maturity,
            timestamp=datetime.now(),
            required_margin=required_margin,
            net_premium=total_premium,
            max_profit=metadata.get("max_profit", float(
                np.max(returns_pct)) if len(returns_pct) > 0 else 0.0),
            max_loss=metadata.get("max_loss", float(
                np.min(returns_pct)) if len(returns_pct) > 0 else 0.0),
            risk_reward_ratio=metadata.get("risk_reward_ratio", 0.0),
            expected_return_pct=metadata.get("expected_return_pct", 0.0),
            liquidity_score=liquidity_score,
            metadata=metadata,
            returns_monthly_pct=returns_pct,
            break_even_points=final_be,
            final_score=0.0,
            rank=0, )