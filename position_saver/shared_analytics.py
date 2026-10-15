# position_saver/shared_analytics.py
# -*- coding: utf-8 -*-

"""
توابع مشترک تحلیلی — منبع واحد حقیقت (Single Source of Truth)

این ماژول برای همخوانی کامل محاسبات Position Saver با برنامه‌ی اصلی
(OptionScanner) طراحی شده است.

استانداردهای پیروی‌شده:
    - OCC (Options Clearing Corporation): محاسبه‌ی Capital Base
    - CBOE: Max Profit / Max Loss برای استراتژی‌ها
    - سمات بورس تهران: کارمزد اعمال و وجه تضمین
    - DRY Principle: یک‌جا محاسبه، همه‌جا استفاده

استفاده:
    from position_saver.shared_analytics import SharedAnalytics

    capital = SharedAnalytics.calculate_capital_base(position)
    max_p = SharedAnalytics.calculate_max_profit_at_expiry(position)
    target = SharedAnalytics.calculate_monthly_target_roi(max_p, capital, D)
    threshold = SharedAnalytics.calculate_dynamic_threshold(target, d)
"""

from __future__ import annotations

import logging
import re
from typing import Optional, List, Dict, Tuple

import jdatetime

from position_saver.models import (
    StrategyPosition, OptionLeg, LegType,
)
from position_saver.providers import get_commission_rate


logger = logging.getLogger("PositionSaver.SharedAnalytics")


# ═══════════════════════════════════════════════════
# ثابت‌ها
# ═══════════════════════════════════════════════════

# نرخ‌های پشتیبان در صورت نبود provider
_FALLBACK_OPTION_RATE = 0.001
_FALLBACK_STOCK_BUY_RATE = 0.003712
_FALLBACK_STOCK_SELL_RATE = 0.0088

# نرخ مالیات انتقال سهم پایه (سمات)
_EXERCISE_TAX_RATE = 0.005  # 0.5%

# نرخ کارمزد اعمال (سمات)
_EXERCISE_FEE_RATE = 0.0005  # 0.05%

# روز در ماه برای محاسبه‌ی ROI ماهانه
_DAYS_PER_MONTH = 30

# حداکثر تعداد نقطه‌ی آزمون در payoff grid
_MAX_PAYOFF_POINTS = 50


# ═══════════════════════════════════════════════════
# کلاس اصلی
# ═══════════════════════════════════════════════════

class SharedAnalytics:
    """
    توابع مشترک تحلیلی — منبع واحد حقیقت.

    تمام محاسبات مالی در این کلاس متمرکز است تا از تناقض
    بین ماژول‌های مختلف جلوگیری شود.
    """

    # ═══════════════════════════════════════════════
    # کارمزد
    # ═══════════════════════════════════════════════

    @staticmethod
    def _contract_size(leg: OptionLeg) -> int:
        """اندازه قرارداد واقعی."""
        return leg.effective_contract_size

    @classmethod
    def _get_commission_rate(cls, leg: OptionLeg,
                              is_buy: bool) -> float:
        """نرخ کارمزد با fallback."""
        if leg.is_option:
            market, asset_type = "tse", "option"
        else:
            market, asset_type = "tse", "stock"

        try:
            rate = get_commission_rate(market, asset_type, is_buy)
            if rate is not None:
                return float(rate)
        except Exception:
            pass

        if leg.is_option:
            return _FALLBACK_OPTION_RATE
        return (_FALLBACK_STOCK_BUY_RATE if is_buy
                else _FALLBACK_STOCK_SELL_RATE)

    @classmethod
    def calculate_leg_entry_fee(cls, leg: OptionLeg) -> float:
        """کارمزد ورود یک لگ."""
        is_buy = (leg.leg_type == LegType.BUY)
        rate = cls._get_commission_rate(leg, is_buy)
        cs = cls._contract_size(leg)
        notional = leg.quantity * leg.entry_price * cs
        return notional * rate

    @classmethod
    def calculate_leg_close_fee(
        cls, leg: OptionLeg, close_price: float
    ) -> float:
        """کارمزد خروج یک لگ."""
        if close_price is None or close_price <= 0:
            return 0.0
        is_buy_on_close = (leg.leg_type == LegType.SELL)
        rate = cls._get_commission_rate(leg, is_buy_on_close)
        cs = cls._contract_size(leg)
        notional = leg.quantity * close_price * cs
        return notional * rate

    # ═══════════════════════════════════════════════
    # ✅ Capital Base — مطابق OCC و سمات
    # ═══════════════════════════════════════════════

    @classmethod
    def calculate_capital_base(
        cls, position: StrategyPosition
    ) -> float:
        """
        سرمایه‌ی درگیر در استراتژی — مطابق OCC و سمات.

        فرمول:
            capital = margin + max(0, net_premium)
                    + stock_investment + entry_fees

        که:
            - margin: وجه تضمین (برای کردیت اسپردها و Naked Short)
            - net_premium: پرداختی خالص برای آپشن‌های خرید
            - stock_investment: هزینه‌ی خرید سهم پایه
            - entry_fees: مجموع کارمزدهای ورود

        Returns:
            سرمایه‌ی درگیر (ریال). اگر صفر بود، 1 برمی‌گرداند
            تا از تقسیم بر صفر جلوگیری شود.
        """
        if not position or not position.legs:
            return 1.0

        # ─── ۱. margin (وجه تضمین) ───
        margin = cls._estimate_margin(position)

        # ─── ۲. net_premium (فقط پرداختی) ───
        net_premium = 0.0
        for leg in position.legs:
            if leg.is_option:
                val = leg.entry_value()
                if leg.leg_type == LegType.BUY:
                    net_premium += val
                else:
                    net_premium -= val
        net_premium = max(0.0, net_premium)

        # ─── ۳. stock_investment ───
        stock_inv = 0.0
        for leg in position.legs:
            if leg.is_stock and leg.leg_type == LegType.BUY:
                stock_inv += leg.entry_value()

        # ─── ۴. entry_fees ───
        fees = 0.0
        for leg in position.legs:
            if leg.entry_fee > 0:
                fees += leg.entry_fee
            else:
                fees += cls.calculate_leg_entry_fee(leg)

        total = margin + net_premium + stock_inv + fees
        return total if total > 0 else 1.0

    @classmethod
    def _estimate_margin(
        cls, position: StrategyPosition
    ) -> float:
        """
        برآورد وجه تضمین برای موقعیت.

        طبق ضوابط سمات:
            - Naked Short CALL/PUT: A × S − OTM (با حداقل B × K)
            - Credit Spread: (K2 − K1) × qty × cs − net_credit
            - Debit Spread: 0 (فقط پرداختی)
            - Covered Call: 0 (سهام پوشش می‌دهد)
            - Iron Condor: max(call_risk, put_risk) − net_credit
        """
        # ─── بررسی پوشش سهام (Covered Call) ───
        sell_legs = [
            l for l in position.legs if l.leg_type == LegType.SELL
        ]
        if not sell_legs:
            return 0.0

        # آیا سهم پایه در position هست که پوشش دهد؟
        stock_buys = [
            l for l in position.legs
            if l.is_stock and l.leg_type == LegType.BUY
        ]

        # ─── Covered Call ───
        if stock_buys:
            # اگر سهم پایه هست و فقط CALL فروخته شده → پوشش دارد
            naked_put_sells = [
                l for l in sell_legs if l.is_put
            ]
            if not naked_put_sells:
                return 0.0

        # ─── Credit Spread ───
        if len(sell_legs) == 1:
            sell = sell_legs[0]
            # جستجوی BUY هم‌نوع با strike متفاوت
            matching_buys = [
                l for l in position.legs
                if l.leg_type == LegType.BUY
                and l.is_option
                and l.option_kind == sell.option_kind
                and l.strike_price != sell.strike_price
            ]
            if matching_buys:
                buy = matching_buys[0]
                cs = sell.effective_contract_size
                qty = sell.quantity
                spread = abs(buy.strike_price - sell.strike_price)
                gross_risk = spread * qty * cs
                net_credit = (sell.entry_price - buy.entry_price) \
                    * qty * cs
                return max(0.0, gross_risk - net_credit)

        # ─── Naked Short ───
        total_margin = 0.0
        S = position.underlying_price
        if S <= 0:
            # بدون قیمت سهم پایه، مارجین تقریبی
            for leg in sell_legs:
                if leg.is_option and leg.strike_price > 0:
                    cs = leg.effective_contract_size
                    # برآورد محافظه‌کارانه: 20% strike
                    total_margin += leg.strike_price * 0.20 \
                        * leg.quantity * cs
            return total_margin

        # محاسبه‌ی دقیق بر اساس سمات
        for leg in sell_legs:
            if not leg.is_option:
                continue
            K = leg.strike_price
            if K <= 0:
                continue

            cs = leg.effective_contract_size
            qty = leg.quantity

            if leg.is_call:
                otm = max(0.0, K - S)
            else:
                otm = max(0.0, S - K)

            base_per_unit = max(0.20 * S - otm, 0.10 * K)
            leg_margin = base_per_unit * cs * qty
            total_margin += leg_margin

        return total_margin

    # ═══════════════════════════════════════════════
    # ✅ Max Profit / Max Loss — مطابق OCC
    # ═══════════════════════════════════════════════

    @classmethod
    def calculate_max_profit_at_expiry(
        cls,
        position: StrategyPosition,
        price_target: Optional[float] = None,
    ) -> Optional[float]:
        """
        حداکثر سود استراتژی در سررسید.

        Args:
            position: موقعیت استراتژی
            price_target: قیمت هدف سهم پایه (برای سود نامحدود).
                اگر None باشد و سود نامحدود باشد، None برمی‌گردد.

        Returns:
            حداکثر سود (ریال) یا None اگر نامحدود و بدون target.
        """
        if not position or not position.legs:
            return 0.0

        # ─── استخراج strikes ───
        strikes = []
        for leg in position.legs:
            if leg.is_option and leg.strike_price > 0:
                strikes.append(leg.strike_price)
            elif leg.is_stock and leg.entry_price > 0:
                strikes.append(leg.entry_price)

        if not strikes:
            return 0.0

        min_K = min(strikes)
        max_K = max(strikes)

        # ─── نقاط آزمون ───
        test_points = cls._build_test_points(
            strikes, min_K, max_K, price_target)

        # ─── محاسبه‌ی payoff در هر نقطه ───
        net_entry = cls.calculate_net_entry_cost(position)
        fees = cls._total_entry_fees(position)

        max_pnl = float('-inf')
        for S_T in test_points:
            payoff = cls._payoff_at_expiry(position, S_T)
            pnl = payoff - net_entry - fees
            if pnl > max_pnl:
                max_pnl = pnl

        # ─── بررسی سود نامحدود ───
        # اگر در نقاط مرزی صعودی، سود در حال افزایش باشد
        # و price_target نباشد → سود نامحدود
        if price_target is None:
            is_unlimited = cls._is_unlimited_profit(position)
            if is_unlimited:
                return None  # نامحدود

        return max(0.0, max_pnl)

    @staticmethod
    def _build_test_points(
        strikes: List[float],
        min_K: float,
        max_K: float,
        price_target: Optional[float],
    ) -> List[float]:
        """ساخت نقاط آزمون برای payoff grid."""
        points = set()

        # نقاط کلیدی
        points.add(0.0)
        points.add(min_K * 0.5)
        points.add(max_K * 1.5)
        points.add(max_K * 3.0)

        # تمام strikes
        for k in strikes:
            points.add(k)
            points.add(k * 0.98)
            points.add(k * 1.02)

        # میانه‌ی هر جفت
        sorted_strikes = sorted(set(strikes))
        for i in range(len(sorted_strikes) - 1):
            mid = (sorted_strikes[i] + sorted_strikes[i + 1]) / 2
            points.add(mid)

        # price_target اگر داده شده
        if price_target and price_target > 0:
            points.add(price_target)

        return sorted(points)

    @classmethod
    def _payoff_at_expiry(
        cls, position: StrategyPosition, S_T: float
    ) -> float:
        """ارزش موقعیت در سررسید به ازای S_T."""
        total = 0.0
        for leg in position.legs:
            cs = leg.effective_contract_size
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

    @staticmethod
    def _is_unlimited_profit(position: StrategyPosition) -> bool:
        """
        آیا استراتژی سود نامحدود دارد؟

        سود نامحدود وقتی است که در سمت صعودی قیمت،
        position خالص BUY (Long) باشد (بدون سقف).
        """
        # محاسبه‌ی وزن خالص CALL ها
        net_calls = 0
        net_puts = 0
        for leg in position.legs:
            sign = 1 if leg.leg_type == LegType.BUY else -1
            if leg.is_call:
                net_calls += sign * leg.quantity
            elif leg.is_put:
                net_puts += sign * leg.quantity

        # Long Call خالص → سود نامحدود
        if net_calls > 0 and net_puts == 0:
            return True

        # Long Straddle/Strangle → سود نامحدود
        if net_calls > 0 and net_puts > 0:
            return True

        return False

    @classmethod
    def calculate_net_entry_cost(
        cls, position: StrategyPosition
    ) -> float:
        """هزینه خالص ورود (بدون کارمزد)."""
        net = 0.0
        for leg in position.legs:
            cs = leg.effective_contract_size
            val = leg.quantity * leg.entry_price * cs
            if leg.leg_type == LegType.BUY:
                net += val
            else:
                net -= val
        return net

    @classmethod
    def _total_entry_fees(cls, position: StrategyPosition) -> float:
        """مجموع کارمزدهای ورود."""
        total = 0.0
        for leg in position.legs:
            if leg.entry_fee > 0:
                total += leg.entry_fee
            else:
                total += cls.calculate_leg_entry_fee(leg)
        return total

    # ═══════════════════════════════════════════════
    # ✅ Target ROI — مطابق برنامه‌ی اصلی
    # ═══════════════════════════════════════════════

    @classmethod
    def calculate_monthly_target_roi(
        cls,
        max_profit: float,
        capital_base: float,
        days_to_maturity: int,
    ) -> float:
        """
        محاسبه‌ی ROI ماهانه‌ی هدف — مطابق برنامه‌ی اصلی.

        فرمول برنامه‌ی اصلی:
            returns_monthly_pct = (max_profit / capital_base)
                                  × (30 / D) × 100

        Returns:
            ROI ماهانه به درصد (مثلاً 5.0 برای 5%)
        """
        if capital_base <= 0 or max_profit <= 0:
            return 0.0
        if days_to_maturity <= 0:
            return 0.0

        roi_period = (max_profit / capital_base) * 100.0
        monthly_factor = _DAYS_PER_MONTH / days_to_maturity
        target = roi_period * monthly_factor

        return round(target, 2)

    # ═══════════════════════════════════════════════
    # ✅ Dynamic Threshold — آلرت پویا
    # ═══════════════════════════════════════════════

    @classmethod
    def calculate_dynamic_threshold(
        cls,
        monthly_target_roi: float,
        days_elapsed: int,
    ) -> float:
        """
        آستانه‌ی آلرت پویا برای روز مشخص.

        فرمول:
            threshold(d) = target × (d / 30)

        که:
            - target: ROI ماهانه (مثلاً 5%)
            - d: تعداد روز سپری‌شده از اجرا
            - 30: یک ماه

        Returns:
            آستانه‌ی ROI روز d (درصد)
        """
        if monthly_target_roi <= 0 or days_elapsed < 0:
            return 0.0

        threshold = monthly_target_roi * (days_elapsed / _DAYS_PER_MONTH)
        return round(threshold, 3)

    # ═══════════════════════════════════════════════
    # ✅ Date Helpers
    # ═══════════════════════════════════════════════

    @staticmethod
    def _parse_jalali_date(date_str: str) -> Optional[jdatetime.date]:
        """تبدیل رشته تاریخ شمسی به jdatetime.date."""
        if not date_str:
            return None
        try:
            s = str(date_str).strip()
            m = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', s)
            if not m:
                return None
            return jdatetime.date(
                int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            return None

    @classmethod
    def calculate_days_elapsed(
        cls, position: StrategyPosition
    ) -> int:
        """تعداد روز سپری‌شده از تاریخ اجرا تا امروز."""
        if not position.execution_date:
            return 0
        start = cls._parse_jalali_date(position.execution_date)
        if start is None:
            return 0
        today = jdatetime.date.today()
        delta = (today - start).days
        return max(0, delta)

    @classmethod
    def calculate_days_to_maturity(
        cls, position: StrategyPosition
    ) -> int:
        """تعداد روز از اجرا تا سررسید."""
        if not position.execution_date or not position.expiry_date:
            return 30  # پیش‌فرض
        start = cls._parse_jalali_date(position.execution_date)
        end = cls._parse_jalali_date(position.expiry_date)
        if start is None or end is None:
            return 30
        delta = (end - start).days
        return max(1, delta)

    @classmethod
    def calculate_days_remaining(
        cls, position: StrategyPosition
    ) -> int:
        """تعداد روز باقی‌مانده تا سررسید."""
        if not position.expiry_date:
            return 0
        end = cls._parse_jalali_date(position.expiry_date)
        if end is None:
            return 0
        today = jdatetime.date.today()
        delta = (end - today).days
        return max(0, delta)

    # ═══════════════════════════════════════════════
    # ✅ Pace — معیار جهانی
    # ═══════════════════════════════════════════════

    @classmethod
    def calculate_pace(
        cls,
        current_roi: float,
        monthly_target: float,
        days_elapsed: int,
    ) -> float:
        """
        محاسبه‌ی Pace (سرعت پیشرفت نسبت به هدف).

        Pace = live_roi / threshold(d)

        که:
            - >= 1.0 → 🎯 «رسید»
            - >= 0.8 → 🟡 «نزدیک»
            - >= 0.0 → 🔵 «دور»
            - < 0.0 → 🔴 «در زیان»
        """
        threshold = cls.calculate_dynamic_threshold(
            monthly_target, days_elapsed)
        if threshold <= 0:
            return 0.0
        return current_roi / threshold

    # ═══════════════════════════════════════════════
    # ✅ Helpers — برای UI
    # ═══════════════════════════════════════════════

    @classmethod
    def get_target_status(
        cls,
        current_roi: float,
        monthly_target: float,
        days_elapsed: int,
        is_open: bool,
    ) -> Tuple[str, str, float]:
        """
        وضعیت تارگت برای نمایش در جدول.

        Returns:
            (متن وضعیت, رنگ, مقدار سورت)
        """
        # Non-ASCII constants for colors
        PROFIT = "#1B8A5A"
        WARN = "#C77700"
        INFO = "#2196F3"
        LOSS = "#D64545"
        MUTED = "#6B7280"

        if monthly_target <= 0:
            return ("— تنظیم نشده", MUTED, -1.0)

        if not is_open:
            # position بسته‌شده
            if current_roi >= monthly_target:
                return ("✅ رسید (بسته)", PROFIT, 3.0)
            return ("— بسته", MUTED, 0.0)

        # position باز
        threshold = cls.calculate_dynamic_threshold(
            monthly_target, days_elapsed)
        pace = current_roi / threshold if threshold > 0 else 0.0

        if pace >= 1.0:
            return ("🎯 رسید", PROFIT, 3.0)
        if pace >= 0.8:
            return ("🟡 نزدیک", WARN, 2.0)
        if current_roi >= 0:
            return ("🔵 دور", INFO, 1.0)
        return ("🔴 در زیان", LOSS, 0.0)


__all__ = ["SharedAnalytics"]