# position_saver/pnl_calculator.py
# -*- coding: utf-8 -*-

from typing import Dict, Tuple, List

from position_saver.models import (
    LegType, OptionLeg, StrategyPosition, PositionStatus,)

from position_saver.providers import get_commission_rate


# نرخ پیش‌فرض در صورت نبود کلید در COMMISSION_DICT
_FALLBACK_OPTION_RATE = 0.001
_FALLBACK_STOCK_BUY_RATE = 0.003712
_FALLBACK_STOCK_SELL_RATE = 0.0088


# ═══════════════════════════════════════════════════
# قوانین استراتژی‌های استاندارد
# ═══════════════════════════════════════════════════

STRATEGY_REQUIREMENTS = {
    # ─── استراتژی‌های تک‌لگ ───
    "Long Call": {
        "min": 1, "max": 1,
        "fa_name": "لانگ کال",
        "composition": [
            {"leg_type": "buy", "option_kind": "CALL",
             "min": 1, "desc": "خرید کال"},
        ],
    },
    "Long Put": {
        "min": 1, "max": 1,
        "fa_name": "لانگ پوت",
        "composition": [
            {"leg_type": "buy", "option_kind": "PUT",
             "min": 1, "desc": "خرید پوت"},
        ],
    },

    # ─── استراتژی‌های اسپرد ───
    "Bull Call Spread": {
        "min": 2, "max": 2,
        "fa_name": "بول کال اسپرد",
        "composition": [
            {"leg_type": "buy", "option_kind": "CALL",
             "min": 1, "desc": "خرید کال"},
            {"leg_type": "sell", "option_kind": "CALL",
             "min": 1, "desc": "فروش کال"},
        ],
        "extra": "bull_call",
    },
    "Bear Put Spread": {
        "min": 2, "max": 2,
        "fa_name": "بیر پوت اسپرد",
        "composition": [
            {"leg_type": "buy", "option_kind": "PUT",
             "min": 1, "desc": "خرید پوت"},
            {"leg_type": "sell", "option_kind": "PUT",
             "min": 1, "desc": "فروش پوت"},
        ],
        "extra": "bear_put",
    },
    "Covered Call": {
        "min": 2, "max": 2,
        "fa_name": "کاورد کال",
        "composition": [
            {"leg_type": "buy", "option_kind": "STOCK",
             "min": 1, "desc": "خرید سهم پایه"},
            {"leg_type": "sell", "option_kind": "CALL",
             "min": 1, "desc": "فروش کال"},
        ],
    },

    # ─── استراتژی‌های پیچیده ───
    "Long Box": {
        "min": 4, "max": 4,
        "fa_name": "لانگ باکس",
        "composition": [
            {"leg_type": "buy", "option_kind": "CALL",
             "min": 1, "desc": "خرید کال K1"},
            {"leg_type": "sell", "option_kind": "CALL",
             "min": 1, "desc": "فروش کال K2"},
            {"leg_type": "buy", "option_kind": "PUT",
             "min": 1, "desc": "خرید پوت K2"},
            {"leg_type": "sell", "option_kind": "PUT",
             "min": 1, "desc": "فروش پوت K1"},
        ],
        "extra": "long_box",
    },
    "Long Straddle": {
        "min": 2, "max": 2,
        "fa_name": "لانگ استرادل",
        "composition": [
            {"leg_type": "buy", "option_kind": "CALL",
             "min": 1, "desc": "خرید کال"},
            {"leg_type": "buy", "option_kind": "PUT",
             "min": 1, "desc": "خرید پوت"},
        ],
        "extra": "straddle",
    },
    "Long Strangle": {
        "min": 2, "max": 2,
        "fa_name": "لانگ استرانگل",
        "composition": [
            {"leg_type": "buy", "option_kind": "CALL",
             "min": 1, "desc": "خرید کال"},
            {"leg_type": "buy", "option_kind": "PUT",
             "min": 1, "desc": "خرید پوت"},
        ],
        "extra": "strangle",
    },

    # ─── استراتژی‌های جدید (برای آفست) ───
    "Long Offset": {
        "min": 2, "max": 2,
        "fa_name": "آفست لانگ",
        "composition": [
            {"leg_type": "buy", "option_kind": None,
             "min": 1, "desc": "خرید"},
            {"leg_type": "sell", "option_kind": None,
             "min": 1, "desc": "فروش"},
        ],
        "extra": "offset",
    },
    "Short Offset": {
        "min": 2, "max": 2,
        "fa_name": "آفست شورت",
        "composition": [
            {"leg_type": "sell", "option_kind": None,
             "min": 1, "desc": "فروش"},
            {"leg_type": "buy", "option_kind": None,
             "min": 1, "desc": "خرید"},
        ],
        "extra": "offset",
    },
    "Single Trade": {
        "min": 1, "max": 1,
        "fa_name": "معامله‌ی تک",
        "composition": [],
        "extra": None,
    },
}


class PositionPnLCalculator:
    """
    محاسبه‌گر سود/زیان موقعیت‌های استراتژی آپشن.

    نکات کلیدی:
        - calculate_realized_pnl: لگ‌های close_price=None به عنوان
          «باز» در نظر گرفته می‌شوند.
        - calculate_live_pnl: کارمزد خروج برآوردی را لحاظ می‌کند.
        - مبنای ROI: دبیت = هزینه خالص، کردیت = حداکثر زیان.
        - calculate_call_default: کارمزد اعمال یک بار حساب می‌شود.
        - تسویه نقدی: از cash_settlement_amount مستقیم استفاده می‌کند.
        - validate_strategy: اعتبارسنجی ترکیب لگ‌ها.
    """

    # =====================================================
    # ابزارهای کمکی
    # =====================================================

    @staticmethod
    def _contract_size(leg: OptionLeg) -> int:
        """اندازه قرارداد واقعی"""
        return leg.effective_contract_size

    @classmethod
    def _fee_rate(cls, leg: OptionLeg, is_buy: bool) -> float:
        """نرخ کارمزد بر اساس نوع دارایی و سمت معامله"""
        if leg.is_option:
            market, asset_type = "tse", "option"
        else:
            market, asset_type = "tse", "stock"

        try:
            rate = get_commission_rate(market, asset_type, is_buy)
        except Exception:
            rate = None

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
    def calculate_leg_close_fee(
        cls, leg: OptionLeg, close_price: float
    ) -> float:
        """کارمزد خروج یک لنگه"""
        if close_price is None or close_price <= 0:
            return 0.0
        is_buy_on_close = (leg.leg_type == LegType.SELL)
        rate = cls._fee_rate(leg, is_buy_on_close)
        cs = cls._contract_size(leg)
        notional = leg.quantity * close_price * cs
        return notional * rate

    @classmethod
    def _estimated_close_fee(cls, leg: OptionLeg) -> float:
        """کارمزد خروج برآوردی"""
        price = leg.current_price if leg.current_price > 0 \
            else leg.entry_price
        return cls.calculate_leg_close_fee(leg, price)

    # =====================================================
    # هزینه خالص ورود
    # =====================================================

    @classmethod
    def calculate_net_entry_cost(
        cls, position: StrategyPosition
    ) -> float:
        """هزینه خالص ورود به استراتژی"""
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
    # حداکثر زیان — با payoff grid
    # =====================================================

    @classmethod
    def _payoff_at_expiry(
        cls, position: StrategyPosition, S_T: float
    ) -> float:
        """ارزش موقعیت در سررسید به ازای S_T"""
        total = 0.0
        for leg in position.legs:
            cs = cls._contract_size(leg)
            qty = leg.quantity

            if leg.is_stock:
                value = S_T * qty * 1
            elif leg.is_call:
                intrinsic = max(0.0, S_T - leg.strike_price)
                value = intrinsic * qty * cs
            elif leg.is_put:
                intrinsic = max(0.0, leg.strike_price - S_T)
                value = intrinsic * qty * cs
            else:
                value = 0.0

            if leg.leg_type == LegType.BUY:
                total += value
            else:
                total -= value

        return total

    @classmethod
    def calculate_max_loss_estimate(
        cls, position: StrategyPosition
    ) -> float:
        """برآورد حداکثر زیان — با payoff grid"""
        strikes = []
        for leg in position.legs:
            if leg.is_option and leg.strike_price > 0:
                strikes.append(leg.strike_price)
            elif leg.is_stock and leg.entry_price > 0:
                strikes.append(leg.entry_price)

        if not strikes:
            return abs(cls.calculate_net_entry_cost(position))

        min_strike = min(strikes)
        max_strike = max(strikes)

        test_points = [
            0.0,
            min_strike * 0.5,
            *strikes,
            max_strike * 1.5,
            max_strike * 3.0,
            max_strike * 10.0,
        ]

        sorted_strikes = sorted(set(strikes))
        for i in range(len(sorted_strikes) - 1):
            mid = (sorted_strikes[i] + sorted_strikes[i + 1]) / 2
            test_points.append(mid)

        test_points = sorted(set(test_points))

        net_entry = cls.calculate_net_entry_cost(position)
        max_loss = 0.0
        for S_T in test_points:
            payoff = cls._payoff_at_expiry(position, S_T)
            pnl = payoff - net_entry
            if pnl < max_loss:
                max_loss = pnl

        if max_loss >= 0:
            return max(abs(net_entry), 1.0)

        return abs(max_loss)

    # =====================================================
    # مبنای سرمایه
    # =====================================================

    @classmethod
    def _get_capital_base(
        cls, position: StrategyPosition
    ) -> float:
        """مبنای سرمایه برای ROI"""
        net_cost = cls.calculate_net_entry_cost(position)

        if net_cost > 0:
            return net_cost

        max_loss = cls.calculate_max_loss_estimate(position)
        if max_loss > 0:
            return max_loss

        return abs(net_cost) if net_cost != 0 else 1.0

    # =====================================================
    # PnL لایو
    # =====================================================

    @classmethod
    def calculate_live_pnl(
        cls, position: StrategyPosition
    ) -> Tuple[float, float]:
        """محاسبه سود/زیان لایو و ROI"""
        live_pnl = 0.0

        for leg in position.legs:
            cs = cls._contract_size(leg)
            curr_price = leg.current_price if leg.current_price > 0 \
                else leg.entry_price
            val_diff = (curr_price - leg.entry_price) * \
                leg.quantity * cs
            entry_fee = leg.entry_fee if leg.entry_fee > 0 \
                else cls.calculate_leg_entry_fee(leg)
            est_close_fee = cls._estimated_close_fee(leg)

            if leg.leg_type == LegType.BUY:
                live_pnl += val_diff - entry_fee - est_close_fee
            else:
                live_pnl -= val_diff + entry_fee + est_close_fee

        base_capital = cls._get_capital_base(position)
        live_roi = (live_pnl / base_capital) * 100.0 \
            if base_capital > 0 else 0.0

        return live_pnl, live_roi

    # =====================================================
    # PnL محقق‌شده
    # =====================================================

    @classmethod
    def calculate_realized_pnl(
        cls, position: StrategyPosition
    ) -> Tuple[float, float]:
        """محاسبه سود/زیان محقق‌شده"""
        if position.status == PositionStatus.OPEN:
            return 0.0, 0.0

        # تسویه نقدی
        if position.status == PositionStatus.CASH_SETTLED:
            if position.cash_settlement_amount:
                net_entry = cls.calculate_net_entry_cost(position)
                realized_pnl = (
                    position.cash_settlement_amount - net_entry)
                base_capital = cls._get_capital_base(position)
                realized_roi = (realized_pnl / base_capital) * 100.0 \
                    if base_capital > 0 else 0.0
                return realized_pnl, realized_roi

        # مسیر عادی
        net_entry = cls.calculate_net_entry_cost(position)
        net_exit = 0.0

        for leg in position.legs:
            cs = cls._contract_size(leg)

            if leg.close_price is not None:
                close_price = leg.close_price
                fee = leg.close_fee if leg.close_fee > 0 \
                    else cls.calculate_leg_close_fee(
                        leg, close_price)
            else:
                close_price = leg.current_price \
                    if leg.current_price > 0 else leg.entry_price
                fee = cls._estimated_close_fee(leg)

            val = leg.quantity * close_price * cs

            if leg.leg_type == LegType.BUY:
                net_exit += (val - fee)
            else:
                net_exit -= (val + fee)

        realized_pnl = net_exit - net_entry
        base_capital = cls._get_capital_base(position)
        realized_roi = (realized_pnl / base_capital) * 100.0 \
            if base_capital > 0 else 0.0

        return realized_pnl, realized_roi

    @classmethod
    def calculate_realized_pnl_with_details(
        cls, position: StrategyPosition
    ) -> Dict[str, float]:
        """نسخه با جزئیات"""
        # تسویه نقدی
        if position.status == PositionStatus.CASH_SETTLED \
                and position.cash_settlement_amount:
            net_entry = cls.calculate_net_entry_cost(position)
            capital_base = cls._get_capital_base(position)
            realized_pnl = (
                position.cash_settlement_amount - net_entry)
            realized_roi = (realized_pnl / capital_base) * 100.0 \
                if capital_base > 0 else 0.0
            return {
                "net_entry": net_entry,
                "net_exit": position.cash_settlement_amount,
                "realized_pnl": realized_pnl,
                "realized_roi": realized_roi,
                "capital_base": capital_base,
                "total_close_fee": 0.0,
                "total_entry_fee": 0.0,
            }

        net_entry = cls.calculate_net_entry_cost(position)
        capital_base = cls._get_capital_base(position)

        net_exit = 0.0
        total_close_fee = 0.0
        total_entry_fee = 0.0

        for leg in position.legs:
            cs = cls._contract_size(leg)

            entry_fee = leg.entry_fee if leg.entry_fee > 0 \
                else cls.calculate_leg_entry_fee(leg)
            total_entry_fee += entry_fee

            if leg.close_price is not None:
                close_price = leg.close_price
                fee = leg.close_fee if leg.close_fee > 0 \
                    else cls.calculate_leg_close_fee(
                        leg, close_price)
            else:
                close_price = leg.current_price \
                    if leg.current_price > 0 else leg.entry_price
                fee = cls._estimated_close_fee(leg)

            total_close_fee += fee
            val = leg.quantity * close_price * cs

            if leg.leg_type == LegType.BUY:
                net_exit += (val - fee)
            else:
                net_exit -= (val + fee)

        realized_pnl = net_exit - net_entry
        realized_roi = (realized_pnl / capital_base) * 100.0 \
            if capital_base > 0 else 0.0

        return {
            "net_entry": net_entry,
            "net_exit": net_exit,
            "realized_pnl": realized_pnl,
            "realized_roi": realized_roi,
            "capital_base": capital_base,
            "total_close_fee": total_close_fee,
            "total_entry_fee": total_entry_fee,
        }

    # =====================================================
    # اعمال فیزیکی
    # =====================================================

    @classmethod
    def calculate_exercise_intrinsic(
        cls, leg: OptionLeg, S_T: float
    ) -> float:
        """ارزش ذاتی یک لگ آپشن"""
        if not leg.is_option:
            return S_T

        K = leg.strike_price
        if leg.is_call:
            return max(0.0, S_T - K)
        elif leg.is_put:
            return max(0.0, K - S_T)
        return 0.0

    @classmethod
    def calculate_exercise_total(
        cls, leg: OptionLeg, S_T: float
    ) -> Dict[str, float]:
        """محاسبه کل مالی اعمال فیزیکی یک لگ"""
        intrinsic = cls.calculate_exercise_intrinsic(leg, S_T)
        cs = cls._contract_size(leg)
        total_value = intrinsic * leg.quantity * cs

        return {
            "intrinsic_per_share": intrinsic,
            "total_value": total_value,
            "is_itm": intrinsic > 0,
        }

    # =====================================================
    # نکول CALL
    # =====================================================

    @classmethod
    def calculate_call_default(
        cls,
        leg: OptionLeg,
        S_T: float,
        exercise_rate: float = 0.0,
        is_self_default: bool = False,
    ) -> Dict[str, float]:
        """محاسبه مالی نکول یک لگ CALL"""
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

        if not leg.is_call:
            return _empty

        K = leg.strike_price
        qty = leg.quantity
        cs = cls._contract_size(leg)

        if qty <= 0 or cs <= 0 or S_T <= 0 or K <= 0:
            return _empty

        shares = qty * cs
        payment = max(0.0, S_T - K) * shares
        penalty = 0.01 * S_T * shares

        exercise_fee = 0.0
        if leg.leg_type == LegType.BUY and exercise_rate > 0:
            exercise_fee = exercise_rate * K * shares

        if is_self_default:
            i_am_beneficiary = (leg.leg_type == LegType.SELL)
        else:
            i_am_beneficiary = (leg.leg_type == LegType.BUY)

        if i_am_beneficiary:
            total_received = payment + penalty
            total_paid = 0.0
            net = total_received
        else:
            total_received = 0.0
            total_paid = payment + penalty
            net = -total_paid

        effective_price = abs(net) / shares if shares > 0 else 0.0

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

    # =====================================================
    # آفست
    # =====================================================

    @classmethod
    def calculate_offset_pnl(
        cls,
        position: StrategyPosition,
        close_prices: Dict[str, float],
    ) -> Dict[str, float]:
        """محاسبه PnL محقق‌شده برای آفست"""
        temp = position.copy()

        for leg in temp.legs:
            if leg.leg_id in close_prices:
                leg.close_price = float(close_prices[leg.leg_id])
                leg.close_fee = cls.calculate_leg_close_fee(
                    leg, leg.close_price)

        temp.status = PositionStatus.CLOSED

        return cls.calculate_realized_pnl_with_details(temp)

    # =====================================================
    # بررسی اعتبار قیمت‌ها
    # =====================================================

    @classmethod
    def has_stale_prices(
        cls, position: StrategyPosition
    ) -> bool:
        """آیا موقعیت لگ‌هایی با قیمت کهنه دارد؟"""
        for leg in position.legs:
            if leg.current_price <= 0:
                return True
        return False

    @classmethod
    def count_stale_legs(
        cls, position: StrategyPosition
    ) -> int:
        """تعداد لگ‌های با قیمت کهنه"""
        count = 0
        for leg in position.legs:
            if leg.current_price <= 0:
                count += 1
        return count

    # =====================================================
    # پیشنهاد نام استراتژی
    # =====================================================

    STANDARD_STRATEGIES = [
        "Long Call",
        "Long Put",
        "Bull Call Spread",
        "Bear Put Spread",
        "Covered Call",
        "Long Box",
        "Long Straddle",
        "Long Strangle",
        "Long Offset",
        "Short Offset",
        "Single Trade",
    ]

    @classmethod
    def suggest_strategy_name(
        cls, legs: List[OptionLeg]
    ) -> str:
        """
        پیشنهاد نام استراتژی بر اساس ترکیب لگ‌ها.

        ترتیب اولویت:
            1. Single Trade (تک‌لگ)
            2. Offset (دولگ متقارن)
            3. استراتژی‌های اسپرد
        """
        if not legs:
            return ""

        n_total = len(legs)

        # ─── تک‌لگ ───
        if n_total == 1:
            return "Single Trade"

        # ─── تشخیص Offset ───
        offset_name = cls._detect_offset(legs)
        if offset_name:
            return offset_name

        # ─── بقیه ───
        call_buys = [l for l in legs
                     if l.is_call and l.leg_type == LegType.BUY]
        call_sells = [l for l in legs
                      if l.is_call and l.leg_type == LegType.SELL]
        put_buys = [l for l in legs
                    if l.is_put and l.leg_type == LegType.BUY]
        put_sells = [l for l in legs
                     if l.is_put and l.leg_type == LegType.SELL]
        stock_buys = [l for l in legs
                      if l.is_stock and l.leg_type == LegType.BUY]

        # ─── دولگ: Bull Call Spread ───
        if n_total == 2:
            if len(call_buys) == 1 and len(call_sells) == 1:
                if call_buys[0].strike_price < \
                        call_sells[0].strike_price:
                    return "Bull Call Spread"

            # Bear Put Spread
            if len(put_buys) == 1 and len(put_sells) == 1:
                if put_buys[0].strike_price > \
                        put_sells[0].strike_price:
                    return "Bear Put Spread"

            # Covered Call
            if len(stock_buys) == 1 and len(call_sells) == 1:
                return "Covered Call"

            # Long Straddle
            if len(call_buys) == 1 and len(put_buys) == 1:
                if call_buys[0].strike_price == \
                        put_buys[0].strike_price:
                    return "Long Straddle"

            # Long Strangle
            if len(call_buys) == 1 and len(put_buys) == 1:
                if call_buys[0].strike_price != \
                        put_buys[0].strike_price:
                    return "Long Strangle"

        # ─── چهارلگ: Long Box ───
        if n_total == 4:
            if (len(call_buys) == 1 and len(call_sells) == 1
                    and len(put_buys) == 1 and len(put_sells) == 1):
                K1_call = call_buys[0].strike_price
                K2_call = call_sells[0].strike_price
                K2_put = put_buys[0].strike_price
                K1_put = put_sells[0].strike_price
                if (K1_call < K2_call
                        and abs(K2_call - K2_put) < 1
                        and abs(K1_call - K1_put) < 1):
                    return "Long Box"

        return ""

    @classmethod
    def _detect_offset(cls, legs: List[OptionLeg]) -> str:
        """
        تشخیص آفست از ترکیب لگ‌ها.

        Returns:
            "Long Offset" یا "Short Offset" یا ""
        """
        if len(legs) != 2:
            return ""

        # بررسی همان نماد
        if legs[0].symbol != legs[1].symbol:
            return ""

        # بررسی همان strike
        if abs(legs[0].strike_price - legs[1].strike_price) > 1:
            return ""

        # بررسی همان expiry
        if legs[0].expiry_date != legs[1].expiry_date:
            return ""

        # بررسی جهت مخالف
        buy_count = sum(
            1 for l in legs if l.leg_type == LegType.BUY)
        sell_count = sum(
            1 for l in legs if l.leg_type == LegType.SELL)

        if buy_count != 1 or sell_count != 1:
            return ""

        # کدام اول BUY بود؟
        sorted_legs = sorted(
            legs,
            key=lambda l: l.open_date or "9999/99/99")
        if sorted_legs[0].leg_type == LegType.BUY:
            return "Long Offset"
        else:
            return "Short Offset"

    # =====================================================
    # اعتبارسنجی استراتژی
    # =====================================================

    @classmethod
    def validate_strategy(
        cls, strategy_name: str, legs: List[OptionLeg]
    ) -> Dict:
        """
        اعتبارسنجی ترکیب لگ‌ها با استراتژی انتخاب‌شده.

        Returns:
            dict با کلیدهای:
                - valid: bool
                - errors: List[str]
                - warnings: List[str]
        """
        result = {"valid": True, "errors": [], "warnings": []}

        # سفارشی — همیشه معتبر
        if strategy_name in ("سفارشی", "Custom", "custom", ""):
            return result

        req = STRATEGY_REQUIREMENTS.get(strategy_name)
        if req is None:
            result["warnings"].append(
                f"استراتژی «{strategy_name}» در لیست "
                f"استاندارد نیست.")
            return result

        n = len(legs)
        fa_name = req.get("fa_name", strategy_name)

        # ─── تعداد لگ ───
        if n < req["min"]:
            result["valid"] = False
            result["errors"].append(
                f"استراتژی «{fa_name}» نیاز به حداقل "
                f"{req['min']} لگ دارد (شما {n} لگ انتخاب "
                f"کرده‌اید).")
            return result

        if n > req["max"]:
            result["valid"] = False
            result["errors"].append(
                f"استراتژی «{fa_name}» حداکثر {req['max']} لگ "
                f"می‌پذیرد (شما {n} لگ انتخاب کرده‌اید).")
            return result

        # ─── ترکیب لگ‌ها ───
        for item in req.get("composition", []):
            count = 0
            for leg in legs:
                match_leg_type = (
                    leg.leg_type.value == item["leg_type"])

                # اگر option_kind=None باشد، همه‌ی انواع قبول
                if item.get("option_kind") is None:
                    match_kind = True
                else:
                    match_kind = (
                        leg.option_kind.name == item["option_kind"])

                if match_leg_type and match_kind:
                    count += 1

            if count < item.get("min", 1):
                result["valid"] = False
                result["errors"].append(
                    f"استراتژی «{fa_name}» نیاز به حداقل "
                    f"{item.get('min', 1)} × {item['desc']} دارد "
                    f"(شما {count} دارید).")

        if not result["valid"]:
            return result

        # ─── قوانین اضافی ───
        extra = req.get("extra")

        if extra == "bull_call":
            buys = [l for l in legs
                    if l.leg_type == LegType.BUY and l.is_call]
            sells = [l for l in legs
                     if l.leg_type == LegType.SELL and l.is_call]
            if buys and sells:
                if buys[0].strike_price >= sells[0].strike_price:
                    result["valid"] = False
                    result["errors"].append(
                        f"در Bull Call Spread، قیمت اعمال خرید "
                        f"({buys[0].strike_price:,.0f}) باید "
                        f"کمتر از قیمت اعمال فروش "
                        f"({sells[0].strike_price:,.0f}) باشد.")

        elif extra == "bear_put":
            buys = [l for l in legs
                    if l.leg_type == LegType.BUY and l.is_put]
            sells = [l for l in legs
                     if l.leg_type == LegType.SELL and l.is_put]
            if buys and sells:
                if buys[0].strike_price <= sells[0].strike_price:
                    result["valid"] = False
                    result["errors"].append(
                        f"در Bear Put Spread، قیمت اعمال خرید "
                        f"({buys[0].strike_price:,.0f}) باید "
                        f"بیشتر از قیمت اعمال فروش "
                        f"({sells[0].strike_price:,.0f}) باشد.")

        elif extra == "straddle":
            calls = [l for l in legs if l.is_call]
            puts = [l for l in legs if l.is_put]
            if calls and puts:
                if calls[0].strike_price != puts[0].strike_price:
                    result["warnings"].append(
                        "در Long Straddle، قیمت اعمال Call و "
                        "Put باید یکسان باشد.")

        elif extra == "strangle":
            calls = [l for l in legs if l.is_call]
            puts = [l for l in legs if l.is_put]
            if calls and puts:
                if calls[0].strike_price == puts[0].strike_price:
                    result["warnings"].append(
                        "در Long Strangle، قیمت اعمال Call و "
                        "Put باید متفاوت باشد.")

        elif extra == "long_box":
            call_buys = [l for l in legs
                         if l.is_call
                         and l.leg_type == LegType.BUY]
            call_sells = [l for l in legs
                          if l.is_call
                          and l.leg_type == LegType.SELL]
            put_buys = [l for l in legs
                        if l.is_put
                        and l.leg_type == LegType.BUY]
            put_sells = [l for l in legs
                         if l.is_put
                         and l.leg_type == LegType.SELL]
            if call_buys and call_sells and put_buys and put_sells:
                K1_call = call_buys[0].strike_price
                K2_call = call_sells[0].strike_price
                K2_put = put_buys[0].strike_price
                K1_put = put_sells[0].strike_price
                if not (K1_call < K2_call):
                    result["valid"] = False
                    result["errors"].append(
                        f"در Long Box، باید K1_call < K2_call "
                        f"باشد ({K1_call:,.0f} < {K2_call:,.0f})")
                if abs(K2_call - K2_put) > 1:
                    result["warnings"].append(
                        f"در Long Box، K2_call "
                        f"({K2_call:,.0f}) و K2_put "
                        f"({K2_put:,.0f}) باید یکسان باشند.")
                if abs(K1_call - K1_put) > 1:
                    result["warnings"].append(
                        f"در Long Box، K1_call "
                        f"({K1_call:,.0f}) و K1_put "
                        f"({K1_put:,.0f}) باید یکسان باشند.")

        elif extra == "offset":
            # بررسی همان نماد
            symbols = set(l.symbol for l in legs)
            if len(symbols) > 1:
                result["valid"] = False
                result["errors"].append(
                    f"در آفست، همه‌ی لگ‌ها باید همان نماد "
                    f"باشند (شما {len(symbols)} نماد دارید).")
                return result

            # بررسی همان strike
            strikes = set(
                l.strike_price for l in legs if l.is_option)
            if len(strikes) > 1:
                result["valid"] = False
                result["errors"].append(
                    f"در آفست، همه‌ی لگ‌ها باید همان "
                    f"قیمت اعمال داشته باشند.")
                return result

            # بررسی همان expiry
            expiries = set(
                l.expiry_date for l in legs
                if l.is_option and l.expiry_date)
            if len(expiries) > 1:
                result["valid"] = False
                result["errors"].append(
                    f"در آفست، همه‌ی لگ‌ها باید همان "
                    f"تاریخ سررسید داشته باشند.")

        # ─── بررسی یکسان بودن سررسید (عمومی) ───
        if extra != "offset":
            expiries = set()
            for leg in legs:
                if leg.is_option and leg.expiry_date:
                    expiries.add(leg.expiry_date)
            if len(expiries) > 1:
                result["warnings"].append(
                    f"لگ‌ها سررسید متفاوت دارند: "
                    f"{', '.join(sorted(expiries))}.")

        # ─── بررسی یکسان بودن سهم پایه ───
        import re
        underlyings = set()
        for leg in legs:
            if leg.is_option and leg.symbol:
                s = leg.symbol
                if s.startswith(("ض", "ط")):
                    s = s[1:]
                m = re.match(r'([^\d]+)', s)
                if m:
                    underlyings.add(m.group(1))
        if len(underlyings) > 1:
            result["valid"] = False
            result["errors"].append(
                f"لگ‌ها سهم پایه‌ی متفاوت دارند: "
                f"{', '.join(sorted(underlyings))}.")

        return result