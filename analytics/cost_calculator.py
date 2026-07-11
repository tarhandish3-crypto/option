# analytics/cost_calculator.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from config import (
    EXERCISE_TAX_RATE,
    get_symbol_info,
    get_symbol_market,
    get_symbol_kind,
    get_commission_rate,
    get_exercise_fee_rate,
    FEATURE_FLAGS,
)
from core.models import LegDefinition
from core.enums import Side, OptionType


@dataclass(slots=True)
class StrategyCosts:
    option_entry_fees: float = 0.0
    option_exit_fees: float = 0.0
    option_exercise_fees: float = 0.0
    exercise_tax: float = 0.0
    underlying_buy_fees: float = 0.0
    underlying_sell_fees: float = 0.0
    clearing_fees: float = 0.0
    total_if_closed: float = 0.0
    total_if_exercised: float = 0.0
    breakdown: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, float]:
        """تبدیل به دیکشنری برای استفاده در سایر ماژول‌ها"""
        return {
            'option_entry_fees': self.option_entry_fees,
            'option_exit_fees': self.option_exit_fees,
            'option_exercise_fees': self.option_exercise_fees,
            'exercise_tax': self.exercise_tax,
            'underlying_buy_fees': self.underlying_buy_fees,
            'underlying_sell_fees': self.underlying_sell_fees,
            'clearing_fees': self.clearing_fees,
            'total_if_closed': self.total_if_closed,
            'total_if_exercised': self.total_if_exercised,
        }


class IranMarketCostCalculator:
    EXERCISE_TAX_RATE = EXERCISE_TAX_RATE
    CLEARING_FEE_RATE = 0.0001
    CLEARING_FEE_MIN = 1000.0  # حداقل ۱,۰۰۰ ریال کف کارمزد پایاپای مصوب بورس

    @classmethod
    def calculate_strategy_costs(
            cls,
            underlying_symbol: str,
            legs: List[LegDefinition],
            spot_price: Optional[float],
            contract_sizes: np.ndarray) -> StrategyCosts:
        """
        محاسبه تمام‌برداری هزینه‌های ورود، خروج و پایاپای قانونی استراتژی آپشن
        """
        if not legs or spot_price is None or spot_price <= 0:
            return StrategyCosts()

        market = get_symbol_market(underlying_symbol)
        kind = get_symbol_kind(underlying_symbol)

        # ۱. استخراج مشخصات لِگ‌ها به آرایه‌های نامپای جهت پردازش موازی و برداری
        ratios = np.array([abs(getattr(l, 'ratio', 1)) for l in legs], dtype=np.float64)
        sides = np.array([1 if l.side == Side.BUY else -1 for l in legs], dtype=np.int32)

        option_types = np.array([
            l.contract.option_type.value if l.contract else OptionType.STOCK.value
            for l in legs
        ], dtype=np.int32)

        # اعمال بند ۴ (ماده ۲۴): فالبک به قیمت نظری در صورت عدم معامله فعال در زنجیره اختیارها
        use_fallback = FEATURE_FLAGS.get("use_theoretical_price_fallback", False)

        def _get_valid_price(leg: LegDefinition) -> float:
            if not leg.contract:
                return spot_price
            lp = getattr(leg.contract, 'last_price', 0.0)
            if lp and lp > 0:
                return lp

            if use_fallback:
                tp = getattr(leg.contract, 'theoretical_price', 0.0)
                if tp and tp > 0:
                    return tp
                return getattr(leg.contract, 'strike_price', spot_price)
            return spot_price

        entry_prices = np.array([
            getattr(l, 'entry_price', None) or _get_valid_price(l) for l in legs
        ], dtype=np.float64)

        last_prices = np.array([_get_valid_price(l) for l in legs], dtype=np.float64)

        # ۲. ساخت ماسک‌های شرطی برداری
        is_option = (option_types != OptionType.STOCK.value)
        is_stock = ~is_option
        is_buy = (sides == 1)

        # ۳. محاسبه برداری ارزش معاملاتی ورود و خروج موقعیت‌های اختیار
        option_qtys = ratios * is_option
        entry_values = entry_prices * contract_sizes * option_qtys
        exit_values = last_prices * contract_sizes * option_qtys

        # دریافت نرخ‌های ثابت کارمزد بورس از فایل تنظیمات
        opt_buy_rate = get_commission_rate(market, 'option', True)
        opt_sell_rate = get_commission_rate(market, 'option', False)

        # محاسبه هم‌زمان کارمزد ورود و خروج آپشن‌ها بر اساس جهت لِگ‌ها
        option_entry_fees = np.sum(
            np.where(is_buy, entry_values * opt_buy_rate, entry_values * opt_sell_rate))
        option_exit_fees = np.sum(
            np.where(~is_buy, exit_values * opt_buy_rate, exit_values * opt_sell_rate))

        # ۴. محاسبه برداری کارمزد پایاپای (سمات) به صورت اجباری برای لِگ‌های خرید (ماده تسویه نقدی/پایاپای)
        clearing_fees = np.sum(
            np.where(
                is_buy & is_option,
                np.maximum(entry_values * cls.CLEARING_FEE_RATE, cls.CLEARING_FEE_MIN), 0.0))

        # ۵. محاسبه کارمزد خرید و فروش دارایی پایه نقدی (سهام عادی، طلا، درآمد ثابت یا مختلط)
        stock_qty = np.sum(ratios * is_stock * contract_sizes)
        if stock_qty > 0:
            total_underlying_buy = (spot_price * stock_qty) * get_commission_rate(market, kind, True)
            total_underlying_sell = (spot_price * stock_qty) * get_commission_rate(market, kind, False)
        else:
            total_underlying_buy = 0.0
            total_underlying_sell = 0.0

        total_if_closed = option_entry_fees + option_exit_fees + clearing_fees + total_underlying_buy

        return StrategyCosts(
            option_entry_fees=round(float(option_entry_fees), 2),
            option_exit_fees=round(float(option_exit_fees), 2),
            clearing_fees=round(float(clearing_fees), 2),
            underlying_buy_fees=round(float(total_underlying_buy), 2),
            underlying_sell_fees=round(float(total_underlying_sell), 2),
            total_if_closed=round(float(total_if_closed), 2),
            total_if_exercised=round(float(total_if_closed), 2))

    @classmethod
    def generate_exercise_cost_vector(
            cls,
            underlying_symbol: str,
            legs: List[LegDefinition],
            price_levels: np.ndarray,
            include_exercise_fee: bool = True) -> np.ndarray:
        """
        تولید کاملاً برداری ماتریس هزینه‌های اعمال بر اساس قیمت‌های سررسید با اعمال هوشمند شروط مالیاتی
        """
        if not legs or price_levels is None or len(price_levels) == 0:
            return np.zeros_like(price_levels, dtype=np.float64)

        market = get_symbol_market(underlying_symbol)
        kind = get_symbol_kind(underlying_symbol)
        exercise_rate = get_exercise_fee_rate(market, kind)

        # استخراج نوع تسویه انتخابی سیستم جهت مدیریت هوشمند مالیات واگذاری
        settlement_type = FEATURE_FLAGS.get("exercise_settlement_type", "PHYSICAL")

        # آرایه خروجی نهایی هم‌اندازه با سطوح قیمتی دایینامیک ارسالی
        exercise_costs_vector = np.zeros_like(price_levels, dtype=np.float64)

        for leg in legs:
            contract = getattr(leg, 'contract', None)
            if contract is None or contract.option_type == OptionType.STOCK:
                continue

            qty = int(abs(getattr(leg, 'ratio', 1)))
            c_size = getattr(contract, 'contract_size', 1000) or 1000
            K = getattr(contract, 'strike_price', 0.0)
            strike_value = K * c_size * qty

            # کارمزد اعمال ثابت سمات (شامل حال خریدار و فروشنده در صورت وقوع فرآیند اعمال)
            leg_exercise_fee = (strike_value * exercise_rate) if include_exercise_fee else 0.0

            # مالیات نقل و انتقال واگذاری (۰.۵٪) تنها در تسویه فیزیکی و فقط برای فروشنده نهایی دارایی پایه
            leg_tax = 0.0
            if settlement_type == "PHYSICAL":
                if (contract.option_type == OptionType.CALL and leg.side == Side.SELL) or \
                   (contract.option_type == OptionType.PUT and leg.side == Side.BUY):
                    leg_tax = strike_value * cls.EXERCISE_TAX_RATE

            total_leg_at_exercise = leg_exercise_fee + leg_tax

            # اعمال مشروط برداری بر مبنای در سود بودن (In-the-Money) موقعیت در زنجیره قیمت‌ها
            if contract.option_type == OptionType.CALL:
                exercise_costs_vector += np.where(price_levels > K, total_leg_at_exercise, 0.0)
            elif contract.option_type == OptionType.PUT:
                exercise_costs_vector += np.where(price_levels < K, total_leg_at_exercise, 0.0)

        return exercise_costs_vector