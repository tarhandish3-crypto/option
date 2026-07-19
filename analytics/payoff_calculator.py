# analytics/payoff_calculator.py
# -*- coding: utf-8 -*-

import numpy as np
from numba import njit
from typing import List, Optional, Tuple

from config import FEATURE_FLAGS
from core.models import LegDefinition, PayoffAnalysis
from core.enums import Side, OptionType
from analytics.cost_calculator import IranMarketCostCalculator


# ============================================================
# بخش ۱: محاسبه سود/زیان ناخالص (Numba)
# ============================================================

@njit(cache=True, fastmath=True)
def calc_pure_gross_payoff_numba(
        price_levels: np.ndarray,
        weights: np.ndarray,
        strikes: np.ndarray,
        entry_prices: np.ndarray,
        option_types: np.ndarray,  # 0: STOCK, 1: CALL, 2: PUT
        sides: np.ndarray,          # 1: BUY, -1: SELL
        contract_sizes: np.ndarray) -> np.ndarray:
    """
    محاسبه سود/زیان ناخالص در سررسید برای تمام سطوح قیمتی
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

            # محاسبه ارزش در سررسید بر اساس نوع لگ
            if opt_type == 0:    # OptionType.STOCK
                val_at_expiry = S
            elif opt_type == 1:  # OptionType.CALL
                val_at_expiry = max(S - strikes[j], 0.0)
            else:                # OptionType.PUT
                val_at_expiry = max(strikes[j] - S, 0.0)

            # سود/زیان این لگ
            pnl = sides[j] * (val_at_expiry - entry_prices[j])
            total_pnl += w * pnl * contract_sizes[j]

        gross_profits[i] = total_pnl

    return gross_profits


# ============================================================
# بخش ۲: محاسبه جریان نقدی اولیه و سرمایه درگیر (Numba)
# ============================================================

@njit(cache=True, fastmath=True)
def calculate_initial_cash_flow_and_capital(
        weights: np.ndarray,
        entry_prices: np.ndarray,
        option_types: np.ndarray,
        sides: np.ndarray,
        contract_sizes: np.ndarray,
        has_contract: np.ndarray,) -> Tuple[float, float, float]:
    """
    محاسبه جریان نقدی اولیه و سرمایه درگیر واقعی استراتژی در زمان ورود (t₀)
    """
    net_option_premium = 0.0
    stock_investment = 0.0
    num_legs = len(weights)

    # ۱. تفکیک و محاسبه جریانات نقدی آپشن‌ها و سهم پایه
    for idx in range(num_legs):
        if has_contract[idx] == 1:
            # محاسبه ارزش لنگه معامله
            leg_val = entry_prices[idx] * contract_sizes[idx] * weights[idx]

            if option_types[idx] != 0:  # این لنگه آپشن است
                # خرید آپشن (خروج نقدینگی = مثبت)، فروش آپشن (ورود نقدینگی = منفی)
                net_option_premium += leg_val if sides[idx] == 1 else -leg_val
            else:  # این لنگه سهم پایه (Stock) است
                # اگر سهم خریده شده، هزینه آن به سرمایه درگیر اضافه می‌شود
                if sides[idx] == 1:
                    stock_investment += leg_val

    # ۲. محاسبه سرمایه پایه (Premium Capital)
    if net_option_premium < 0:
        net_option_premium = 0.0

    return net_option_premium, stock_investment


# ============================================================
# بخش ۳: کلاس اصلی محاسبه‌گر
# ============================================================

class IranMarketPayoffCalculator:
    """
    محاسبه‌گر ماتریس P&L استراتژی‌های آپشن در سررسید
    بر اساس ساختار واقعی هزینه‌های بورس ایران
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
        محاسبه بازدهی خالص با کسر دقیق هزینه‌های ورود و سررسید و احتساب دارایی پایه
        """
        # ── اعتبارسنجی ──────────────────────────────────────────────────────
        if price_levels is None or len(price_levels) == 0:
            return PayoffAnalysis()

        num_legs = len(legs)

        # ── آرایه‌های عددی برای Numba ──────────────────────────────────────
        weights = np.zeros(num_legs, dtype=np.float64)
        strikes = np.zeros(num_legs, dtype=np.float64)
        entry_prices = np.zeros(num_legs, dtype=np.float64)
        option_types = np.zeros(num_legs, dtype=np.int32)
        sides = np.zeros(num_legs, dtype=np.int32)
        contract_sizes = np.zeros(num_legs, dtype=np.int32)
        has_contract = np.zeros(num_legs, dtype=np.int32)

        use_fallback = FEATURE_FLAGS.get(
            "use_theoretical_price_fallback", False)

        # ── استخراج اطلاعات لگ‌ها ────────────────────────────────────────────
        for idx, leg in enumerate(legs):
            weights[idx] = leg.ratio
            sides[idx] = 1 if leg.side == Side.BUY else -1
            contract = leg.contract

            if contract is not None:
                strikes[idx] = contract.strike_price
                has_contract[idx] = 1  # لگ دارای قرارداد معتبر است

                if contract.option_type == OptionType.STOCK:
                    option_types[idx] = 0
                    contract_sizes[idx] = base_option_size
                elif contract.option_type == OptionType.CALL:
                    option_types[idx] = 1
                    contract_sizes[idx] = contract.contract_size
                else:  # OptionType.PUT
                    option_types[idx] = 2
                    contract_sizes[idx] = contract.contract_size

                # اولویت‌بندی استخراج قیمت ورود
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
                # این لگ قرارداد آپشن ندارد و مستقیماً خود سهم پایه است (مانند لگ خرید سهم در Covered Call)
                entry_prices[idx] = leg.entry_price if (
                    leg.entry_price and leg.entry_price > 0) else spot_price
                option_types[idx] = 0
                contract_sizes[idx] = base_option_size
                # اصلاح کلیدی: فعال کردن این پرچم تا تابع Numba هزینه خرید سهم را در محاسبات سرمایه لحاظ کند
                has_contract[idx] = 1

        # ── ۱. محاسبه سود ناخالص ──────────────────────────────────────────────
        gross_profits = calc_pure_gross_payoff_numba(
            price_levels, weights, strikes, entry_prices,
            option_types, sides, contract_sizes)

        # ── ۲. تشخیص نماد پایه ─────────────────────────────────────────────────
        first_option_leg = next(
            (l for l in legs if l.contract and l.contract.option_type != OptionType.STOCK), None)
        underlying_ticker = first_option_leg.contract.underlying_ticker if first_option_leg else ""

        # ── ۳. اعمال کارمزد ورود (t₀) ─────────────────────────────────────────
        option_fees = 0.0
        net_profits_expiry = gross_profits.copy()

        apply_commissions = FEATURE_FLAGS.get("apply_commissions", True)
        if apply_commissions and underlying_ticker:
            strategy_costs = IranMarketCostCalculator.calculate_strategy_costs(
                underlying_symbol=underlying_ticker,
                legs=legs,
                spot_price=spot_price,
                contract_sizes=contract_sizes)
            net_profits_expiry -= strategy_costs.total_entry_cost
            option_fees = strategy_costs.total_entry_cost

        # ── ۴. اعمال کارمزد اعمال و مالیات در سررسید ────────────────────────
        apply_exercise_fee = FEATURE_FLAGS.get("apply_exercise_fee", True)
        if apply_exercise_fee and underlying_ticker:
            exercise_costs_vector = IranMarketCostCalculator.generate_exercise_cost_vector(
                underlying_symbol=underlying_ticker,
                legs=legs,
                price_levels=price_levels,
                include_exercise_fee=True)
            net_profits_expiry -= exercise_costs_vector

        # ── ۵. محاسبه جریان نقدی اولیه و سرمایه درگیر ────────────────────────
        net_option_premium, stock_investment = calculate_initial_cash_flow_and_capital(
            weights=weights,
            entry_prices=entry_prices,
            option_types=option_types,
            sides=sides,
            contract_sizes=contract_sizes,
            has_contract=has_contract,)

        # ── ۶. محاسبه سرمایه درگیر واقعی ───────────────────────────────────────
        # اکنون به لطف اصلاح بلاک else، هزینه خرید سهام (stock_investment) نیز به درستی جمع می‌شود
        capital_base = required_margin + net_option_premium + stock_investment + option_fees

        # جلوگیری از تقسیم بر صفر
        if capital_base <= 0:
            capital_base = 1.0

        # ── ۷. محاسبه درصد بازدهی و سود ماهانه ───────────────────────────────
        returns_pct_period = (net_profits_expiry / capital_base) * 100.0
        dte_factor = 30.0 / max(days_to_maturity, 1.0)
        monthly_returns = np.round(returns_pct_period * dte_factor, 1)

        # ── ۸. استخراج شاخص‌های نهایی ─────────────────────────────────────────
        max_profit_total = float(np.max(net_profits_expiry))
        max_loss_total = float(np.min(net_profits_expiry))

        break_even_points = cls._find_break_even_points(
            price_levels, net_profits_expiry)

        # ── ۹. بازگشت نتیجه ────────────────────────────────────────────────────
        return PayoffAnalysis(
            returns_pct=monthly_returns,
            net_premium=round(float(net_option_premium), 2),
            max_profit=round(max_profit_total, 2),
            max_loss=round(abs(max_loss_total), 2),
            break_even_points=break_even_points)

    # ============================================================
    # بخش ۴: توابع کمکی
    # ============================================================

    @staticmethod
    def _find_break_even_points(
            price_levels: np.ndarray,
            profits: np.ndarray) -> List[float]:
        """
        یافتن دقیق نقاط سربه‌سر استراتژی با درون‌یابی خطی روی بردار سود خالص
        """
        break_even_points = []
        sign_changes = np.where(np.diff(np.sign(profits)))[0]

        for idx in sign_changes:
            p1, p2 = price_levels[idx], price_levels[idx + 1]
            v1, v2 = profits[idx], profits[idx + 1]
            if v2 != v1:
                be = p1 - v1 * (p2 - p1) / (v2 - v1)
                break_even_points.append(round(float(be), 2))

        return break_even_points
