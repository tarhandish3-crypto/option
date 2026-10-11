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


class PositionPnLCalculator:
    """
    محاسبه‌گر سود/زیان موقعیت‌های استراتژی آپشن.

    نکات کلیدی این نسخه:
        - calculate_realized_pnl: لگ‌های close_price=None به عنوان «باز» در نظر
          گرفته می‌شوند و از محاسبه حذف نمی‌شوند.
        - calculate_live_pnl: کارمزد خروج برآوردی را لحاظ می‌کند تا با realized
          هم‌پایه باشد.
        - مبنای ROI: برای استراتژی‌های دبیت = هزینه خالص، برای کردیت = حداکثر
          زیان یا وجه تضمین برآوردی.
        - calculate_call_default: کارمزد اعمال فقط یک بار در net حساب می‌شود.
        - تسویه نقدی: از cash_settlement_amount مستقیماً استفاده می‌شود.
        - نکول: پارامتر is_self_default به صراحت تعیین می‌کند چه کسی نکول کرده.
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
        """
        نرخ کارمزد بر اساس نوع دارایی و سمت معامله.
        از main.get_commission_rate استفاده می‌کند.
        """
        if leg.is_option:
            market, asset_type = "tse", "option"
        else:
            market, asset_type = "tse", "stock"

        try:
            rate = get_commission_rate(market, asset_type, is_buy)
        except Exception:
            rate = None

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
    def calculate_leg_close_fee(
        cls, leg: OptionLeg, close_price: float
    ) -> float:
        """کارمزد خروج یک لنگه (سمت معامله معکوس می‌شود)"""
        if close_price is None or close_price <= 0:
            return 0.0
        is_buy_on_close = (leg.leg_type == LegType.SELL)
        rate = cls._fee_rate(leg, is_buy_on_close)
        cs = cls._contract_size(leg)
        notional = leg.quantity * close_price * cs
        return notional * rate

    @classmethod
    def _estimated_close_fee(cls, leg: OptionLeg) -> float:
        """
        کارمزد خروج برآوردی بر اساس قیمت فعلی.
        برای هم‌پایه‌سازی live_pnl با realized_pnl.
        """
        price = leg.current_price if leg.current_price > 0 \
            else leg.entry_price
        return cls.calculate_leg_close_fee(leg, price)

    # =====================================================
    # هزینه خالص ورود
    # =====================================================

    @classmethod
    def calculate_net_entry_cost(cls, position: StrategyPosition) -> float:
        """
        هزینه خالص ورود به استراتژی:
            لنگه‌های BUY: هزینه = ارزش + کارمزد
            لنگه‌های SELL: درآمد = ارزش - کارمزد

        مقدار مثبت = هزینه خالص (دبیت)، مقدار منفی = درآمد خالص (کردیت)
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
    # حداکثر زیان — با payoff grid
    # =====================================================

    @classmethod
    def _payoff_at_expiry(
        cls, position: StrategyPosition, S_T: float
    ) -> float:
        """
        محاسبه‌ی ارزش موقعیت در سررسید به ازای قیمت پایه‌ی S_T.
        (شامل ارزش سهم و ارزش ذاتی آپشن‌ها)
        """
        total = 0.0
        for leg in position.legs:
            cs = cls._contract_size(leg)
            qty = leg.quantity

            if leg.is_stock:
                # سهم پایه
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
        """
        برآورد حداکثر زیان ممکن برای استراتژی — با payoff grid.

        روش:
            ۱. نقاط کلیدی: strike ها + مرزهای بالا/پایین
            ۲. محاسبه‌ی PnL برای هر نقطه
            ۳. حداکثر زیان = min(PnL)
            ۴. اگر زیان نامحدود باشد (Short Call بدون پوشش)،
               از نقاط دورتر استفاده می‌کنیم.

        این روش دقیق‌تر از heuristic قبلی است.
        """
        # نقاط کلیدی: strike ها + مرزها
        strikes = []
        for leg in position.legs:
            if leg.is_option and leg.strike_price > 0:
                strikes.append(leg.strike_price)
            elif leg.is_stock and leg.entry_price > 0:
                strikes.append(leg.entry_price)

        if not strikes:
            # بدون strike — از هزینه خالص استفاده کن
            return abs(cls.calculate_net_entry_cost(position))

        min_strike = min(strikes)
        max_strike = max(strikes)

        # نقاط آزمون: 0, half, strikes, midpoints, double
        test_points = [
            0.0,
            min_strike * 0.5,
            *strikes,
            max_strike * 1.5,
            max_strike * 3.0,    # برای Short Call
            max_strike * 10.0,   # برای اطمینان
        ]

        # midpoints بین strike ها
        sorted_strikes = sorted(set(strikes))
        for i in range(len(sorted_strikes) - 1):
            mid = (sorted_strikes[i] + sorted_strikes[i + 1]) / 2
            test_points.append(mid)

        test_points = sorted(set(test_points))

        # محاسبه‌ی PnL در هر نقطه (با احتساب هزینه ورود)
        net_entry = cls.calculate_net_entry_cost(position)
        max_loss = 0.0
        for S_T in test_points:
            payoff = cls._payoff_at_expiry(position, S_T)
            pnl = payoff - net_entry
            if pnl < max_loss:
                max_loss = pnl

        # اگر هیچ زیانی نبود، حداقل هزینه خالص
        if max_loss >= 0:
            return max(abs(net_entry), 1.0)

        return abs(max_loss)

    # =====================================================
    # مبنای سرمایه برای ROI
    # =====================================================

    @classmethod
    def _get_capital_base(cls, position: StrategyPosition) -> float:
        """
        مبنای سرمایه برای محاسبه ROI.

        قواعد:
            - اگر هزینه خالص (دبیت) > 0: مبنای = هزینه خالص
            - اگر هزینه خالص (کردیت) < 0: مبنای = برآورد حداکثر زیان
            - اگر هزینه خالص نزدیک صفر: مبنای = حداکثر زیان برآوردی
        """
        net_cost = cls.calculate_net_entry_cost(position)

        # اگر دبیت است، همان هزینه خالص
        if net_cost > 0:
            return net_cost

        # اگر کردیت است، از برآورد حداکثر زیان استفاده کن
        max_loss = cls.calculate_max_loss_estimate(position)
        if max_loss > 0:
            return max_loss

        # فال‌بک: حداقل ۱
        return abs(net_cost) if net_cost != 0 else 1.0

    # =====================================================
    # PnL لایو
    # =====================================================

    @classmethod
    def calculate_live_pnl(
        cls, position: StrategyPosition
    ) -> Tuple[float, float]:
        """
        محاسبه سود/زیان لایو و درصد بازدهی (ROI).

        Returns: (live_pnl: float, live_roi: float)
        """
        live_pnl = 0.0

        for leg in position.legs:
            cs = cls._contract_size(leg)

            # قیمت فعلی: اگر صفر بود، از entry_price
            curr_price = leg.current_price if leg.current_price > 0 \
                else leg.entry_price

            # سود/زیان ارزش
            val_diff = (curr_price - leg.entry_price) * \
                leg.quantity * cs

            # کارمزد ورود (اگر ذخیره نشده، محاسبه)
            entry_fee = leg.entry_fee if leg.entry_fee > 0 \
                else cls.calculate_leg_entry_fee(leg)

            # کارمزد خروج برآوردی
            est_close_fee = cls._estimated_close_fee(leg)

            if leg.leg_type == LegType.BUY:
                live_pnl += val_diff - entry_fee - est_close_fee
            else:
                live_pnl -= val_diff + entry_fee + est_close_fee

        base_capital = cls._get_capital_base(position)
        live_roi = (live_pnl / base_capital) * 100.0 if base_capital > 0 \
            else 0.0

        return live_pnl, live_roi

    # =====================================================
    # PnL محقق‌شده
    # =====================================================

    @classmethod
    def calculate_realized_pnl(
        cls, position: StrategyPosition
    ) -> Tuple[float, float]:
        """
        محاسبه سود/زیان محقق‌شده برای موقعیت‌های بسته‌شده.

        ✅ اصلاح باگ تسویه نقدی:
            اگر status == CASH_SETTLED و cash_settlement_amount > 0،
            مستقیماً از آن استفاده می‌شود (بدون توزیع روی close_price).

        Returns: (realized_pnl: float, realized_roi: float)
        """
        if position.status == PositionStatus.OPEN:
            return 0.0, 0.0

        # ✅ تسویه نقدی — استفاده مستقیم از cash_settlement_amount
        if position.status == PositionStatus.CASH_SETTLED:
            if position.cash_settlement_amount:
                net_entry = cls.calculate_net_entry_cost(position)
                realized_pnl = position.cash_settlement_amount - net_entry
                base_capital = cls._get_capital_base(position)
                realized_roi = (realized_pnl / base_capital) * 100.0 \
                    if base_capital > 0 else 0.0
                return realized_pnl, realized_roi

        # مسیر عادی
        net_entry = cls.calculate_net_entry_cost(position)

        net_exit = 0.0
        for leg in position.legs:
            cs = cls._contract_size(leg)

            # اگر بسته نشده، از قیمت فعلی استفاده کن
            if leg.close_price is not None:
                close_price = leg.close_price
                fee = leg.close_fee if leg.close_fee > 0 \
                    else cls.calculate_leg_close_fee(leg, close_price)
            else:
                close_price = leg.current_price if leg.current_price > 0 \
                    else leg.entry_price
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
        """
        نسخه با جزئیات — برای دیالوگ‌ها و گزارش‌ها.

        Returns:
            dict با کلیدهای:
                - net_entry: هزینه خالص ورود
                - net_exit: ارزش خالص خروج
                - realized_pnl: سود/زیان محقق‌شده
                - realized_roi: بازدهی
                - capital_base: مبنای ROI
                - total_close_fee: مجموع کارمزد خروج
                - total_entry_fee: مجموع کارمزد ورود
        """
        # ✅ تسویه نقدی
        if position.status == PositionStatus.CASH_SETTLED \
                and position.cash_settlement_amount:
            net_entry = cls.calculate_net_entry_cost(position)
            capital_base = cls._get_capital_base(position)
            realized_pnl = position.cash_settlement_amount - net_entry
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

        # مسیر عادی
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
                    else cls.calculate_leg_close_fee(leg, close_price)
            else:
                close_price = leg.current_price if leg.current_price > 0 \
                    else leg.entry_price
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
    # اعمال فیزیکی — ارزش ذاتی
    # =====================================================

    @classmethod
    def calculate_exercise_intrinsic(
        cls, leg: OptionLeg, S_T: float
    ) -> float:
        """
        ارزش ذاتی یک لگ آپشن در روز اعمال.
        """
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
        """
        محاسبه کل مالی اعمال فیزیکی یک لگ.
        """
        intrinsic = cls.calculate_exercise_intrinsic(leg, S_T)
        cs = cls._contract_size(leg)
        total_value = intrinsic * leg.quantity * cs

        return {
            "intrinsic_per_share": intrinsic,
            "total_value": total_value,
            "is_itm": intrinsic > 0,
        }

    # =====================================================
    # نکول CALL — با پارامتر is_self_default
    # =====================================================

    @classmethod
    def calculate_call_default(
        cls,
        leg: OptionLeg,
        S_T: float,
        exercise_rate: float = 0.0,
        is_self_default: bool = False,
    ) -> Dict[str, float]:
        """
        محاسبه مالی نکول یک لگ CALL در روز سررسید.

        فرمول‌ها (طبق ضوابط بورس تهران):
            payment   = max(0, S_T - K) × qty × contract_size
            penalty   = 0.01 × S_T × qty × contract_size
            exercise_fee = exercise_rate × K × qty × contract_size

        Args:
            leg: لگ CALL (buy یا sell)
            S_T: قیمت پایانی سهم پایه در روز سررسید
            exercise_rate: نرخ کارمزد اعمال
            is_self_default: اگر True، «من» نکول کرده‌ام (حتی اگر Long باشم).
                             اگر False، بر اساس leg_type تصمیم گرفته می‌شود.

        Returns:
            dict با کلیدهای payment, penalty, exercise_fee,
            total_received, total_paid, net, effective_price
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

        # کارمزد اعمال فقط برای Long Call
        exercise_fee = 0.0
        if leg.leg_type == LegType.BUY and exercise_rate > 0:
            exercise_fee = exercise_rate * K * shares

        # ✅ تعیین نقش: آیا من ذی‌نفع هستم یا متضرر؟
        # پیش‌فرض: Long Call ذی‌نفع، Short Call متضرر
        # اگر is_self_default=True → برعکس (من نکول کرده‌ام)
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
    # آفست — محاسبه PnL محقق‌شده بر اساس قیمت‌های ورودی
    # =====================================================

    @classmethod
    def calculate_offset_pnl(
        cls,
        position: StrategyPosition,
        close_prices: Dict[str, float],
    ) -> Dict[str, float]:
        """
        محاسبه PnL محقق‌شده برای آفست با قیمت‌های ورودی.
        """
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
    # ✅ پیشنهاد نام استراتژی (برای ComboBox در Wizard)
    # =====================================================

    # استراتژی‌های استاندارد پشتیبانی‌شده
    STANDARD_STRATEGIES = [
        "Long Call",
        "Long Put",
        "Bull Call Spread",
        "Bear Put Spread",
        "Covered Call",
        "Long Box",
    ]

    @classmethod
    def suggest_strategy_name(
        cls, legs: List[OptionLeg]
    ) -> str:
        """
        پیشنهاد نام استراتژی بر اساس ترکیب لگ‌ها.
        این تابع هیچ‌گاه تصمیم قطعی نمی‌گیرد — فقط پیشنهاد می‌دهد.

        Returns:
            نام استراتژی یا "" اگر تشخیص ممکن نبود.
        """
        if not legs:
            return ""

        # دسته‌بندی لگ‌ها
        call_buys = [l for l in legs if l.is_call and l.leg_type == LegType.BUY]
        call_sells = [l for l in legs if l.is_call and l.leg_type == LegType.SELL]
        put_buys = [l for l in legs if l.is_put and l.leg_type == LegType.BUY]
        put_sells = [l for l in legs if l.is_put and l.leg_type == LegType.SELL]
        stock_buys = [l for l in legs if l.is_stock and l.leg_type == LegType.BUY]

        n_total = len(legs)

        # ─── تک‌لگ ───
        if n_total == 1:
            leg = legs[0]
            if leg.is_call and leg.leg_type == LegType.BUY:
                return "Long Call"
            if leg.is_put and leg.leg_type == LegType.BUY:
                return "Long Put"
            # Short Call / Short Put فعلاً پشتیبانی نمی‌شود
            return ""

        # ─── دولگ: Bull Call Spread ───
        if n_total == 2 and len(call_buys) == 1 and len(call_sells) == 1:
            if call_buys[0].strike_price < call_sells[0].strike_price:
                return "Bull Call Spread"

        # ─── دولگ: Bear Put Spread ───
        if n_total == 2 and len(put_buys) == 1 and len(put_sells) == 1:
            if put_buys[0].strike_price > put_sells[0].strike_price:
                return "Bear Put Spread"

        # ─── دولگ: Covered Call ───
        if n_total == 2 and len(stock_buys) == 1 and len(call_sells) == 1:
            return "Covered Call"

        # ─── چهارلگ: Long Box ───
        # Long Call K1 + Short Call K2 + Long Put K2 + Short Put K1
        # (K1 < K2، همه با یک expiry)
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