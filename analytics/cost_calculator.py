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
    CLEARING_FEE_MIN = 1000.0

    @classmethod
    def calculate_strategy_costs(
            cls,
            underlying_symbol: str,
            legs: List[LegDefinition],
            spot_price: Optional[float],
            contract_sizes: np.ndarray,
            include_clearing: bool = True,) -> StrategyCosts:
        total_entry = 0.0
        total_exit = 0.0
        total_clearing = 0.0
        total_underlying_buy = 0.0
        total_underlying_sell = 0.0

        market = get_symbol_market(underlying_symbol)
        kind = get_symbol_kind(underlying_symbol)

        # محاسبه حجم و کارمزد ورود/خروج پوزیشن‌های اختیار
        for idx, leg in enumerate(legs):
            contract = getattr(leg, 'contract', None)
            # 🟢 اصلاح: کارمزدها فقط برای لنگه‌های اختیار محاسبه می‌شوند، نه لنگه دارایی پایه مستقیم
            if contract is not None and contract.option_type != OptionType.STOCK:
                # 🟢 اصلاح: تغییر فیلد از weight به ratio
                qty = int(abs(getattr(leg, 'ratio', 1)))
                c_size = contract_sizes[idx]
                entry_p = getattr(leg, 'entry_price', None) or getattr(
                    contract, 'last_price', 0.0)
                exit_p = getattr(contract, 'last_price', 0.0)

                entry_val = entry_p * c_size * qty
                exit_val = exit_p * c_size * qty

                entry_rate = get_commission_rate(
                    market, 'option', leg.side == Side.BUY)
                total_entry += entry_val * entry_rate

                exit_rate = get_commission_rate(
                    market, 'option', leg.side != Side.BUY)
                total_exit += exit_val * exit_rate

                if include_clearing and leg.side == Side.BUY:
                    total_clearing += max(entry_val *
                                          cls.CLEARING_FEE_RATE, cls.CLEARING_FEE_MIN)
        
        stock_qty = 0.0
        for idx, leg in enumerate(legs):
            if leg.contract and leg.contract.option_type == OptionType.STOCK:
                # 🟢 نسبت لِگ سهم را در سایز نرمالایز شده موجود در آرایه ضرب می‌کنیم
                stock_qty += abs(leg.ratio) * contract_sizes[idx]

        if stock_qty > 0 and spot_price is not None and spot_price > 0:
            stock_buy_rate = get_commission_rate(market, kind, True)
            total_underlying_buy = (spot_price * stock_qty) * stock_buy_rate

            stock_sell_rate = get_commission_rate(market, kind, False)
            total_underlying_sell = (spot_price * stock_qty) * stock_sell_rate

        total_if_closed = total_entry + total_exit + total_clearing + total_underlying_buy

        return StrategyCosts(
            option_entry_fees=round(total_entry, 2),
            option_exit_fees=round(total_exit, 2),
            clearing_fees=round(total_clearing, 2),
            underlying_buy_fees=round(total_underlying_buy, 2),
            underlying_sell_fees=round(total_underlying_sell, 2),
            total_if_closed=round(total_if_closed, 2),
            total_if_exercised=round(total_if_closed, 2)
        )

    @classmethod
    def generate_exercise_cost_vector(
            cls,
            underlying_symbol: str,
            legs: List[LegDefinition],
            price_levels: np.ndarray,
            include_exercise_tax: bool = True
    ) -> np.ndarray:
        """
        تولید کاملاً برداری بردار هزینه‌های اعمال بر اساس سطوح قیمتی سررسید
        """
        market = get_symbol_market(underlying_symbol)
        kind = get_symbol_kind(underlying_symbol)
        exercise_rate = get_exercise_fee_rate(market, kind)

        exercise_costs_vector = np.zeros_like(price_levels, dtype=np.float64)

        for leg in legs:
            contract = getattr(leg, 'contract', None)
            # 🟢 اصلاح: نادیده گرفتن لنگه سهام پایه در اعمال
            if contract is None or contract.option_type == OptionType.STOCK:
                continue

            # 🟢 اصلاح: تغییر فیلد از weight به ratio
            qty = int(abs(getattr(leg, 'ratio', 1)))
            c_size = getattr(contract, 'contract_size', 1000) or 1000
            K = getattr(contract, 'strike_price', 0.0)
            strike_value = K * c_size * qty

            # کارمزد اعمال فقط و فقط متعلق به دارنده موقعیت خرید (Long) است
            leg_exercise_fee = strike_value * exercise_rate if leg.side == Side.BUY else 0.0

            # مالیات واگذاری سهم (0.5%) فقط برای فروشنده واقعی دارایی پایه
            leg_tax = 0.0
            if include_exercise_tax:
                if (contract.option_type == OptionType.CALL and leg.side == Side.SELL) or \
                   (contract.option_type == OptionType.PUT and leg.side == Side.BUY):
                    leg_tax = strike_value * cls.EXERCISE_TAX_RATE

            total_leg_at_exercise = leg_exercise_fee + leg_tax

            # اعمال مشروط برداری بر اساس وضعیت In-The-Money بودن در سررسید
            if contract.option_type == OptionType.CALL:
                exercise_costs_vector += np.where(price_levels >
                                                  K, total_leg_at_exercise, 0.0)
            elif contract.option_type == OptionType.PUT:
                exercise_costs_vector += np.where(price_levels <
                                                  K, total_leg_at_exercise, 0.0)

        return exercise_costs_vector
