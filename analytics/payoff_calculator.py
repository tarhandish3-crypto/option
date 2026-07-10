# analytics/payoff_calculator.py
# -*- coding: utf-8 -*-

import numpy as np
from numba import njit
from typing import List, Optional

from config import get_feature_flags
from core.models import LegDefinition, PayoffAnalysis
from core.enums import Side, OptionType
from analytics.cost_calculator import IranMarketCostCalculator


# @njit(cache=True, fastmath=True)
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
            required_margin: float,
            days_to_maturity: float) -> PayoffAnalysis:
        """
        محاسبه برداری بازدهی خالص و ناخالص و تبدیل به درصد بازدهی ماهانه بر اساس Capital Base واقعی بورس ایران
        """

        num_legs = len(legs)
        weights = np.zeros(num_legs, dtype=np.float64)
        strikes = np.zeros(num_legs, dtype=np.float64)
        entry_prices = np.zeros(num_legs, dtype=np.float64)
        option_types = np.zeros(num_legs, dtype=np.int32)
        sides = np.zeros(num_legs, dtype=np.int32)
        contract_sizes = np.zeros(num_legs, dtype=np.int32)
        has_contract = np.zeros(num_legs, dtype=np.int32)

        # ✅ استخراج اطلاعات به صورت ایمن
        for idx, leg in enumerate(legs):
            weights[idx] = leg.ratio
            sides[idx] = 1 if leg.side == Side.BUY else -1
            contract = leg.contract

            if contract is not None:
                strikes[idx] = contract.strike_price
                entry_prices[idx] = leg.entry_price or getattr(
                    contract, 'mid_price', 0.0) or contract.last_price
                option_types[idx] = contract.option_type.value
                contract_sizes[idx] = contract.contract_size
                has_contract[idx] = 1
            else:
                entry_prices[idx] = spot_price
                option_types[idx] = OptionType.STOCK.value
                contract_sizes[idx] = 1

        # ✅ محاسبه P&L ناخالص مطلق ریالی کل موقعیت
        gross_profits = calc_pure_gross_payoff_numba(
            price_levels, weights, strikes, entry_prices,
            option_types, sides, contract_sizes)

        # ✅ استخراج امن نام نماد پایه بدون تداخل با لایه‌های مدل آپشن
        first_option_leg = next(
            (l for l in legs if l.contract and l.contract.option_type != OptionType.STOCK), None)
        underlying_ticker = first_option_leg.contract.underlying_ticker if first_option_leg else ""

        # ✅ محاسبه هزینه‌های معاملاتی ورود با رویکرد Lazy Evaluation
        flags = get_feature_flags()
        if flags.get("apply_commissions", True) and underlying_ticker:
            strategy_costs = IranMarketCostCalculator.calculate_strategy_costs(
                underlying_symbol=underlying_ticker,
                legs=legs,
                spot_price=spot_price)
            net_profits_closed = gross_profits - strategy_costs.total_if_closed
            option_fees = strategy_costs.option_entry_fees + \
                strategy_costs.clearing_fees + strategy_costs.underlying_buy_fees
        else:
            net_profits_closed = gross_profits.copy()
            option_fees = 0.0

        # ✅ محاسبه جریانات نقدی خالص پرمیوم (دبیت هزینه کل مثبت / کردیت دریافتی منفی)
        # لنگه‌های غیر سهام (آپشن‌ها) بر مبنای جهت معامله تعیین وضعیت می‌شوند.
        net_premium = 0.0
        for idx in range(num_legs):
            if option_types[idx] != OptionType.STOCK.value and has_contract[idx] == 1:
                leg_val = entry_prices[idx] * \
                    contract_sizes[idx] * weights[idx]
                net_premium += leg_val if sides[idx] == 1 else -leg_val

        # ✅ تشکیل مخرج کسر سرمایه‌گذاری واقعی معامله (Capital Base)
        # فرمول: خالص پرمیوم جریان نقدی (در صورت بدهکار بودن موقعیت) + مجموع هزینه‌ها کارمزد ورود + وجه تضمین کل
        premium_pay = max(net_premium, 0.0)
        capital_base = premium_pay + option_fees + required_margin

        #  محاسبه درصد بازدهی کل دوره و اعمال فاکتور زمانی ۳۰ روزه (سود ماهانه اسکیل‌شده)
        returns_pct_period = (net_profits_closed / capital_base) * 100.0
        dte_factor = 30.0 / max(days_to_maturity, 1)
        monthly_returns = returns_pct_period * dte_factor

        # ✅ استخراج سود و زیان ماکزیمم ریالی دوره (مطلق)
        max_profit_total = float(np.max(net_profits_closed))
        max_loss_total = float(np.min(net_profits_closed))

        # ✅ نقاط سربه‌سر بر مبنای قیمت دارایی پایه
        break_even_points = cls._find_break_even_points(
            price_levels, net_profits_closed)

        return PayoffAnalysis(
            returns_pct=monthly_returns,
            net_premium=round(float(net_premium), 2),
            max_profit=round(max_profit_total, 2),
            max_loss=round(abs(max_loss_total), 2),
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
