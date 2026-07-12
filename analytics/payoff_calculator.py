# analytics/payoff_calculator.py
# -*- coding: utf-8 -*-

import numpy as np
from numba import njit
from typing import List, Optional

from config import FEATURE_FLAGS
from core.models import LegDefinition, PayoffAnalysis
from core.enums import Side, OptionType
from analytics.cost_calculator import IranMarketCostCalculator


# @njit(cache=True, fastmath=True)
def calc_pure_gross_payoff_numba(
        price_levels: np.ndarray,
        weights: np.ndarray,
        strikes: np.ndarray,
        entry_prices: np.ndarray,
        option_types: np.ndarray,  # 0: STOCK, 1: CALL, 2: PUT
        sides: np.ndarray,         # 1: BUY, -1: SELL
        contract_sizes: np.ndarray) -> np.ndarray:
    """
    محاسبه سود/زیان ناخالص با استفاده از Numba و وکتوریزاسیون پیشرفته به صورت کاملاً کامپایل‌شده
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
    محاسبه‌گر ماتریس P&L استراتژی‌های آپشن در سررسید بر اساس ساختار واقعی هزینه‌های بورس ایران
    """

    @classmethod
    def calculate_payoff(
            cls,
            legs: List[LegDefinition],
            spot_price: float,
            price_levels: Optional[np.ndarray],
            required_margin: float,
            days_to_maturity: float,
            base_option_size: float) -> PayoffAnalysis:
        """
        محاسبه بازدهی خالص با کسر دقیق هزینه ثابت ورود و ماتریس متغیر هزینه‌های اعمال سررسید (بدون سقف)
        """
        if price_levels is None or len(price_levels) == 0:
            return PayoffAnalysis()

        num_legs = len(legs)
        weights = np.zeros(num_legs, dtype=np.float64)
        strikes = np.zeros(num_legs, dtype=np.float64)
        entry_prices = np.zeros(num_legs, dtype=np.float64)
        option_types = np.zeros(num_legs, dtype=np.int32)
        sides = np.zeros(num_legs, dtype=np.int32)
        contract_sizes = np.zeros(num_legs, dtype=np.int32)
        has_contract = np.zeros(num_legs, dtype=np.int32)

        use_fallback = FEATURE_FLAGS.get(
            "use_theoretical_price_fallback", False)

        # استخراج اطلاعات لگ‌ها به آرایه‌های عددی همگن جهت ارسال به هسته Numba
        for idx, leg in enumerate(legs):
            weights[idx] = leg.ratio
            sides[idx] = 1 if leg.side == Side.BUY else -1
            contract = leg.contract

            if contract is not None:
                strikes[idx] = contract.strike_price
                has_contract[idx] = 1

                if contract.option_type == OptionType.STOCK:
                    option_types[idx] = 0
                    contract_sizes[idx] = base_option_size
                elif contract.option_type == OptionType.CALL:
                    option_types[idx] = 1
                    contract_sizes[idx] = contract.contract_size
                else:  # OptionType.PUT
                    option_types[idx] = 2
                    contract_sizes[idx] = contract.contract_size

                # اولویت‌بندی استخراج قیمت مبنای ورود (بند ۴)
                if leg.entry_price and leg.entry_price > 0:
                    entry_prices[idx] = leg.entry_price
                else:
                    lp = getattr(contract, 'last_price', 0.0)
                    if lp and lp > 0:
                        entry_prices[idx] = lp
                    elif use_fallback:
                        tp = getattr(contract, 'theoretical_price', 0.0)
                        entry_prices[idx] = tp if (
                            tp and tp > 0) else contract.strike_price
                    else:
                        entry_prices[idx] = spot_price
            else:
                entry_prices[idx] = spot_price
                option_types[idx] = 0
                contract_sizes[idx] = base_option_size

        # ۱. محاسبه سود ناخالص پایه در لحظه سررسید
        gross_profits = calc_pure_gross_payoff_numba(
            price_levels, weights, strikes, entry_prices,
            option_types, sides, contract_sizes)

        first_option_leg = next(
            (l for l in legs if l.contract and l.contract.option_type != OptionType.STOCK), None)
        underlying_ticker = first_option_leg.contract.underlying_ticker if first_option_leg else ""

        apply_commissions = FEATURE_FLAGS.get("apply_commissions", True)
        apply_exercise_fee = FEATURE_FLAGS.get("apply_exercise_fee", True)

        option_fees = 0.0
        net_profits_expiry = gross_profits.copy()

        # ۲. اعمال کارمزد ثابت ورود (t0) با احتساب سقف مصوب جدید بورس (۲۰۰ میلیون ریال برای هر لگ)
        if apply_commissions and underlying_ticker:
            strategy_costs = IranMarketCostCalculator.calculate_strategy_costs(
                underlying_symbol=underlying_ticker,
                legs=legs,
                spot_price=spot_price,
                contract_sizes=contract_sizes)

            # کسر هزینه قطعی ورود اولیه از ماتریس سود نهایی
            net_profits_expiry -= strategy_costs.total_entry_cost
            option_fees = strategy_costs.total_entry_cost

        # ۳. اعمال برداری ماتریس هزینه‌های اعمال و مالیات انتقال فیزیکی در سررسید (بدون سقف ریالی)
        if apply_exercise_fee and underlying_ticker:
            exercise_costs_vector = IranMarketCostCalculator.generate_exercise_cost_vector(
                underlying_symbol=underlying_ticker,
                legs=legs,
                price_levels=price_levels,
                include_exercise_fee=True)

            # کسر مشروط هزینه‌های پایاپای سررسید بر اساس وضعیت ITM
            net_profits_expiry -= exercise_costs_vector

        # محاسبه جریانات نقدی خالص پرمیوم (Debit / Credit)
        # ۱. تفکیک و محاسبه جریانات نقدی آپشن‌ها و سهم پایه
        net_option_premium = 0.0
        stock_investment = 0.0
        for idx in range(num_legs):
            if has_contract[idx] == 1:
                # محاسبه ارزش لنگه معامله
                leg_val = entry_prices[idx] * \
                    contract_sizes[idx] * weights[idx]

                if option_types[idx] != 0:  # این لنگه آپشن است
                    # خرید آپشن (خروج نقدینگی = مثبت)، فروش آپشن (ورود نقدینگی = منفی)
                    net_option_premium += leg_val if sides[idx] == 1 else -leg_val
                else:  # این لنگه سهم پایه (Stock) است
                    # اگر سهم خریده شده، هزینه آن به سرمایه درگیر اضافه می‌شود
                    if sides[idx] == 1:
                        stock_investment += leg_val

        # ۲. محاسبه سرمایه درگیر واقعی (Capital Base)
        # اگر آپشن‌ها خالص دریافتی (منفی) باشند، از وجه تضمین کم می‌شوند تا سرمایه درگیر واقعی به دست آید
        if net_option_premium < 0:
            # استراتژی اعتباری (Credit): سرمایه = وجه تضمین - پرمیوم دریافتی
            premium_capital = max(required_margin + net_option_premium, 0.0)
        else:
            # استراتژی بدهی (Debit): سرمایه = پرمیوم پرداختی + وجه تضمین
            premium_capital = net_option_premium + required_margin

        # مخرج کسر نهایی شامل: هزینه آپشن‌ها + وجه تضمین + هزینه خرید سهم پایه + کارمزدها
        capital_base = premium_capital + stock_investment + option_fees

        # محاسبه درصد بازدهی کل دوره و اسکیل کردن زمانی به ۳۰ روز (سود ماهانه واقعی)
        returns_pct_period = (net_profits_expiry / capital_base) * \
            100.0 if capital_base > 0 else np.zeros_like(net_profits_expiry)
        dte_factor = 30.0 / max(days_to_maturity, 1.0)
        monthly_returns = returns_pct_period * dte_factor

        max_profit_total = float(np.max(net_profits_expiry))
        max_loss_total = float(np.min(net_profits_expiry))

        # استخراج دقیق نقاط سر‌به‌سر پس از اعمال تمام هزینه‌ها و مالیات‌ها
        break_even_points = cls._find_break_even_points(
            price_levels, net_profits_expiry)

        return PayoffAnalysis(
            returns_pct=monthly_returns,
            net_premium=round(float(net_option_premium), 2),
            max_profit=round(max_profit_total, 2),
            max_loss=round(abs(max_loss_total), 2),
            break_even_points=break_even_points)

    @staticmethod
    def _find_break_even_points(price_levels: np.ndarray, profits: np.ndarray) -> List[float]:
        """یافتن دقیق نقاط سربه‌سر استراتژی با درون‌یابی خطی روی بردار سود خالص"""
        break_even_points = []
        sign_changes = np.where(np.diff(np.sign(profits)))[0]

        for idx in sign_changes:
            p1, p2 = price_levels[idx], price_levels[idx + 1]
            v1, v2 = profits[idx], profits[idx + 1]
            if v2 != v1:
                be = p1 - v1 * (p2 - p1) / (v2 - v1)
                break_even_points.append(round(float(be), 2))

        return break_even_points
