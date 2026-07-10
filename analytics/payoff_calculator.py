# analytics/payoff_calculator.py
# -*- coding: utf-8 -*-

import numpy as np
from numba import njit
from typing import List, Optional

from config import get_feature_flags
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
    محاسبه سود/زیان ناخالص با استفاده از Numba و وکتوریزاسیون پیشرفته
    """
    num_points = len(price_levels)
    num_legs = len(weights)
    gross_profits = np.zeros(num_points, dtype=np.float64)

    for i in range(num_points):
        S = price_levels[i]
        total_pnl = 0.0

        for j in range(num_legs):
            w = weights[j]
            if abs(w) < 1e-8:
                continue

            opt_type = option_types[j]
            if opt_type == 0:    # OptionType.STOCK
                val_at_expiry = S
            elif opt_type == 1:  # OptionType.CALL
                val_at_expiry = max(S - strikes[j], 0.0)
            else:                # OptionType.PUT
                val_at_expiry = max(strikes[j] - S, 0.0)

            pnl = sides[j] * (val_at_expiry - entry_prices[j])
            total_pnl += w * pnl * contract_sizes[j]

        gross_profits[i] = total_pnl

    return gross_profits


class IranMarketPayoffCalculator:
    """
    محاسبه‌گر ماتریس P&L استراتژی‌های آپشن همراه با نرمال‌سازی درصد ماهانه
    """

    @classmethod
    def calculate_payoff(
            cls,
            legs: List[LegDefinition],
            spot_price: float,
            price_levels: Optional[np.ndarray],
            required_margin: float = 0.0) -> PayoffAnalysis:
        """
        محاسبه برداری بازدهی خالص و ناخالص و تبدیل به درصد بازدهی ماهانه (نرمال شده ۳۰ روزه)
        """
        if price_levels is None:
            # گام ۵ درصدی پیش‌فرض در بازه -۵۰ تا +۵۰ درصد دارایی پایه
            price_levels = np.arange(
                spot_price * 0.5, spot_price * 1.5, spot_price * 0.05)

        num_legs = len(legs)
        weights = np.zeros(num_legs, dtype=np.float64)
        strikes = np.zeros(num_legs, dtype=np.float64)
        entry_prices = np.zeros(num_legs, dtype=np.float64)
        option_types = np.zeros(num_legs, dtype=np.int32)
        sides = np.zeros(num_legs, dtype=np.int32)
        contract_sizes = np.zeros(num_legs, dtype=np.int32)
        has_contract = np.zeros(num_legs, dtype=np.int32)

        days_to_maturity = 30  # مقدار پیش‌فرض منطقی دوره در صورت عدم وجود آپشن

        # ✅ استخراج اطلاعات به صورت ایمن
        for idx, leg in enumerate(legs):
            weights[idx] = leg.ratio  # اصلاح دسترسی فیلد از weight به ratio
            sides[idx] = 1 if leg.side == Side.BUY else -1
            contract = leg.contract

            if contract is not None:
                strikes[idx] = contract.strike_price
                entry_prices[idx] = leg.entry_price or getattr(
                    contract, 'mid_price', 0.0) or contract.last_price
                option_types[idx] = contract.option_type.value
                contract_sizes[idx] = contract.contract_size
                has_contract[idx] = 1

                # استخراج امن DTE از اولین لگ آپشن معتبر
                if contract.option_type != OptionType.STOCK and contract.days_to_maturity > 0:
                    days_to_maturity = contract.days_to_maturity
            else:
                entry_prices[idx] = spot_price
                option_types[idx] = OptionType.STOCK.value
                contract_sizes[idx] = 1

        # ✅ محاسبه P&L ناخالص مطلق ریالی کل موقعیت
        gross_profits = calc_pure_gross_payoff_numba(
            price_levels, weights, strikes, entry_prices,
            option_types, sides, contract_sizes)

        # ✅ محاسبه هزینه‌های معاملاتی با رویکرد Lazy Evaluation
        flags = get_feature_flags()
        if flags.get("apply_commissions", True):
            underlying_ticker = legs[0].contract.underlying_ticker if legs and legs[0].contract else ""
            strategy_costs = IranMarketCostCalculator.calculate_strategy_costs(
                underlying_symbol=underlying_ticker,
                legs=legs,
                spot_price=spot_price)
            net_profits_closed = gross_profits - strategy_costs.total_if_closed
        else:
            net_profits_closed = gross_profits.copy()

        # ✅ محاسبه Net Premium (کاملاً برداری) کل موقعیت
        net_premium = np.sum(
            entry_prices * contract_sizes * weights * sides * has_contract,
            dtype=np.float64)

        # ✅ تعیین پایه سرمایه‌گذاری واقعی معامله (Capital Base) برای تبدیل درصد
        capital_base = required_margin if required_margin > 0 else abs(
            net_premium)
        if capital_base <= 0:
            # همپوشانی در مواقع اضطراری پوزیشن‌های کاملاً درآمدی بدون مارجین
            fallback_size = contract_sizes[0] if num_legs > 0 else 1000
            capital_base = spot_price * fallback_size

        # ✅ محاسبه درصد بازدهی کل دوره و اعمال فاکتور زمانی ۳۰ روزه (سود ماهانه اسکیل‌شده)
        returns_pct_period = (net_profits_closed / capital_base) * 100.0
        dte_factor = 30.0 / max(days_to_maturity, 1)
        monthly_returns = returns_pct_period * dte_factor

        # تبدیل سقف و کف نتایج نهایی به درصد ماهانه جهت تغذیه موتورهای فازی
        max_profit = float(np.max(monthly_returns))
        max_loss = float(np.min(monthly_returns))

        # ✅ نقاط سربه‌سر بر مبنای قیمت دارایی پایه
        break_even_points = cls._find_break_even_points(
            price_levels, net_profits_closed)

        return PayoffAnalysis(
            returns_pct=monthly_returns,
            net_premium=round(float(net_premium), 2),
            max_profit=round(max_profit, 2),
            max_loss=round(abs(max_loss), 2),
            break_even_points=break_even_points)

    @staticmethod
    def _find_break_even_points(
            price_levels: np.ndarray,
            profits: np.ndarray) -> List[float]:
        """یافتن نقاط سربه‌سر با درون‌یابی خطی"""
        break_even_points = []
        sign_changes = np.where(np.diff(np.sign(profits)))[0]

        for idx in sign_changes:
            p1, p2 = price_levels[idx], price_levels[idx + 1]
            v1, v2 = profits[idx], profits[idx + 1]
            if v2 != v1:
                be = p1 - v1 * (p2 - p1) / (v2 - v1)
                break_even_points.append(round(float(be), 2))

        return break_even_points
