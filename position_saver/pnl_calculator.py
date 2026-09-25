# position_saver/pnl_calculator.py
# -*- coding: utf-8 -*-

from typing import Dict

from position_saver.models import (
    LegType, OptionLeg, StrategyPosition, PositionStatus,
)

# تابع کارمزد از config برنامه اصلی
from config import get_commission_rate


# نرخ پیش‌فرض در صورت نبود کلید در COMMISSION_DICT
_FALLBACK_OPTION_RATE = 0.001
_FALLBACK_STOCK_BUY_RATE = 0.003712
_FALLBACK_STOCK_SELL_RATE = 0.0088


class PositionPnLCalculator:
    """محاسبه‌گر سود/زیان موقعیت‌های استراتژی آپشن"""

    # =====================================================
    # ابزارهای کمکی
    # =====================================================

    @staticmethod
    def _contract_size(leg: OptionLeg) -> int:
        """اندازه قرارداد واقعی"""
        if not leg.is_option:
            return 1
        return leg.contract_size if leg.contract_size > 0 else 1000

    @classmethod
    def _fee_rate(cls, leg: OptionLeg, is_buy: bool) -> float:
        """
        نرخ کارمزد بر اساس نوع دارایی و سمت معامله.
        امضای get_commission_rate در config: (market, asset_type, is_buy)
        """
        if leg.is_option:
            market, asset_type = "tse", "option"
        else:
            market, asset_type = "tse", "stock"

        rate = get_commission_rate(market, asset_type, is_buy)

        # مدیریت حالت None (کلید نامعتبر در COMMISSION_DICT)
        if rate is None:
            if leg.is_option:
                rate = _FALLBACK_OPTION_RATE
            else:
                rate = _FALLBACK_STOCK_BUY_RATE if is_buy \
                    else _FALLBACK_STOCK_SELL_RATE

        return float(rate)

    # =====================================================
    # کارمزدها
    # =====================================================

    @classmethod
    def calculate_leg_entry_fee(cls, leg: OptionLeg) -> float:
        """کارمزد ورود یک لنگه"""
        is_buy = (leg.leg_type == LegType.BUY)
        rate = cls._fee_rate(leg, is_buy)
        cs = cls._contract_size(leg)
        notional = leg.quantity * leg.entry_price * cs
        return notional * rate

    @classmethod
    def calculate_leg_close_fee(cls, leg: OptionLeg, close_price: float) -> float:
        """کارمزد خروج یک لنگه (سمت معامله معکوس می‌شود)"""
        if close_price is None or close_price <= 0:
            return 0.0
        is_buy_on_close = (leg.leg_type == LegType.SELL)
        rate = cls._fee_rate(leg, is_buy_on_close)
        cs = cls._contract_size(leg)
        notional = leg.quantity * close_price * cs
        return notional * rate

    # =====================================================
    # هزینه خالص ورود
    # =====================================================

    @classmethod
    def calculate_net_entry_cost(cls, position: StrategyPosition) -> float:
        """
        هزینه خالص ورود به استراتژی:
            لنگه‌های BUY: هزینه = ارزش + کارمزد
            لنگه‌های SELL: درآمد = ارزش - کارمزد
        مقدار مثبت = هزینه خالص، مقدار منفی = درآمد خالص (کِرِدیت)
        """
        net_cost = 0.0
        for leg in position.legs:
            cs = cls._contract_size(leg)
            leg_val = leg.quantity * leg.entry_price * cs
            fee = leg.entry_fee if leg.entry_fee > 0 \
                else cls.calculate_leg_entry_fee(leg)

            if leg.leg_type == LegType.BUY:
                net_cost += (leg_val + fee)
            else:
                net_cost -= (leg_val - fee)
        return net_cost

    # =====================================================
    # PnL لایو
    # =====================================================

    @classmethod
    def calculate_live_pnl(cls, position: StrategyPosition):
        """
        محاسبه سود/زیان لایو و درصد بازدهی (ROI).
        Returns: (live_pnl: float, live_roi: float)
        """
        live_pnl = 0.0
        net_entry_cost = cls.calculate_net_entry_cost(position)

        for leg in position.legs:
            cs = cls._contract_size(leg)
            curr_price = leg.current_price if leg.current_price > 0 \
                else leg.entry_price
            val_diff = (curr_price - leg.entry_price) * leg.quantity * cs

            if leg.leg_type == LegType.BUY:
                live_pnl += val_diff
            else:
                live_pnl -= val_diff

        base_capital = abs(net_entry_cost) if net_entry_cost != 0 else 1.0
        live_roi = (live_pnl / base_capital) * 100.0
        return live_pnl, live_roi

    # =====================================================
    # PnL محقق‌شده
    # =====================================================

    @classmethod
    def calculate_realized_pnl(cls, position: StrategyPosition):
        """
        محاسبه سود/زیان محقق‌شده برای موقعیت‌های بسته‌شده.
        Returns: (realized_pnl: float, realized_roi: float)
        """
        if position.status == PositionStatus.OPEN:
            return 0.0, 0.0

        net_entry = cls.calculate_net_entry_cost(position)

        net_exit = 0.0
        for leg in position.legs:
            if leg.close_price is None:
                continue
            cs = cls._contract_size(leg)
            val = leg.quantity * leg.close_price * cs
            fee = leg.close_fee if leg.close_fee > 0 \
                else cls.calculate_leg_close_fee(leg, leg.close_price)

            if leg.leg_type == LegType.BUY:
                net_exit += (val - fee)
            else:
                net_exit -= (val + fee)

        realized_pnl = net_exit - net_entry
        base_capital = abs(net_entry) if net_entry != 0 else 1.0
        realized_roi = (realized_pnl / base_capital) * 100.0
        return realized_pnl, realized_roi

    # =====================================================
    # ✅ نکول CALL (جدید)
    # =====================================================

    @classmethod
    def calculate_call_default(
        cls,
        leg: OptionLeg,
        S_T: float,
        exercise_rate: float = 0.0,
    ) -> Dict[str, float]:
        """
        محاسبه مالی نکول یک لگ CALL در روز سررسید.

        فرمول‌ها (طبق ضوابط بورس تهران):
            payment   = (S_T - K) × qty × contract_size
            penalty   = 0.01 × S_T × qty × contract_size
            exercise_fee = exercise_rate × K × qty × contract_size
                          (فقط برای Long Call — خریدار اعمال‌کننده)

        Args:
            leg: لگ CALL (buy یا sell)
            S_T: قیمت پایانی سهم پایه در روز سررسید
            exercise_rate: نرخ کارمزد اعمال (پیش‌فرض 0)

        Returns:
            dict با کلیدهای:
                - valid: bool              — آیا معتبر است (CALL + مقادیر > 0)
                - payment: float           — وجه تسویه نقدی
                - penalty: float           — جریمه ۱٪ نکول
                - exercise_fee: float      — کارمزد اعمال (فقط Long)
                - total_received: float    — مجموع دریافتی (Long)
                - total_paid: float        — مجموع پرداختی (Short)
                - net: float               — خالص (مثبت Long، منفی Short)
                - effective_price: float   — قیمت مؤثر هر سهم
        """
        _empty = {
            "valid": False,
            "payment": 0.0,
            "penalty": 0.0,
            "exercise_fee": 0.0,
            "total_received": 0.0,
            "total_paid": 0.0,
            "net": 0.0,
            "effective_price": 0.0,
        }

        # ✅ فقط CALL
        if not leg.is_call:
            return _empty

        K = leg.strike_price
        qty = leg.quantity
        cs = cls._contract_size(leg)

        if qty <= 0 or cs <= 0 or S_T <= 0 or K <= 0:
            return _empty

        shares = qty * cs

        # وجه تسویه نقدی به جای تحویل سهم
        payment = max(0.0, S_T - K) * shares

        # جریمه ۱٪ نکول
        penalty = 0.01 * S_T * shares

        # کارمزد اعمال (فقط برای Long Call = خریدار اعمال‌کننده)
        exercise_fee = 0.0
        if leg.leg_type == LegType.BUY and exercise_rate > 0:
            exercise_fee = exercise_rate * K * shares

        if leg.leg_type == LegType.BUY:
            # Long Call → من ذی‌نفع
            total_received = payment + penalty
            total_paid = exercise_fee
            net = total_received - total_paid
        else:
            # Short Call → من متضرر
            total_received = 0.0
            total_paid = payment + penalty
            net = -total_paid

        effective_price = (
            abs(net) / shares if shares > 0 else 0.0
        )

        return {
            "valid": True,
            "payment": payment,
            "penalty": penalty,
            "exercise_fee": exercise_fee,
            "total_received": total_received,
            "total_paid": total_paid,
            "net": net,
            "effective_price": effective_price,
        }