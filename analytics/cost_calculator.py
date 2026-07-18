# analytics/cost_calculator.py
# -*- coding: utf-8 -*-

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from config import (
    EXERCISE_TAX_RATE,
    get_symbol_market,
    get_symbol_kind,
    get_commission_rate,
    get_exercise_fee_rate,
    FEATURE_FLAGS,)
from core.models import LegDefinition
from core.enums import Side, OptionType


@dataclass(slots=True)
class StrategyCosts:
    option_entry_fees: float = 0.0
    underlying_buy_fees: float = 0.0
    underlying_sell_fees: float = 0.0
    total_entry_cost: float = 0.0  # مجموع هزینه‌های قطعی در لحظه ورود (t0)
    breakdown: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, float]:
        """تبدیل به دیکشنری برای استفاده در سایر ماژول‌ها و لایه‌های تحلیلی V3"""
        return {
            'option_entry_fees': self.option_entry_fees,
            'underlying_buy_fees': self.underlying_buy_fees,
            'underlying_sell_fees': self.underlying_sell_fees,
            'total_entry_cost': self.total_entry_cost, }


class IranMarketCostCalculator:
    EXERCISE_TAX_RATE = EXERCISE_TAX_RATE  # 0.005 (نیم درصد)

    # سقف کارمزد معاملات خرید/فروش پرمیوم آپشن معادل ۲۰۰,۰۰۰,۰۰۰ ریال (۲۰ میلیون تومان) برای هر لگ
    OPTION_FEE_CAP = 200000000.0

    @classmethod
    def calculate_strategy_costs(
            cls,
            underlying_symbol: str,
            legs: List[LegDefinition],
            spot_price: Optional[float],
            contract_sizes: np.ndarray) -> StrategyCosts:
        """
        محاسبه تمام‌برداری هزینه‌های قطعی اولیه در لحظه ورود به استراتژی (t0).
        کارمزد خروج پرمیوم حذف شده است، چرا که پوزیشن‌ها تا روز سررسید و تسویه نهایی باز می‌مانند.
        """
        if not legs or spot_price is None or spot_price <= 0:
            return StrategyCosts()

        market = get_symbol_market(underlying_symbol)
        kind = get_symbol_kind(underlying_symbol)

        # ۱. استخراج مشخصات لِگ‌ها به آرایه‌های نامپای جهت پردازش موازی و برداری
        ratios = np.array([abs(getattr(l, 'ratio', 1))
                          for l in legs], dtype=np.float64)
        sides = np.array([1 if l.side == Side.BUY else -
                         1 for l in legs], dtype=np.int32)

        option_types = np.array([
            l.contract.option_type.value if l.contract else OptionType.STOCK.value
            for l in legs
        ], dtype=np.int32)

        # اعمال بند ۴ (ماده ۲۴): فالبک به قیمت نظری در صورت عدم معامله فعال در زنجیره اختیارها
        use_fallback = FEATURE_FLAGS.get(
            "use_theoretical_price_fallback", False)

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

        # ۲. ساخت ماسک‌های شرطی برداری
        is_option = (option_types != OptionType.STOCK.value)
        is_stock = ~is_option
        is_buy = (sides == 1)

        # ۳. محاسبه برداری ارزش معاملاتی و کارمزدهای ورود آپشن با اعمال سقف ۲۰۰ میلیون ریالی
        option_qtys = ratios * is_option
        entry_values = entry_prices * contract_sizes * option_qtys

        opt_buy_rate = get_commission_rate(market, 'option', True)
        opt_sell_rate = get_commission_rate(market, 'option', False)

        raw_entry_fees = np.where(
            is_buy, entry_values * opt_buy_rate, entry_values * opt_sell_rate)
        option_entry_fees = np.round(
            np.sum(np.minimum(raw_entry_fees, cls.OPTION_FEE_CAP)), 0)

        # ۴. محاسبه کارمزد خرید و فروش دارایی پایه نقدی (در صورت وجود سهم پایه مثل Covered Call)
        stock_qty = np.sum(ratios * is_stock * contract_sizes)
        total_underlying_buy = 0.0
        total_underlying_sell = 0.0

        if stock_qty > 0:
            total_underlying_buy = np.round(
                (spot_price * stock_qty) * get_commission_rate(market, kind, True), 0)
            total_underlying_sell = np.round(
                (spot_price * stock_qty) * get_commission_rate(market, kind, False), 0)

        # مجموع جریانات هزینه نقدی قطعی در لحظه ورود
        total_entry_cost = option_entry_fees + total_underlying_buy

        return StrategyCosts(
            option_entry_fees=int(option_entry_fees),
            underlying_buy_fees=int(total_underlying_buy),
            underlying_sell_fees=int(total_underlying_sell),
            total_entry_cost=int(total_entry_cost))

    @classmethod
    def generate_exercise_cost_vector(
            cls,
            underlying_symbol: str,
            legs: List[LegDefinition],
            price_levels: np.ndarray,
            include_exercise_fee: bool = True) -> np.ndarray:
        """
        تولید کاملاً برداری ماتریس هزینه‌های پایان دوره (سررسید).
        کارمزد اعمال و مالیات انتقال فیزیکی دارایی پایه بدون سقف ریالی محاسبه می‌شود.
        """
        if not legs or price_levels is None or len(price_levels) == 0:
            return np.zeros_like(price_levels, dtype=np.float64)

        market = get_symbol_market(underlying_symbol)
        kind = get_symbol_kind(underlying_symbol)
        exercise_rate = get_exercise_fee_rate(market, kind)  # 0.0005 (نیم در هزار ارزش اعمال)

        # استخراج نوع تسویه انتخابی سیستم (PHYSICAL یا CASH)
        settlement_type = FEATURE_FLAGS.get(
            "exercise_settlement_type", "PHYSICAL")

        exercise_costs_vector = np.zeros_like(price_levels, dtype=np.float64)

        for leg in legs:
            contract = getattr(leg, 'contract')
            if contract is None or contract.option_type == OptionType.STOCK:
                continue

            qty = int(abs(getattr(leg, 'ratio')))
            c_size = getattr(contract, 'contract_size')
            K = getattr(contract, 'strike_price')
            strike_value = K * c_size * qty

            # ۱. کارمزد اعمال ثابت شرکت سپرده‌گذاری مرکزی (سمات): کسر ۰.۰۰۰۵ از هر دو طرف بدون سقف
            leg_exercise_fee = (
                strike_value * exercise_rate) if include_exercise_fee else 0.0

            # ۲. مالیات نقل و انتقال سهم پایه: کسر ۰.۰۰۵ تنها در تسویه فیزیکی و فقط از واگذارکننده (فروشنده سهم) بدون سقف
            leg_tax = 0.0
            if settlement_type == "PHYSICAL":
                # فروشنده کال (تعهد فروش سهم) و خریدار پوت (حق فروش سهم) واگذارکننده هستند و مشمول مالیات می‌شوند
                if (contract.option_type == OptionType.CALL and leg.side == Side.SELL) or \
                   (contract.option_type == OptionType.PUT and leg.side == Side.BUY):
                    leg_tax = strike_value * cls.EXERCISE_TAX_RATE

            total_leg_at_exercise = leg_exercise_fee + leg_tax

            # # اعمال مشروط برداری: هزینه تنها زمانی فعال می‌شود که آپشن در سررسید در سود (ITM) باشد
            # if contract.option_type == OptionType.CALL:
            #     exercise_costs_vector += np.where(price_levels >
            #                                       K, total_leg_at_exercise, 0.0)
            # elif contract.option_type == OptionType.PUT:
            #     exercise_costs_vector += np.where(price_levels <
            #                                       K, total_leg_at_exercise, 0.0)
            exercise_costs_vector += total_leg_at_exercise

        return exercise_costs_vector
