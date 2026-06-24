# analytics/risk_engine.py
# -*- coding: utf-8 -*-

"""
موتور محاسبات ریسک و آمار پیشرفته برای استراتژی‌های اختیار معامله

"""

import numpy as np
from typing import Dict, Optional
from dataclasses import dataclass, field
import logging

from config import RISK_FREE_RATE, DEFAULT_VOLATILITY, get_price_steps
from analytics.greeks_and_probabilities import get_price_step_probabilities
from core.models import Opportunity
from core.enums import CurveType

logger = logging.getLogger("OptionScanner.Analytics.RiskEngine")


# ============================================================================
# بخش ۱: کلاس‌های داده
# ============================================================================

@dataclass(slots=True)
class RiskMetrics:
    """
    معیارهای ریسک و بازده یک استراتژی بر اساس توزیع احتمالات سناریوها

    Attributes:
        expected_value: امید ریاضی سود
        pop: احتمال سوددهی (Probability of Profit)
        sharpe_ratio: نسبت شارپ وزنی
        var_95: Value at Risk با سطح اطمینان 95%
        var_99: Value at Risk با سطح اطمینان 99%
        profit_area: مساحت زیر منحنی سود
        loss_area: مساحت زیر منحنی زیان
        area_ratio: نسبت مساحت سود به زیان
        max_drawdown: حداکثر افت
        profit_factor: نسبت سود به ضرر
        avg_profit: میانگین سود
        avg_loss: میانگین زیان
        win_rate: نرخ برد
        curve_type: نوع منحنی سود/زیان
        probabilities: بردار احتمالات
        max_profit: حداکثر سود
        max_loss: حداکثر ضرر
        std_profit: انحراف معیار سود
    """
    expected_value: float = 0.0
    pop: float = 0.0
    sharpe_ratio: float = 0.0
    var_95: float = 0.0
    var_99: float = 0.0
    profit_area: float = 0.0
    loss_area: float = 0.0
    area_ratio: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    avg_profit: float = 0.0
    avg_loss: float = 0.0
    win_rate: float = 0.0
    curve_type: CurveType = CurveType.UNKNOWN
    probabilities: np.ndarray = field(default_factory=lambda: np.array([]))
    max_profit: float = 0.0
    max_loss: float = 0.0
    std_profit: float = 0.0


# ============================================================================
# بخش ۲: موتور محاسبات ریسک
# ============================================================================

class RiskEngine:
    """موتور محاسبات ریسک و آمار پیشرفته مبتنی بر احتمالات وزنی"""

    @staticmethod
    def calculate_probabilities(
        S0_stock: float,
        pct_steps: np.ndarray,
        days_to_maturity: int,
        volatility: float = DEFAULT_VOLATILITY,
        risk_free_rate: float = RISK_FREE_RATE
    ) -> np.ndarray:
        """
        محاسبه احتمالات برای هر سطح قیمتی با استفاده از توزیع لگ-نرمال بومی

        Args:
            S0_stock: قیمت روز دارایی پایه
            pct_steps: گام‌های درصدی
            days_to_maturity: روزهای باقی‌مانده تا سررسید
            volatility: نوسان‌پذیری ضمنی
            risk_free_rate: نرخ بدون ریسک

        Returns:
            np.ndarray: بردار احتمالات برای هر سطح قیمتی
        """
        return get_price_step_probabilities(
            S0=S0_stock,
            pct_steps=pct_steps,
            t=days_to_maturity / 365.0,
            r=risk_free_rate,
            sigma=volatility,
            normalize=True
        )

    @staticmethod
    def calculate_expected_value(
        net_pnl_profile: np.ndarray,
        probabilities: np.ndarray
    ) -> float:
        """
        محاسبه امید ریاضی واقعی سود (توزیع وزنی سناریوها)

        Args:
            net_pnl_profile: پروفایل سود خالص
            probabilities: بردار احتمالات

        Returns:
            float: امید ریاضی
        """
        if len(net_pnl_profile) == 0 or len(probabilities) == 0:
            return 0.0

        if len(net_pnl_profile) != len(probabilities):
            raise ValueError("عدم تطابق طول آرایه P&L و آرایه احتمالات.")

        expected_value = float(np.dot(net_pnl_profile, probabilities))
        return round(expected_value, 2)

    @staticmethod
    def calculate_pnl_areas_and_ratio(
        net_pnl_profile: np.ndarray,
        step_size: float = 5.0
    ) -> Dict[str, float]:
        """
        محاسبه مساحت هندسی سود و زیان با روش ذوزنقه‌ای

        Args:
            net_pnl_profile: پروفایل سود خالص
            step_size: اندازه گام برای انتگرال‌گیری

        Returns:
            Dict: شامل profit_area, loss_area, ratio
        """
        if len(net_pnl_profile) == 0:
            return {'profit_area': 0.0, 'loss_area': 0.0, 'ratio': 0.0}

        dx = step_size / 100.0
        profit_area = np.trapz(np.maximum(0, net_pnl_profile), dx=dx)
        loss_area = np.trapz(np.maximum(0, -net_pnl_profile), dx=dx)

        return {
            'profit_area': round(profit_area, 2),
            'loss_area': round(loss_area, 2),
            'ratio': round(profit_area / (loss_area + 1e-6), 4)
        }

    @staticmethod
    def calculate_probability_of_profit(
        net_pnl_profile: np.ndarray,
        probabilities: np.ndarray,
        threshold: float = 0.0
    ) -> float:
        """
        محاسبه واقعی POP بر اساس مجموع احتمالات سناریوهای سودآور

        Args:
            net_pnl_profile: پروفایل سود خالص
            probabilities: بردار احتمالات
            threshold: آستانه سود

        Returns:
            float: احتمال سوددهی (درصد)
        """
        if len(net_pnl_profile) == 0 or len(probabilities) == 0:
            return 0.0

        profitable_mask = net_pnl_profile > threshold
        pop = np.sum(probabilities[profitable_mask]) * 100
        return round(float(pop), 2)

    @staticmethod
    def calculate_weighted_sharpe_ratio(
        net_pnl_profile: np.ndarray,
        probabilities: np.ndarray,
        risk_free_rate: float = RISK_FREE_RATE
    ) -> float:
        """
        محاسبه نسبت شارپ وزنی با استفاده از توزیع احتمالات

        Args:
            net_pnl_profile: پروفایل سود خالص
            probabilities: بردار احتمالات
            risk_free_rate: نرخ بدون ریسک

        Returns:
            float: نسبت شارپ
        """
        if len(net_pnl_profile) == 0 or len(probabilities) == 0:
            return 0.0

        weighted_mean = np.dot(net_pnl_profile, probabilities)
        weighted_variance = np.dot(
            (net_pnl_profile - weighted_mean) ** 2, probabilities)
        weighted_std = np.sqrt(weighted_variance) + 1e-6

        daily_rf = risk_free_rate / 252
        sharpe = (weighted_mean - daily_rf) / weighted_std

        return round(float(sharpe), 4)

    @staticmethod
    def calculate_weighted_var(
        net_pnl_profile: np.ndarray,
        probabilities: np.ndarray,
        confidence_level: float = 0.95
    ) -> float:
        """
        محاسبه Value at Risk با استفاده از توزیع تجمعی احتمالات (CDF)

        Args:
            net_pnl_profile: پروفایل سود خالص
            probabilities: بردار احتمالات
            confidence_level: سطح اطمینان (0.95 یا 0.99)

        Returns:
            float: VaR
        """
        if len(net_pnl_profile) == 0 or len(probabilities) == 0:
            return 0.0

        sort_indices = np.argsort(net_pnl_profile)
        sorted_pnl = net_pnl_profile[sort_indices]
        sorted_probs = probabilities[sort_indices]

        cdf = np.cumsum(sorted_probs)
        target_alpha = 1 - confidence_level

        idx = np.searchsorted(cdf, target_alpha)
        idx = min(idx, len(sorted_pnl) - 1)

        return round(float(sorted_pnl[idx]), 2)

    @staticmethod
    def calculate_static_max_drawdown(net_pnl_profile: np.ndarray) -> float:
        """
        محاسبه بدترین زیان ممکن نسبت به حداکثر سود در کل پهنای پروفایل

        Args:
            net_pnl_profile: پروفایل سود خالص

        Returns:
            float: حداکثر افت (درصد)
        """
        if len(net_pnl_profile) == 0:
            return 0.0

        max_profit = np.max(net_pnl_profile)
        min_pnl = np.min(net_pnl_profile)

        if min_pnl >= 0:
            return 0.0

        denom = max_profit if max_profit > 0 else 1.0
        drawdown = abs(min_pnl) / denom
        return round(float(drawdown * 100), 2)

    @staticmethod
    def calculate_weighted_profit_factor(
        net_pnl_profile: np.ndarray,
        probabilities: np.ndarray
    ) -> float:
        """
        محاسبه نسبت سود به ضرر با تاثیر دادن شانس وقوع هر سناریو

        Args:
            net_pnl_profile: پروفایل سود خالص
            probabilities: بردار احتمالات

        Returns:
            float: نسبت سود به ضرر
        """
        if len(net_pnl_profile) == 0 or len(probabilities) == 0:
            return 0.0

        weighted_pnl = net_pnl_profile * probabilities
        total_profit = np.sum(weighted_pnl[net_pnl_profile > 0])
        total_loss = abs(np.sum(weighted_pnl[net_pnl_profile < 0]))

        if total_loss == 0:
            return float('inf') if total_profit > 0 else 0.0

        return round(float(total_profit / total_loss), 2)

    @staticmethod
    def detect_curve_type(
        pct_steps: np.ndarray,
        net_pnl_profile: np.ndarray,
        tolerance: float = 0.02
    ) -> CurveType:
        """
        تشخیص پیشرفته و پایدار ساختار هندسی منحنی سود/زیان استراتژی

        Args:
            pct_steps: گام‌های درصدی
            net_pnl_profile: پروفایل سود خالص
            tolerance: تلورانس تشخیص

        Returns:
            CurveType: نوع منحنی تشخیص داده شده
        """
        if len(net_pnl_profile) < 5:
            return CurveType.UNKNOWN

        std_pnl = np.std(net_pnl_profile)
        if std_pnl < 10.0:
            return CurveType.FLAT

        zero_idx = np.argmin(np.abs(pct_steps))
        max_idx = np.argmax(net_pnl_profile)
        min_idx = np.argmin(net_pnl_profile)

        # 1. بررسی ساختارهای متقارن رنج یا غیرجهتی (Butterfly / Iron Condor)
        if max_idx != 0 and max_idx != len(net_pnl_profile) - 1:
            if net_pnl_profile[0] <= 0 and net_pnl_profile[-1] <= 0:
                # محاسبه محدوده مجاز نزدیک به ماکزیمم (0.5 درصد از محدوده کل)
                pnl_range = np.max(net_pnl_profile) - np.min(net_pnl_profile)
                peak_tolerance = 0.005 * (pnl_range + 1e-6)

                # تعداد نقاطی که در محدوده نزدیک به ماکزیمم هستند
                near_max_count = np.sum(
                    net_pnl_profile >= (
                        net_pnl_profile[max_idx] - peak_tolerance)
                )

                # اگر تعداد نقاط نزدیک به ماکزیمم <= 2 باشد، قله تیز است -> Butterfly
                # در غیر این صورت سقف مسطح است -> Iron Condor
                if near_max_count <= 2:
                    return CurveType.BUTTERFLY
                else:
                    return CurveType.IRON_CONDOR

        # 2. رفتارهای کاملاً جهتی (Bullish / Bearish)
        corr = np.corrcoef(pct_steps, net_pnl_profile)[0, 1]
        if corr > 0.85:
            return CurveType.BULLISH
        elif corr < -0.85:
            return CurveType.BEARISH

        # 3. موقعیت‌های خنثی یا نوسانی خالص
        if min_idx == zero_idx or (zero_idx - 2 <= min_idx <= zero_idx + 2):
            return CurveType.HIGH_VOLATILITY
        elif max_idx == zero_idx or (zero_idx - 2 <= max_idx <= zero_idx + 2):
            return CurveType.NEUTRAL

        return CurveType.UNKNOWN

    @classmethod
    def calculate_all_metrics(
        cls,
        net_pnl_profile: np.ndarray,
        pct_steps: np.ndarray,
        S0_stock: float,
        days_to_maturity: int,
        probabilities: Optional[np.ndarray] = None,
        volatility: float = DEFAULT_VOLATILITY,
        risk_free_rate: float = RISK_FREE_RATE,
        step_size: float = 5.0,
        confidence_level: float = 0.95
    ) -> RiskMetrics:
        """
        محاسبه یکپارچه تمام معیارهای مدیریت ریسک آپشن بر پایه توزیع آماری تصحیح‌شده

        Args:
            net_pnl_profile: پروفایل سود خالص
            pct_steps: گام‌های درصدی
            S0_stock: قیمت روز دارایی پایه
            days_to_maturity: روزهای باقی‌مانده تا سررسید
            probabilities: بردار احتمالات (اختیاری)
            volatility: نوسان‌پذیری
            risk_free_rate: نرخ بدون ریسک
            step_size: اندازه گام برای انتگرال‌گیری
            confidence_level: سطح اطمینان برای VaR

        Returns:
            RiskMetrics: تمام شاخص‌های ریسک محاسبه‌شده
        """
        if probabilities is None or len(probabilities) == 0:
            probabilities = cls.calculate_probabilities(
                S0_stock=S0_stock,
                pct_steps=pct_steps,
                days_to_maturity=days_to_maturity,
                volatility=volatility,
                risk_free_rate=risk_free_rate
            )

        expected_value = cls.calculate_expected_value(
            net_pnl_profile, probabilities)
        area_metrics = cls.calculate_pnl_areas_and_ratio(
            net_pnl_profile, step_size)
        pop = cls.calculate_probability_of_profit(
            net_pnl_profile, probabilities)
        sharpe = cls.calculate_weighted_sharpe_ratio(
            net_pnl_profile, probabilities, risk_free_rate)

        var_95 = cls.calculate_weighted_var(
            net_pnl_profile, probabilities, 0.95)
        var_99 = cls.calculate_weighted_var(
            net_pnl_profile, probabilities, 0.99)

        max_drawdown = cls.calculate_static_max_drawdown(net_pnl_profile)
        profit_factor = cls.calculate_weighted_profit_factor(
            net_pnl_profile, probabilities)

        gains = net_pnl_profile[net_pnl_profile > 0]
        losses = net_pnl_profile[net_pnl_profile < 0]
        avg_profit = round(float(np.mean(gains)), 2) if len(gains) > 0 else 0.0
        avg_loss = round(float(abs(np.mean(losses))),
                         2) if len(losses) > 0 else 0.0

        weighted_mean = np.dot(net_pnl_profile, probabilities)
        weighted_variance = np.dot(
            (net_pnl_profile - weighted_mean) ** 2, probabilities)

        return RiskMetrics(
            expected_value=expected_value,
            pop=pop,
            sharpe_ratio=sharpe,
            var_95=var_95,
            var_99=var_99,
            profit_area=area_metrics['profit_area'],
            loss_area=area_metrics['loss_area'],
            area_ratio=area_metrics['ratio'],
            max_drawdown=max_drawdown,
            profit_factor=profit_factor,
            avg_profit=avg_profit,
            avg_loss=avg_loss,
            win_rate=pop,
            curve_type=cls.detect_curve_type(pct_steps, net_pnl_profile),
            probabilities=probabilities,
            max_profit=round(float(np.max(net_pnl_profile)), 2),
            max_loss=round(float(np.min(net_pnl_profile)), 2),
            std_profit=round(float(np.sqrt(weighted_variance)), 2)
        )

    # =====================================================
    # متد اصلی تزریق به Opportunity
    # =====================================================

    @classmethod
    def evaluate_opportunity(
        cls,
        opportunity: Opportunity,
        volatility: float = DEFAULT_VOLATILITY,
        risk_free_rate: float = RISK_FREE_RATE) -> Opportunity:
        """
        تزریق داده‌های ریسک به شیء Opportunity با مکانیزم Early Return جهت پایداری سیستم

        """
        try:
            # 1. دریافت پروفایل P&L از metadata
            net_pnl_profile = opportunity.metadata.get(
                'net_profits_closed', None)
            if net_pnl_profile is None:
                logger.warning(
                    f"No P&L profile found for {opportunity.strategy_name}, skipping risk metrics")
                return opportunity

            if isinstance(net_pnl_profile, list):
                net_pnl_profile = np.array(net_pnl_profile)

            if len(net_pnl_profile) == 0:
                logger.warning(
                    f"Empty P&L profile for {opportunity.strategy_name}, skipping risk metrics")
                return opportunity

            # 2. بررسی پایداری داده‌های پایه بازار (جلوگیری از محاسبات مخدوش)
            S0_stock = getattr(opportunity, 'S0_stock', None)
            if not S0_stock or S0_stock <= 0:
                S0_stock = opportunity.metadata.get('underlying_price', None)

            days_to_maturity = getattr(opportunity, 'days_to_maturity', None)

            # Early Return: اگر داده‌های حیاتی وجود نداشته باشند، محاسبات متوقف می‌شود
            if not S0_stock or S0_stock <= 0:
                logger.error(
                    f"Missing critical market data (S0_stock) for {opportunity.strategy_name}. "
                    f"Risk evaluation aborted.")
                return opportunity

            if days_to_maturity is None or days_to_maturity <= 0:
                logger.error(
                    f"Missing critical market data (days_to_maturity) for {opportunity.strategy_name}. "
                    f"Risk evaluation aborted.")
                return opportunity

            # 3. دریافت گام‌های درصدی
            pct_steps = np.array(get_price_steps())

            # 4. محاسبه تمام شاخص‌های ریسک
            metrics = cls.calculate_all_metrics(
                net_pnl_profile=net_pnl_profile,
                pct_steps=pct_steps,
                S0_stock=float(S0_stock),
                days_to_maturity=int(days_to_maturity),
                volatility=volatility,
                risk_free_rate=risk_free_rate)

            # 5. تزریق مستقیم به فیلدهای اصلی Opportunity
            opportunity.pop = metrics.pop
            opportunity.max_profit = metrics.max_profit
            opportunity.max_loss = metrics.max_loss

            # 6. محاسبه دقیق Risk/Reward بر پایه مقادیر جدید استخراج شده
            denom = metrics.max_profit if metrics.max_profit != 0 else 1.0
            opportunity.risk_reward_ratio = round(
                abs(metrics.max_loss / denom), 4)

            # 7. تزریق داده‌های تکمیلی به لایه metadata
            opportunity.metadata['expected_value'] = metrics.expected_value
            opportunity.metadata['sharpe_ratio'] = metrics.sharpe_ratio
            opportunity.metadata['var_95'] = metrics.var_95
            opportunity.metadata['var_99'] = metrics.var_99
            opportunity.metadata['max_drawdown_pct'] = metrics.max_drawdown
            opportunity.metadata['profit_factor'] = metrics.profit_factor
            opportunity.metadata['area_ratio'] = metrics.area_ratio
            opportunity.metadata['curve_shape_detected'] = metrics.curve_type.value
            opportunity.metadata['volatility_used'] = volatility
            opportunity.metadata['probabilities_vector'] = metrics.probabilities.tolist(
            )
            opportunity.metadata['avg_profit'] = metrics.avg_profit
            opportunity.metadata['avg_loss'] = metrics.avg_loss
            opportunity.metadata['std_profit'] = metrics.std_profit

            logger.debug(
                f"Risk metrics successfully injected for {opportunity.strategy_name} on asset price {S0_stock}: "
                f"EV={metrics.expected_value}, POP={metrics.pop}%, Sharpe={metrics.sharpe_ratio}"
            )

            return opportunity

        except Exception as e:
            logger.error(
                f"Critical error in RiskEngine.evaluate_opportunity for {opportunity.strategy_name}: {str(e)}",
                exc_info=True
            )
            return opportunity


# ============================================================================
# بخش ۳: توابع کمکی (Facade)
# ============================================================================

def print_risk_summary(risk_metrics: RiskMetrics) -> None:
    """
    نمایش شکیل و خلاصه معیارهای ارزیابی ریسک در کنسول

    Args:
        risk_metrics: شیء RiskMetrics
    """
    print("=" * 55)
    print("خلاصه تحلیل ریسک استراتژی (اصلاح شده آماری)")
    print("=" * 55)
    print(f"مساحت سود (Profit Area)     : {risk_metrics.profit_area:>12.2f}")
    print(f"مساحت زیان (Loss Area)      : {risk_metrics.loss_area:>12.2f}")
    print(f"نسبت مساحت‌ها               : {risk_metrics.area_ratio:>12.4f}")
    print(
        f"امید ریاضی واقعی (EV)       : {risk_metrics.expected_value:>12.2f}")
    print(f"وزنی VaR 95%                : {risk_metrics.var_95:>12.2f}")
    print(f"نسبت شارپ وزنی              : {risk_metrics.sharpe_ratio:>12.4f}")
    print(f"حداکثر کاهش افت منحنی       : {risk_metrics.max_drawdown:>12.2f}%")
    print(f"احتمال سوددهی واقعی (POP)   : {risk_metrics.pop:>12.2f}%")
    print(f"نوع منحنی استراتژی          : {risk_metrics.curve_type.value:>12}")
    print("=" * 55)


def calculate_risk_metrics_from_payoff(
    payoff_result,
    S0_stock: float,
    days_to_maturity: int,
    pct_steps: np.ndarray,
    volatility: float = DEFAULT_VOLATILITY,
    risk_free_rate: float = RISK_FREE_RATE
) -> RiskMetrics:
    """
    محاسبه مستقیم معیارهای ریسک با پل زدن میان ساختار خروجی PayoffResult و موتور ریسک

    Args:
        payoff_result: نتیجه محاسبه P&L
        S0_stock: قیمت روز دارایی پایه
        days_to_maturity: روزهای باقی‌مانده تا سررسید
        pct_steps: گام‌های درصدی
        volatility: نوسان‌پذیری
        risk_free_rate: نرخ بدون ریسک

    Returns:
        RiskMetrics: شاخص‌های ریسک محاسبه‌شده
    """
    return RiskEngine.calculate_all_metrics(
        net_pnl_profile=payoff_result.net_profits_closed,
        pct_steps=pct_steps,
        S0_stock=S0_stock,
        days_to_maturity=days_to_maturity,
        volatility=volatility,
        risk_free_rate=risk_free_rate
    )


def evaluate_opportunity_risk(
    opportunity: Opportunity,
    volatility: float = DEFAULT_VOLATILITY,
    risk_free_rate: float = RISK_FREE_RATE
) -> Opportunity:
    """
    تابع راحت‌تر برای تزریق ریسک به فرصت

    """
    return RiskEngine.evaluate_opportunity(opportunity, volatility, risk_free_rate)
