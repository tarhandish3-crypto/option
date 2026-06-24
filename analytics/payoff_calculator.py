# analytics/payoff_calculator.py
# -*- coding: utf-8 -*-

"""
محاسبه‌گر یکپارچه P&L و سود خالص استراتژی‌های اختیار معامله

"""

from __future__ import annotations

import logging
from typing import Any, List, Optional, Tuple

import numpy as np
from numba import njit

from config import (
    PRICE_RANGE_CONFIG,
    get_price_steps,)
from core.enums import OptionType, Side
from core.models import Opportunity

from analytics.cost_calculator import IranMarketCostCalculator, StrategyCosts

logger = logging.getLogger("OptionScanner.Analytics.PayoffCalculator")


# =====================================================
# بخش ۱: محاسبات سریع برداری با Numba
# =====================================================

@njit(cache=True)
def calc_payoff_numba_full(
    weights: np.ndarray,
    types: np.ndarray,
    strikes: np.ndarray,
    prices: np.ndarray,
    contract_sizes: np.ndarray,
    S0_stock: float,
    price_levels: np.ndarray,
    factor: float
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
    """
    محاسبه سریع سود و زیان ناخالص و نرخ‌های بازدهی برداری

    Returns:
        gross_profits, returns_pct, profits_monthly, returns_monthly_pct, total_capital_engaged
    """
    n_levels = price_levels.shape[0]
    n_assets = weights.shape[0]

    gross_profits = np.zeros(n_levels, dtype=np.float64)
    returns_pct = np.zeros(n_levels, dtype=np.float64)
    profits_monthly = np.zeros(n_levels, dtype=np.float64)
    returns_monthly_pct = np.zeros(n_levels, dtype=np.float64)

    # محاسبه سرمایه واقعی درگیر
    total_capital_engaged = 0.0
    for i in range(n_assets):
        w = weights[i]
        w_adj = w * contract_sizes[i]
        if w > 0:  # Long positions - سرمایه واقعی = پریمیوم پرداختی
            total_capital_engaged += w_adj * prices[i]
        else:  # Short positions - سرمایه تضمینی (مارجین)
            total_capital_engaged += abs(w_adj) * \
                (strikes[i] if strikes[i] > 0 else S0_stock) * 0.2

    if total_capital_engaged <= 1e-5:
        total_capital_engaged = S0_stock if S0_stock > 0 else 10000.0

    for idx_s in range(n_levels):
        S = price_levels[idx_s]
        payoff = 0.0

        for i in range(n_assets):
            w = weights[i]
            if abs(w) < 1e-8:
                continue

            t = types[i]
            K = strikes[i]
            P = prices[i]
            w_adj = w * contract_sizes[i]

            if t == 0:  # سهم پایه
                payoff += w_adj * (S - S0_stock)
            elif t == 1:  # Call
                payoff += w_adj * (max(S - K, 0.0) - P)
            elif t == 2:  # Put
                payoff += w_adj * (max(K - S, 0.0) - P)

        gross_profits[idx_s] = payoff
        returns_pct[idx_s] = (payoff / total_capital_engaged) * 100
        profits_monthly[idx_s] = np.round(payoff * factor, 0)
        returns_monthly_pct[idx_s] = returns_pct[idx_s] * factor

    return (
        np.round(gross_profits, 0),
        np.round(returns_pct, 1),
        profits_monthly,
        np.round(returns_monthly_pct, 1),
        total_capital_engaged,
    )


# =====================================================
# بخش ۲: محاسبه‌گر یکپارچه P&L
# =====================================================

class PayoffCalculator:
    """مدیریت محاسبات برداری سود و زیان نهایی بر پایه خروجی‌های StrategyCosts"""

    @staticmethod
    def calculate_and_enrich(
        opportunity: Opportunity,
        factor: float = 1.0,
        include_clearing: bool = True,
        include_exercise_tax: bool = True,
        profit_threshold: Optional[float] = None
    ) -> Opportunity:
        """
        محاسبه P&L و تزریق مستقیم به شیء Opportunity
        """
        if profit_threshold is None:
            profit_threshold = PRICE_RANGE_CONFIG.get("default_threshold", 3.0)

        # ============================================================
        # ۱. استخراج داده‌های پایه
        # ============================================================
        S0_stock = float(opportunity.S0_stock) if opportunity.S0_stock else 0.0
        if S0_stock <= 0:
            logger.warning(
                f"S0_stock is zero for {opportunity.strategy_name}, using default 10000.0")
            S0_stock = 10000.0
            opportunity.S0_stock = S0_stock

        # ============================================================
        # ۲. آماده‌سازی آرایه‌ها برای هسته محاسباتی Numba
        # ============================================================
        weights, types, strikes, prices, contract_sizes = [], [], [], [], []

        for leg in opportunity.legs:
            weights.append(leg.weight)

            if leg.contract:  # اختیار معامله
                types.append(1 if leg.option_type == OptionType.CALL else 2)
                strikes.append(float(leg.contract.strike_price or 0))
                prices.append(
                    float(leg.contract.last_price or getattr(leg, 'entry_price', 0) or 0))
                contract_sizes.append(int(leg.contract.contract_size or 1000))
            else:  # سهم پایه
                types.append(0)
                strikes.append(0.0)
                prices.append(S0_stock)
                contract_sizes.append(1)

        pct_steps = np.array(get_price_steps())
        price_levels = np.round(S0_stock * (1 + pct_steps / 100), 0)

        # اجرای محاسبات برداری سود ناخالص
        gross_profits, returns_pct, profits_monthly, returns_monthly_pct, total_capital_engaged = calc_payoff_numba_full(
            np.array(weights), np.array(types), np.array(
                strikes), np.array(prices),
            np.array(contract_sizes), S0_stock, price_levels, factor
        )

        # ============================================================
        # ۳. فراخوانی مرجع واحد هزینه
        # ============================================================
        strategy_costs: StrategyCosts = IranMarketCostCalculator.calculate_strategy_costs(
            underlying_symbol=opportunity.underlying_ticker,
            legs=opportunity.legs,
            spot_price=S0_stock,
            include_clearing=include_clearing,
            include_exercise_tax=include_exercise_tax
        )

        # هزینه سناریوی بسته شدن
        total_costs_closed = strategy_costs.total_if_closed

        # ============================================================
        # ۴. ساخت آرایه پویای هزینه‌های اعمال در سررسید
        # ============================================================
        exercise_costs_array = np.zeros_like(price_levels, dtype=np.float64)

        # هزینه‌های ثابت اولیه
        exercise_costs_array += (
            strategy_costs.option_entry_fees +
            strategy_costs.clearing_fees
        )

        legs_breakdown = strategy_costs.breakdown.get("legs", [])
        option_idx = 0  # شمارنده جداگانه برای Option Legs

        for idx, leg in enumerate(opportunity.legs):
            if not leg.contract:
                continue

            if option_idx >= len(legs_breakdown):
                continue

            fee_info = legs_breakdown[option_idx]
            K = float(leg.contract.strike_price or 0)
            quantity = abs(leg.weight)
            quantity = float(fee_info.get("quantity"))

            exercise_fee = float(fee_info["exercise_fee"])
            exercise_tax = float(fee_info["exercise_tax"])

            # Long Call - خریدار اعمال می‌کند
            if leg.option_type == OptionType.CALL and leg.side == Side.BUY:
                exercise_costs_array += np.where(
                    price_levels > K,
                    exercise_fee, 0.0)

            # Short Call - فروشنده تخصیص می‌خورد + مالیات
            elif leg.option_type == OptionType.CALL and leg.side == Side.SELL:
                exercise_costs_array += np.where(
                    price_levels > K,
                    exercise_fee + exercise_tax, 0.0)

            # Long Put - خریدار اعمال می‌کند + مالیات
            elif leg.option_type == OptionType.PUT and leg.side == Side.BUY:
                exercise_costs_array += np.where(
                    price_levels < K,
                    exercise_fee + exercise_tax, 0.0)

            # Short Put - فروشنده تخصیص می‌خورد
            elif leg.option_type == OptionType.PUT and leg.side == Side.SELL:
                exercise_costs_array += np.where(
                    price_levels < K,
                    exercise_fee, 0.0)

            option_idx += 1

        # ============================================================
        # ۵. تشخیص Naked Call واقعی
        # ============================================================
        def _is_naked_short_call(legs) -> bool:
            """
            فقط زمانی True می‌شود که:
            - حداقل یک Short Call وجود داشته باشد
            - هیچ سهم پایه‌ای وجود نداشته باشد
            - هیچ Long Call پوشش‌دهنده‌ای وجود نداشته باشد
            """
            short_calls = [
                leg for leg in legs
                if (
                    leg.contract and
                    leg.option_type == OptionType.CALL and
                    leg.side == Side.SELL
                )
            ]

            if not short_calls:
                return False

            has_stock = any(
                getattr(leg, "is_stock_leg", False)
                for leg in legs
            )

            if has_stock:
                return False

            long_calls = [
                leg for leg in legs
                if (
                    leg.contract and
                    leg.option_type == OptionType.CALL and
                    leg.side == Side.BUY
                )
            ]

            for short_leg in short_calls:
                short_k = short_leg.contract.strike_price

                covered = any(
                    long_leg.contract.strike_price <= short_k
                    for long_leg in long_calls
                )

                if not covered:
                    return True

            return False

        if _is_naked_short_call(opportunity.legs):
            short_call = next(
                leg for leg in opportunity.legs
                if (
                    leg.contract and
                    leg.option_type == OptionType.CALL and
                    leg.side == Side.SELL
                )
            )

            qty = abs(short_call.weight)
            contract_size = short_call.contract.contract_size or 1000
            underlying_qty = qty * contract_size

            # محاسبه کارمزد خرید سهام پایه
            fee_info = IranMarketCostCalculator._calculate_underlying_cost(
                underlying_symbol=opportunity.underlying_ticker,
                spot_price=S0_stock,
                quantity=underlying_qty,
                is_buy=True,
            )

            underlying_buy_fee = fee_info["fee"]

            total_costs_closed += underlying_buy_fee
            exercise_costs_array += underlying_buy_fee

        # ============================================================
        # ۶. محاسبه سودهای خالص نهایی
        # ============================================================
        net_profits_closed = gross_profits - total_costs_closed
        net_profits_exercised = gross_profits - exercise_costs_array

        # ============================================================
        # ۷. محاسبه بازدهی خالص
        # ============================================================
        net_returns_closed = np.where(
            total_capital_engaged > 0,
            net_profits_closed / total_capital_engaged * 100,
            0.0
        )

        net_returns_exercised = np.where(
            total_capital_engaged > 0,
            net_profits_exercised / total_capital_engaged * 100,
            0.0
        )

        # ============================================================
        # ۸. محاسبه نقاط سربه‌سر و بازه‌ها
        # ============================================================
        breakeven_closed = PayoffCalculator._find_breakeven_points(
            price_levels, net_profits_closed)
        breakeven_exercised = PayoffCalculator._find_breakeven_points(
            price_levels, net_profits_exercised)

        # دو سناریو برای Dynamic Range
        dynamic_range_closed, profitable_closed = PayoffCalculator._find_dynamic_range(
            price_levels, net_returns_closed, profit_threshold
        )

        dynamic_range_exercised, profitable_exercised = PayoffCalculator._find_dynamic_range(
            price_levels, net_returns_exercised, profit_threshold
        )

        # ============================================================
        # ۹. غنی‌سازی شیء Opportunity
        # ============================================================
        def _safe_set(attr_name: str, value: Any):
            if hasattr(opportunity, attr_name):
                setattr(opportunity, attr_name, value)
            else:
                opportunity.metadata[attr_name] = value

        max_p = float(np.max(net_profits_closed))
        max_l = float(np.min(net_profits_closed))

        _safe_set('max_profit', max_p)
        _safe_set('max_loss', max_l)
        _safe_set('break_even_points', breakeven_closed)
        _safe_set('breakeven_exercised', breakeven_exercised)
        _safe_set('transaction_costs', float(total_costs_closed))
        _safe_set('capital_engaged', float(total_capital_engaged))

        # Risk/Reward Ratio
        if max_l < 0:
            risk_reward_ratio = round(abs(max_p) / abs(max_l), 2)
        else:
            risk_reward_ratio = float("inf")

        _safe_set('risk_reward_ratio', risk_reward_ratio)
        _safe_set('expected_return_pct', 0.0)

        # درصد سود بر اساس سرمایه واقعی
        _safe_set(
            'max_profit_pct',
            (max_p / total_capital_engaged * 100)
            if total_capital_engaged > 0
            else 0.0
        )

        _safe_set(
            'max_loss_pct',
            (abs(max_l) / total_capital_engaged * 100)
            if total_capital_engaged > 0
            else 0.0
        )

        # ============================================================
        # ۱۰. توصیه اکشن مبتنی بر Expected Value
        # ============================================================
        try:
            from analytics.risk_engine import RiskEngine

            pct_steps_array = np.array(get_price_steps())
            probabilities = RiskEngine.calculate_probabilities(
                S0_stock=S0_stock,
                pct_steps=pct_steps_array,
                days_to_maturity=opportunity.days_to_maturity
            )

            probabilities = np.asarray(probabilities)
            if probabilities.sum() > 0:
                probabilities = probabilities / probabilities.sum()

            expected_closed = np.sum(net_profits_closed * probabilities)
            expected_exercised = np.sum(net_profits_exercised * probabilities)

            recommended_action = (
                "نگهداری تا سررسید و اعمال موقعیت" if expected_exercised > expected_closed
                else "بستن پوزیشن قبل از سررسید (آفست نقدی)"
            )

            opportunity.metadata['expected_value_closed'] = float(
                expected_closed)
            opportunity.metadata['expected_value_exercised'] = float(
                expected_exercised)

        except Exception as e:
            logger.warning(
                f"Could not calculate expected value: {e}. Using mean comparison.")
            mean_exercised = np.mean(net_profits_exercised)
            mean_closed = np.mean(net_profits_closed)
            recommended_action = (
                "نگهداری تا سررسید و اعمال موقعیت" if mean_exercised > mean_closed
                else "بستن پوزیشن قبل از سررسید (آفست نقدی)"
            )

        # ============================================================
        # ۱۱. تزریق نهایی به metadata
        # ============================================================
        opportunity.metadata.update({
            'net_profits_closed': net_profits_closed.tolist(),
            'net_profits_exercised': net_profits_exercised.tolist(),
            'gross_profits': gross_profits.tolist(),
            'price_levels': price_levels.tolist(),
            'price_labels': [f"{int(p)}%" for p in pct_steps],
            'profitable_indices_closed': profitable_closed,
            'profitable_indices_exercised': profitable_exercised,
            'dynamic_range_closed': dynamic_range_closed,
            'dynamic_range_exercised': dynamic_range_exercised,
            'total_costs_closed': float(total_costs_closed),
            'min_exercise_cost': float(np.min(exercise_costs_array)),
            'max_exercise_cost': float(np.max(exercise_costs_array)),
            'exercise_costs_array': exercise_costs_array.tolist(),
            'recommended_action': recommended_action,
            'returns_pct': returns_pct.tolist(),
            'profits_monthly': profits_monthly.tolist(),
            'returns_monthly_pct': returns_monthly_pct.tolist(),
            'net_returns_closed': net_returns_closed.tolist(),
            'net_returns_exercised': net_returns_exercised.tolist(),
            'capital_engaged': float(total_capital_engaged),
        })

        logger.debug(
            f"Enriched Opportunity: {opportunity.strategy_name} | "
            f"max_profit={max_p}, max_loss={max_l}, "
            f"risk_reward={risk_reward_ratio}, capital={total_capital_engaged:.0f}, S0={S0_stock}"
        )

        return opportunity

    # ============================================================
    # متدهای کمکی
    # ============================================================

    @staticmethod
    def _find_breakeven_points(
        price_levels: np.ndarray,
        profits: np.ndarray,
        tolerance: float = 10.0
    ) -> List[float]:
        """یافتن نقاط سربه‌سر استراتژی با میان‌یابی خطی"""
        breakeven_points = []
        for i in range(len(profits) - 1):
            p1 = profits[i]
            p2 = profits[i + 1]
            if (p1 < 0 and p2 > 0) or (p1 > 0 and p2 < 0) or abs(p1) <= tolerance:
                if abs(p1) <= tolerance:
                    breakeven_points.append(round(float(price_levels[i]), 2))
                    continue
                ratio = (-p1) / (p2 - p1)
                be_price = price_levels[i] + ratio * \
                    (price_levels[i + 1] - price_levels[i])
                breakeven_points.append(round(float(be_price), 2))
        return breakeven_points

    @staticmethod
    def _find_dynamic_range(
        price_levels: np.ndarray,
        returns: np.ndarray,
        threshold: float = 3.0
    ) -> Tuple[List[float], List[int]]:
        """تشخیص محدوده‌های قیمتی که بازدهی در آن‌ها فراتر از حد آستانه است"""
        profitable_indices = [i for i, ret in enumerate(
            returns) if ret >= threshold]
        dynamic_range = [float(price_levels[i]) for i in profitable_indices]
        return dynamic_range, profitable_indices


# =====================================================
# بخش ۳: توابع Facade بیرونی
# =====================================================

def enrich_opportunity_with_pnl(
    opportunity: Opportunity,
    factor: float = 1.0,
    include_clearing: bool = True,
    include_exercise_tax: bool = True,
    profit_threshold: Optional[float] = None
) -> Opportunity:
    """
    تابع راحت‌تر برای غنی‌سازی یک فرصت با محاسبات P&L

    Args:
        opportunity: شیء Opportunity خام
        factor: ضریب تبدیل برای محاسبات ماهانه
        include_clearing: شامل کارمزد تسویه
        include_exercise_tax: شامل مالیات اعمال
        profit_threshold: آستانه سود برای محدوده داینامیک

    Returns:
        Opportunity: شیء غنی‌شده با داده‌های P&L
    """
    return PayoffCalculator.calculate_and_enrich(
        opportunity=opportunity,
        factor=factor,
        include_clearing=include_clearing,
        include_exercise_tax=include_exercise_tax,
        profit_threshold=profit_threshold
    )
