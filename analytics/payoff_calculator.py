# analytics/payoff_calculator.py
# -*- coding: utf-8 -*-

"""
محاسبه‌گر فوق سریع P&L و ماتریس بازدهی بر پایه محاسبات وکتوریزه Numba
تنظیم شده برای خط لوله پردازش جریانی (Streaming Pipeline) بازار ایران
"""

import numpy as np
from numba import njit
from typing import List, Optional

from config import get_price_levels, get_feature_flags
from core.models import LegDefinition, PayoffAnalysis
from core.enums import Side, OptionType
from analytics.cost_calculator import IranMarketCostCalculator


@njit(cache=True, fastmath=True)
def calc_pure_gross_payoff_numba(
        price_levels: np.ndarray,
        weights: np.ndarray,
        strikes: np.ndarray,
        entry_prices: np.ndarray,
        option_types: np.ndarray,
        sides: np.ndarray,
        contract_sizes: np.ndarray) -> np.ndarray:
    """
    محاسبه سود/زیان ناخالص با استفاده از Numba و وکتوریزاسیون پیشرفته پردازنده (fastmath)
    """
    num_points = len(price_levels)
    num_legs = len(weights)
    gross_profits = np.zeros(num_points, dtype=np.float64)

    for i in range(num_points):
        S = price_levels[i]
        total_pnl = 0.0
        for j in range(num_legs):
            w = weights[j]
            # شرط مدار کوتاه (Short-circuit) برای پرش از لگ‌های بدون اثر در محاسبات
            if abs(w) < 1e-8:
                continue

            side = sides[j]
            opt_type = option_types[j]
            K = strikes[j]
            entry_p = entry_prices[j]
            c_size = contract_sizes[j]

            if opt_type == 0:  # Stock
                pnl = (S - entry_p) if side == 1 else (entry_p - S)
                total_pnl += w * pnl * c_size
            elif opt_type == 1:  # Call
                payoff = max(S - K, 0.0)
                premium_pnl = (
                    payoff - entry_p) if side == 1 else (entry_p - payoff)
                total_pnl += w * premium_pnl * c_size
            elif opt_type == 2:  # Put
                payoff = max(K - S, 0.0)
                premium_pnl = (
                    payoff - entry_p) if side == 1 else (entry_p - payoff)
                total_pnl += w * premium_pnl * c_size

        gross_profits[i] = total_pnl

    return gross_profits


class IranMarketPayoffCalculator:
    """
    محاسبه‌گر ماتریس P&L استراتژی‌های آپشن هماهنگ با حامل‌های سبک پردازشی (PayoffAnalysis)
    """

    @classmethod
    def calculate_payoff(
            cls,
            legs: List[LegDefinition],
            spot_price: float,
            price_levels: Optional[np.ndarray] = None) -> PayoffAnalysis:
        """
        محاسبه برداری بازدهی خالص و ناخالص، محاسبه دقیق پرمیوم و استخراج خطی نقاط سربه‌سر استراتژی.
        """
        if price_levels is None:
            price_levels = get_price_levels(spot_price)

        num_legs = len(legs)
        weights = np.zeros(num_legs, dtype=np.float64)
        strikes = np.zeros(num_legs, dtype=np.float64)
        entry_prices = np.zeros(num_legs, dtype=np.float64)
        option_types = np.zeros(num_legs, dtype=np.int32)
        sides = np.zeros(num_legs, dtype=np.int32)
        contract_sizes = np.zeros(num_legs, dtype=np.int32)

        # ۱. استخراج اطلاعات لگ‌ها به آرایه‌های مجزای ساختاریافته پایتون
        for idx, leg in enumerate(legs):
            weights[idx] = leg.weight
            sides[idx] = 1 if leg.side == Side.BUY else -1
            contract = leg.contract

            if contract is not None:
                strikes[idx] = contract.strike_price
                # اولویت‌بندی قیمت: ورود کاربر -> قیمت میانی (بهترین برای آپشن ایران) -> آخرین معامله
                entry_prices[idx] = leg.entry_price or getattr(
                    contract, 'mid_price', 0.0) or contract.last_price
                ot = contract.option_type
                option_types[idx] = 0 if ot == OptionType.STOCK else (
                    1 if ot == OptionType.CALL else 2)
                contract_sizes[idx] = contract.contract_size
            else:
                strikes[idx] = 0.0
                entry_prices[idx] = spot_price
                option_types[idx] = 0
                contract_sizes[idx] = 1

        # ۲. اجرای پردازش ماتریسی توسط موتور کامپایل شده Numba
        gross_profits = calc_pure_gross_payoff_numba(
            price_levels, weights, strikes, entry_prices,
            option_types, sides, contract_sizes)

        # ۳. محاسبه و کسر هزینه‌ها و کارمزدهای معاملاتی بورس تهران
        underlying_ticker = legs[0].contract.underlying_ticker if legs and legs[0].contract else ""
        strategy_costs = IranMarketCostCalculator.calculate_strategy_costs(
            underlying_symbol=underlying_ticker,
            legs=legs,
            spot_price=spot_price)

        flags = get_feature_flags()
        if flags.get("apply_commissions", True):
            net_profits_closed = gross_profits - strategy_costs.total_if_closed
        else:
            net_profits_closed = gross_profits.copy()

        # ۴. محاسبه دقیق جریان نقدینگی ناشی از حق بیمه (Net Premium) با احتساب جهت موقعیت‌ها
        net_premium = 0.0
        for leg in legs:
            if leg.contract:
                price = leg.entry_price or getattr(
                    leg.contract, 'mid_price', 0.0) or leg.contract.last_price
                value = price * leg.contract.contract_size * leg.ratio
                # خرید باعث خروج نقدینگی (بدهکار) و فروش باعث ورود نقدینگی (بستانکار) می‌شود
                net_premium += value if leg.side == Side.BUY else -value

        max_profit = float(np.max(net_profits_closed))
        max_loss = float(np.min(net_profits_closed))

        # ۵. استخراج سریع برداری نقاط سربه‌سر (Break-even Points) با متد درون‌یابی خطی
        break_even_points = []
        sign_changes = np.where(np.diff(np.sign(net_profits_closed)))[0]
        for idx in sign_changes:
            p1, p2 = price_levels[idx], price_levels[idx + 1]
            v1, v2 = net_profits_closed[idx], net_profits_closed[idx + 1]
            if v2 != v1:
                be = p1 - v1 * (p2 - p1) / (v2 - v1)
                break_even_points.append(round(float(be), 2))

        # ۶. بسته‌بندی خروجی در قالب دیتاتایپ سبک و نهایی خط لوله پردازشی
        return PayoffAnalysis(
            # نگهداری به صورت آرایه خام نپای جهت فیلترینگ‌های سریع بعدی
            returns_pct=net_profits_closed,
            net_premium=round(net_premium, 2),
            max_profit=round(max_profit, 2),
            max_loss=round(abs(max_loss), 2),
            break_even_points=break_even_points)
