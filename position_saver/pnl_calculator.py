# position_saver/pnl_calculator.py
# -*- coding: utf-8 -*-

"""
محاسبات مالی موقعیت‌های استراتژی آپشن.

استانداردهای پیروی‌شده:
    - OCC: Payoff و Max Profit/Loss
    - سمات: کارمزدها و مالیات
    - برنامه‌ی اصلی OptionScanner: همخوانی کامل

منابع حقیقت:
    - SharedAnalytics: سرمایه‌ی درگیر، max_profit، target_roi
    - PositionPnLCalculator: PnL لحظه‌ای و محقق‌شده
"""

from typing import Dict, Tuple, List

from position_saver.models import (
    LegType, OptionLeg, StrategyPosition, PositionStatus,
)
from position_saver.providers import get_commission_rate


# ═══════════════════════════════════════════════════
# قوانین استراتژی‌های استاندارد
# ═══════════════════════════════════════════════════

STRATEGY_REQUIREMENTS = {
    # ─── تک‌لگ ───
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
    "Short Call": {
        "min": 1, "max": 1,
        "fa_name": "شورت کال",
        "composition": [
            {"leg_type": "sell", "option_kind": "CALL",
             "min": 1, "desc": "فروش کال"},
        ],
    },
    "Short Put": {
        "min": 1, "max": 1,
        "fa_name": "شورت پوت",
        "composition": [
            {"leg_type": "sell", "option_kind": "PUT",
             "min": 1, "desc": "فروش پوت"},
        ],
    },

    # ─── اسپرد ───
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

    # ─── پیچیده ───
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

    # ─── آفست ───
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


# ═══════════════════════════════════════════════════
# کلاس اصلی
# ═══════════════════════════════════════════════════

class PositionPnLCalculator:
    """
    محاسبه‌گر سود/زیان موقعیت‌های استراتژی آپشن.

    نکات کلیدی:
        - calculate_live_pnl: از SharedAnalytics استفاده می‌کند.
        - calculate_realized_pnl: از SharedAnalytics استفاده می‌کند.
        - مبنای ROI: SharedAnalytics.calculate_capital_base (OCC + سمات).
        - calculate_call_default: مطابق ضوابط بورس تهران.
        - تسویه نقدی: از cash_settlement_amount مستقیم.
        - validate_strategy: اعتبارسنجی ترکیب لگ‌ها.
    """

    # =====================================================
    # کارمزد (Delegate به SharedAnalytics)
    # =====================================================

    @classmethod
    def calculate_leg_entry_fee(cls, leg: OptionLeg) -> float:
        """کارمزد ورود یک لنگه."""
        from position_saver.shared_analytics import SharedAnalytics
        return SharedAnalytics.calculate_leg_entry_fee(leg)

    @classmethod
    def calculate_leg_close_fee(
        cls, leg: OptionLeg, close_price: float
    ) -> float:
        """کارمزد خروج یک لنگه."""
        from position_saver.shared_analytics import SharedAnalytics
        return SharedAnalytics.calculate_leg_close_fee(leg, close_price)

    @classmethod
    def _estimated_close_fee(cls, leg: OptionLeg) -> float:
        """کارمزد خروج برآوردی."""
        price = leg.current_price if leg.current_price > 0 \
            else leg.entry_price
        return cls.calculate_leg_close_fee(leg, price)

    # =====================================================
    # ✅ PnL سطح لگ — منبع واحد حقیقت
    # =====================================================

    @classmethod
    def calculate_leg_live_pnl(cls, leg: OptionLeg) -> float:
        """
        PnL لحظه‌ای یک لگ.

        شامل:
            - تغییر قیمت
            - کارمزد ورود (اگر ثبت نشده، محاسبه)
            - کارمزد خروج برآوردی
        """
        if leg.is_closed:
            return cls.calculate_leg_realized_pnl(leg)

        cs = leg.effective_contract_size
        curr_price = leg.current_price if leg.current_price > 0 \
            else leg.entry_price
        val_diff = (curr_price - leg.entry_price) * leg.quantity * cs

        entry_fee = leg.entry_fee if leg.entry_fee > 0 \
            else cls.calculate_leg_entry_fee(leg)
        est_close_fee = cls._estimated_close_fee(leg)

        if leg.leg_type == LegType.BUY:
            return val_diff - entry_fee - est_close_fee
        return -val_diff - entry_fee - est_close_fee

    @classmethod
    def calculate_leg_realized_pnl(cls, leg: OptionLeg) -> float:
        """
        PnL محقق‌شده‌ی یک لگ.

        اگر leg.realized_pnl ست شده باشد، اولویت دارد (سازگاری).
        """
        if leg.realized_pnl is not None:
            return float(leg.realized_pnl)

        if not leg.is_closed:
            return 0.0

        cs = leg.effective_contract_size
        try:
            close_price = float(leg.close_price)
        except (TypeError, ValueError):
            return 0.0

        price_diff = (close_price - leg.entry_price) \
            * leg.quantity * cs

        entry_fee = leg.entry_fee if leg.entry_fee > 0 \
            else cls.calculate_leg_entry_fee(leg)
        close_fee = leg.close_fee if leg.close_fee > 0 \
            else cls.calculate_leg_close_fee(leg, close_price)
        fees = entry_fee + close_fee

        if leg.leg_type == LegType.BUY:
            return price_diff - fees
        return -price_diff - fees

    # =====================================================
    # هزینه خالص ورود
    # =====================================================

    @classmethod
    def calculate_net_entry_cost(
        cls, position: StrategyPosition
    ) -> float:
        """هزینه خالص ورود (با احتساب کارمزد ورود)."""
        net_cost = 0.0
        for leg in position.legs:
            cs = leg.effective_contract_size
            leg_val = leg.quantity * leg.entry_price * cs
            fee = leg.entry_fee if leg.entry_fee > 0 \
                else cls.calculate_leg_entry_fee(leg)

            if leg.leg_type == LegType.BUY:
                net_cost += (leg_val + fee)
            else:
                net_cost -= (leg_val - fee)
        return net_cost

    # =====================================================
    # ✅ Capital Base — از SharedAnalytics
    # =====================================================

    @classmethod
    def _get_capital_base(
        cls, position: StrategyPosition
    ) -> float:
        """سرمایه‌ی درگیر — مطابق OCC و سمات."""
        from position_saver.shared_analytics import SharedAnalytics
        return SharedAnalytics.calculate_capital_base(position)

    # =====================================================
    # ✅ حداکثر سود / زیان — از SharedAnalytics
    # =====================================================

    @classmethod
    def calculate_max_profit_at_expiry(
        cls,
        position: StrategyPosition,
        price_target: float = None,
    ):
        """
        حداکثر سود استراتژی در سررسید.

        Returns:
            مبلغ (float) یا None اگر نامحدود.
        """
        from position_saver.shared_analytics import SharedAnalytics
        target = price_target if price_target else (
            position.price_target or None
        )
        return SharedAnalytics.calculate_max_profit_at_expiry(
            position, target)

    @classmethod
    def calculate_max_loss_estimate(
        cls, position: StrategyPosition
    ) -> float:
        """برآورد حداکثر زیان — با payoff grid."""
        from position_saver.shared_analytics import SharedAnalytics

        strikes = []
        for leg in position.legs:
            if leg.is_option and leg.strike_price > 0:
                strikes.append(leg.strike_price)
            elif leg.is_stock and leg.entry_price > 0:
                strikes.append(leg.entry_price)

        if not strikes:
            return abs(cls.calculate_net_entry_cost(position))

        min_K = min(strikes)
        max_K = max(strikes)

        test_points = SharedAnalytics._build_test_points(
            strikes, min_K, max_K, None)

        net_entry = cls.calculate_net_entry_cost(position)
        max_loss = 0.0
        for S_T in test_points:
            payoff = SharedAnalytics._payoff_at_expiry(position, S_T)
            pnl = payoff - net_entry
            if pnl < max_loss:
                max_loss = pnl

        if max_loss >= 0:
            return max(abs(net_entry), 1.0)
        return abs(max_loss)

    # =====================================================
    # ✅ Target ROI — از SharedAnalytics
    # =====================================================

    @classmethod
    def calculate_monthly_target_roi(
        cls,
        position: StrategyPosition,
        price_target: float = None,
    ) -> float:
        """
        محاسبه‌ی ROI ماهانه‌ی هدف.

        فرمول: (max_profit / capital_base) × (30 / D) × 100

        Returns:
            ROI ماهانه (درصد) یا 0 اگر محاسبه ممکن نبود.
        """
        from position_saver.shared_analytics import SharedAnalytics

        max_profit = cls.calculate_max_profit_at_expiry(
            position, price_target)
        if max_profit is None or max_profit <= 0:
            return 0.0

        capital = cls._get_capital_base(position)
        if capital <= 0:
            return 0.0

        D = position.total_days()
        if D <= 0:
            D = 30

        return SharedAnalytics.calculate_monthly_target_roi(
            max_profit=max_profit,
            capital_base=capital,
            days_to_maturity=D,
        )

    @classmethod
    def calculate_dynamic_threshold(
        cls,
        position: StrategyPosition,
    ) -> float:
        """
        آستانه‌ی آلرت پویا برای امروز.

        فرمول: target_monthly × (d / 30)
        """
        from position_saver.shared_analytics import SharedAnalytics

        target = position.target_roi_maturity
        if target <= 0:
            return 0.0

        d = position.days_elapsed()
        return SharedAnalytics.calculate_dynamic_threshold(target, d)

    # =====================================================
    # ✅ PnL لحظه‌ای (سطح position) — Delegate به لگ
    # =====================================================

    @classmethod
    def calculate_live_pnl(
        cls, position: StrategyPosition
    ) -> Tuple[float, float]:
        """محاسبه سود/زیان لایو و ROI."""
        live_pnl = sum(
            cls.calculate_leg_live_pnl(leg)
            for leg in position.legs
        )

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
        """محاسبه سود/زیان محقق‌شده."""
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
            cs = leg.effective_contract_size

            if leg.close_price is not None:
                try:
                    close_price = float(leg.close_price)
                except (TypeError, ValueError):
                    close_price = leg.entry_price
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
        """نسخه با جزئیات."""
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
            cs = leg.effective_contract_size

            entry_fee = leg.entry_fee if leg.entry_fee > 0 \
                else cls.calculate_leg_entry_fee(leg)
            total_entry_fee += entry_fee

            if leg.close_price is not None:
                try:
                    close_price = float(leg.close_price)
                except (TypeError, ValueError):
                    close_price = leg.entry_price
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
        """ارزش ذاتی یک لگ آپشن."""
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
        """محاسبه کل مالی اعمال فیزیکی یک لگ."""
        intrinsic = cls.calculate_exercise_intrinsic(leg, S_T)
        cs = leg.effective_contract_size
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
        """محاسبه مالی نکول یک لگ CALL — مطابق ضوابط بورس تهران."""
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
        cs = leg.effective_contract_size

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
        """محاسبه PnL محقق‌شده برای آفست."""
        temp = position.copy()

        for leg in temp.legs:
            if leg.leg_id in close_prices:
                leg.close_price = float(close_prices[leg.leg_id])
                leg.close_fee = cls.calculate_leg_close_fee(
                    leg, leg.close_price)

        temp.status = PositionStatus.CLOSED

        return cls.calculate_realized_pnl_with_details(temp)

    # =====================================================
    # پیشنهاد نام استراتژی
    # =====================================================

    STANDARD_STRATEGIES = [
        "Long Call",
        "Long Put",
        "Short Call",
        "Short Put",
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
        """پیشنهاد نام استراتژی بر اساس ترکیب لگ‌ها."""
        if not legs:
            return ""

        n_total = len(legs)

        # تک‌لگ
        if n_total == 1:
            leg = legs[0]
            if leg.is_call:
                return "Long Call" if leg.leg_type == LegType.BUY \
                    else "Short Call"
            if leg.is_put:
                return "Long Put" if leg.leg_type == LegType.BUY \
                    else "Short Put"
            return "Single Trade"

        # آفست
        offset_name = cls._detect_offset(legs)
        if offset_name:
            return offset_name

        # دسته‌بندی
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

        # دولگ
        if n_total == 2:
            if len(call_buys) == 1 and len(call_sells) == 1:
                if call_buys[0].strike_price < \
                        call_sells[0].strike_price:
                    return "Bull Call Spread"

            if len(put_buys) == 1 and len(put_sells) == 1:
                if put_buys[0].strike_price > \
                        put_sells[0].strike_price:
                    return "Bear Put Spread"

            if len(stock_buys) == 1 and len(call_sells) == 1:
                return "Covered Call"

            if len(call_buys) == 1 and len(put_buys) == 1:
                if abs(call_buys[0].strike_price
                       - put_buys[0].strike_price) < 0.5:
                    return "Long Straddle"
                else:
                    return "Long Strangle"

        # چهارلگ: Long Box
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
        """تشخیص آفست از ترکیب لگ‌ها."""
        if len(legs) != 2:
            return ""
        if legs[0].symbol != legs[1].symbol:
            return ""
        if abs(legs[0].strike_price - legs[1].strike_price) > 0.5:
            return ""
        if legs[0].expiry_date != legs[1].expiry_date:
            return ""

        buy_count = sum(
            1 for l in legs if l.leg_type == LegType.BUY)
        sell_count = sum(
            1 for l in legs if l.leg_type == LegType.SELL)

        if buy_count != 1 or sell_count != 1:
            return ""

        sorted_legs = sorted(
            legs,
            key=lambda l: l.open_date or "9999/99/99")
        if sorted_legs[0].leg_type == LegType.BUY:
            return "Long Offset"
        return "Short Offset"

    # =====================================================
    # اعتبارسنجی استراتژی
    # =====================================================

    @classmethod
    def validate_strategy(
        cls, strategy_name: str, legs: List[OptionLeg]
    ) -> Dict:
        """اعتبارسنجی ترکیب لگ‌ها با استراتژی انتخاب‌شده."""
        result = {"valid": True, "errors": [], "warnings": []}

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

        for item in req.get("composition", []):
            count = 0
            for leg in legs:
                match_leg_type = (
                    leg.leg_type.value == item["leg_type"])

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

        # قوانین اضافی
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
                if abs(calls[0].strike_price
                       - puts[0].strike_price) > 0.5:
                    result["warnings"].append(
                        "در Long Straddle، قیمت اعمال Call و "
                        "Put باید یکسان باشد.")

        elif extra == "strangle":
            calls = [l for l in legs if l.is_call]
            puts = [l for l in legs if l.is_put]
            if calls and puts:
                if abs(calls[0].strike_price
                       - puts[0].strike_price) < 0.5:
                    result["warnings"].append(
                        "در Long Strangle، قیمت اعمال Call و "
                        "Put باید متفاوت باشد.")

        elif extra == "offset":
            symbols = set(l.symbol for l in legs)
            if len(symbols) > 1:
                result["valid"] = False
                result["errors"].append(
                    f"در آفست، همه‌ی لگ‌ها باید همان نماد "
                    f"باشند (شما {len(symbols)} نماد دارید).")
                return result

            strikes = set(
                l.strike_price for l in legs if l.is_option)
            if len(strikes) > 1:
                result["valid"] = False
                result["errors"].append(
                    f"در آفست، همه‌ی لگ‌ها باید همان "
                    f"قیمت اعمال داشته باشند.")
                return result

            expiries = set(
                l.expiry_date for l in legs
                if l.is_option and l.expiry_date)
            if len(expiries) > 1:
                result["valid"] = False
                result["errors"].append(
                    f"در آفست، همه‌ی لگ‌ها باید همان "
                    f"تاریخ سررسید داشته باشند.")

        # بررسی یکسان بودن سررسید (عمومی)
        if extra != "offset":
            expiries = set()
            for leg in legs:
                if leg.is_option and leg.expiry_date:
                    expiries.add(leg.expiry_date)
            if len(expiries) > 1:
                result["warnings"].append(
                    f"لگ‌ها سررسید متفاوت دارند: "
                    f"{', '.join(sorted(expiries))}.")

        # بررسی یکسان بودن سهم پایه
        import re as _re
        underlyings = set()
        for leg in legs:
            if leg.is_option and leg.symbol:
                s = leg.symbol
                if s.startswith(("ض", "ط")):
                    s = s[1:]
                m = _re.match(r'([^\d]+)', s)
                if m:
                    underlyings.add(m.group(1))
        if len(underlyings) > 1:
            result["valid"] = False
            result["errors"].append(
                f"لگ‌ها سهم پایه‌ی متفاوت دارند: "
                f"{', '.join(sorted(underlyings))}.")

        return result

    # =====================================================
    # ✅ آلرت پویا — چک نهایی
    # =====================================================

    @classmethod
    def check_dynamic_alert(
        cls, position: StrategyPosition
    ) -> Dict:
        """
        بررسی شرط آلرت پویا برای یک position.

        Returns:
            {
                "should_alert": bool,
                "current_roi": float,
                "threshold": float,
                "pace": float,
                "days_elapsed": int,
                "days_total": int,
                "target_monthly": float,
                "reason": str,
            }
        """
        from position_saver.shared_analytics import SharedAnalytics

        result = {
            "should_alert": False,
            "current_roi": 0.0,
            "threshold": 0.0,
            "pace": 0.0,
            "days_elapsed": 0,
            "days_total": 0,
            "target_monthly": 0.0,
            "reason": "",
        }

        # بررسی فعال بودن
        if not position.alert_enabled:
            result["reason"] = "آلرت غیرفعال است"
            return result

        if position.alert_sent:
            result["reason"] = "آلرت قبلاً ارسال شده"
            return result

        if position.target_roi_maturity <= 0:
            result["reason"] = "تارگت تنظیم نشده"
            return result

        # محاسبه PnL لایو
        live_pnl, live_roi = cls.calculate_live_pnl(position)
        result["current_roi"] = round(live_roi, 3)

        # روزها
        d = position.days_elapsed()
        D = position.total_days()
        result["days_elapsed"] = d
        result["days_total"] = D
        result["target_monthly"] = position.target_roi_maturity

        # آستانه
        threshold = SharedAnalytics.calculate_dynamic_threshold(
            position.target_roi_maturity, d)
        result["threshold"] = round(threshold, 3)

        # Pace
        if threshold > 0:
            pace = live_roi / threshold
            result["pace"] = round(pace, 3)

        # بررسی شرط
        if live_roi >= threshold:
            result["should_alert"] = True
            result["reason"] = (
                f"ROI فعلی {live_roi:.2f}% ≥ آستانه "
                f"{threshold:.2f}%")
        else:
            result["reason"] = (
                f"ROI فعلی {live_roi:.2f}% < آستانه "
                f"{threshold:.2f}%")

        return result


__all__ = ["PositionPnLCalculator", "STRATEGY_REQUIREMENTS"]