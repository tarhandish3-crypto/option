# scoring/point_analyzer.py
# -*- coding: utf-8 -*-

"""
تحلیلگر نقطه‌ای Opportunity — پل بین دو فلسفه.

این ماژول:
1. Opportunity ماتریسی (سیستم قدیمی) را می‌گیرد
2. شاخص‌های نقطه‌ای (R30، M30، سربه‌سر، M_risk، prob_survival) را استخراج می‌کند
3. امتیاز Cobb-Douglas را محاسبه می‌کند
4. فیلتر نقطه‌ای R30/M30 اعمال می‌کند

مزایا:
- بدون بازنویسی Opportunity
- استخراج‌شده از returns_monthly_pct و break_even_points موجود
- کاملاً مستقل از UI
- قابل تست جداگانه

اجرای مستقل:
    python -m scoring.point_analyzer
"""

from __future__ import annotations

import math
import logging
from typing import List, Optional, Dict, Any

import numpy as np
from scipy.stats import norm

from core.models import Opportunity


logger = logging.getLogger("OptionScanner.Scoring.PointAnalyzer")


# ═════════════════════════════════════════════════════════════
# ثابت‌ها
# ═════════════════════════════════════════════════════════════

# وزن‌های Cobb-Douglas
DEFAULT_W_R = 0.4
DEFAULT_W_M = 0.6

# مقادیر پیش‌فرض
DEFAULT_SIGMA_FALLBACK = 0.30
DEFAULT_VOL_QUALITY_POWER = 0.3
DEFAULT_IMBALANCE_POWER = 0.5
T_DISPLAY_EPSILON = 0.02

# پارامترهای فیلتر پیش‌فرض
DEFAULT_R_MIN = 5.0
DEFAULT_M_MIN = 10.0
DEFAULT_SCORE_THRESHOLD = 0.5

# فیلتر اختصاصی هر استراتژی
STRATEGY_FILTERS: Dict[str, Dict[str, float]] = {
    "bull_call_spread": {
        "R_min": 7.0,
        "M_min": 20.0,
        "score": 0.5,
    },
    "covered_call": {
        "R_min": 5.0,
        "M_min": 10.0,
        "score": 0.5,
    },
    "long_call": {
        "R_min": 5.0,
        "M_min": 15.0,
        "score": 0.5,
    },
}


# ═════════════════════════════════════════════════════════════
# API اصلی — Enrichment
# ═════════════════════════════════════════════════════════════

def enrich_opportunity(
    opp: Opportunity,
    w_r: float = DEFAULT_W_R,
    w_m: float = DEFAULT_W_M,
) -> Opportunity:
    """
    Enrich یک Opportunity با شاخص‌های نقطه‌ای.

    فیلدهای افزوده‌شده به opp.metadata:
        - break_even_first      : اولین نقطه سربه‌سر
        - break_even_percent    : درصد فاصله قیمت تا سربه‌سر
        - R30                   : بازده ماهانه
        - M30                   : حاشیه امنیت مقیاس‌شده
        - raw_margin_percent    : حاشیه امنیت خام
        - M_risk                : M_risk
        - prob_survival         : احتمال بقا
        - composite_score       : امتیاز نهایی Cobb-Douglas

    فیلدهای افزوده‌شده به خود opp (اگر __slots__ اجازه دهد):
        - R30, M30, M_risk, prob_survival, break_even_first, composite_score

    Args:
        opp: Opportunity (از ScannerEngine)
        w_r: وزن بازده در Cobb-Douglas
        w_m: وزن حاشیه امنیت در Cobb-Douglas

    Returns:
        Opportunity (با فیلدهای جدید)
    """
    try:
        # ─── ۱. سربه‌سر ───────────────────────────────────
        break_even_points = getattr(opp, 'break_even_points', []) or []
        if break_even_points:
            try:
                first_be = float(break_even_points[0])
            except (ValueError, TypeError):
                first_be = None

            opp.metadata['break_even_first'] = first_be

            S0 = float(getattr(opp, 'S0_stock', 0.0) or 0.0)
            if first_be is not None and S0 > 0:
                be_pct = ((first_be - S0) / S0) * 100
                opp.metadata['break_even_percent'] = round(be_pct, 2)
            else:
                opp.metadata['break_even_percent'] = 0.0
        else:
            opp.metadata['break_even_first'] = None
            opp.metadata['break_even_percent'] = 0.0

        # ─── ۲. R30 (بازده ماهانه) ────────────────────────
        R30 = _extract_R30(opp)
        opp.metadata['R30'] = round(R30, 2)

        # ─── ۳. M30 (حاشیه امنیت مقیاس‌شده) ──────────────
        raw_margin = _calculate_raw_margin(opp)
        opp.metadata['raw_margin_percent'] = round(raw_margin, 2)

        days = max(
            T_DISPLAY_EPSILON,
            float(getattr(opp, 'days_to_maturity', 30) or 30)
        )
        time_factor = math.sqrt(days / 30.0)
        M30 = raw_margin / time_factor if time_factor > 0 else 0.0
        opp.metadata['M30'] = round(M30, 2)

        # ─── ۴. M_risk و prob_survival ───────────────────
        sigma = _get_sigma(opp)
        M_risk = _calculate_m_risk(raw_margin, sigma, days)
        opp.metadata['M_risk'] = round(M_risk, 2)

        prob_survival = float(norm.cdf(M_risk))
        opp.metadata['prob_survival'] = round(prob_survival, 4)

        # ─── ۵. امتیاز Cobb-Douglas ────────────────────────
        liquidity = float(getattr(opp, 'liquidity_score', 0.0) or 0.0)
        composite_score = _calculate_cobb_douglas(
            R30=R30,
            M30=M30,
            prob_survival=prob_survival,
            liquidity_score=liquidity,
            w_r=w_r,
            w_m=w_m,
        )
        opp.metadata['composite_score'] = round(composite_score, 4)

        # ─── ۶. نگاشت به فیلدهای مستقیم (اختیاری) ─────────
        try:
            opp.R30 = R30
            opp.M30 = M30
            opp.M_risk = M_risk
            opp.prob_survival = prob_survival
            opp.break_even_first = opp.metadata['break_even_first']
            opp.composite_score = composite_score
        except AttributeError:
            # اگر __slots__ مانع شود، نادیده بگیر
            pass

        logger.debug(
            "Enriched %s/%s: R30=%.2f M30=%.2f M_risk=%.2f score=%.4f",
            getattr(opp, 'strategy_name', '?'),
            getattr(opp, 'underlying_ticker', '?'),
            R30, M30, M_risk, composite_score,
        )

    except Exception as e:
        logger.error(
            "Enrichment failed for %s: %s",
            getattr(opp, 'strategy_name', '?'),
            e,
            exc_info=True,
        )
        _set_defaults(opp)

    return opp


def enrich_all(
    opportunities: List[Opportunity],
    w_r: float = DEFAULT_W_R,
    w_m: float = DEFAULT_W_M,
) -> List[Opportunity]:
    """
    Enrich گروهی برای همه Opportunity ها.

    Args:
        opportunities: لیست Opportunity
        w_r: وزن بازده
        w_m: وزن حاشیه امنیت

    Returns:
        همان لیست (به‌روزرسانی‌شده)
    """
    if not opportunities:
        return []

    count = 0
    for opp in opportunities:
        try:
            enrich_opportunity(opp, w_r=w_r, w_m=w_m)
            count += 1
        except Exception as e:
            logger.warning("Failed to enrich one opp: %s", e)

    logger.info("Enriched %d/%d opportunities", count, len(opportunities))
    return opportunities


# ═════════════════════════════════════════════════════════════
# API اصلی — فیلتر نقطه‌ای
# ═════════════════════════════════════════════════════════════

def apply_point_filters(
    opportunities: List[Opportunity],
    R_min: float = DEFAULT_R_MIN,
    M_min: float = DEFAULT_M_MIN,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
    exclude_risk_free: bool = False,
) -> List[Opportunity]:
    """
    فیلتر نقطه‌ای روی Opportunity ها.

    Args:
        opportunities: لیست Opportunity (باید enrich شده باشند)
        R_min: حداقل سود ماهانه (%)
        M_min: حداقل حاشیه امنیت
        score_threshold: حداقل امتیاز
        exclude_risk_free: حذف فرصت‌های Risk-Free؟

    Returns:
        لیست فیلترشده
    """
    if not opportunities:
        return []

    filtered = []
    for opp in opportunities:
        if _passes_point_filter(
            opp, R_min, M_min, score_threshold, exclude_risk_free
        ):
            filtered.append(opp)

    logger.debug(
        "Point filter: %d/%d passed (R30>=%.2f, M30>=%.2f, score>=%.2f)",
        len(filtered), len(opportunities),
        R_min, M_min, score_threshold,
    )
    return filtered


def filter_by_strategy(
    opportunities: List[Opportunity],
    strategy_name: str,
    R_min: Optional[float] = None,
    M_min: Optional[float] = None,
    score_threshold: Optional[float] = None,
) -> List[Opportunity]:
    """
    فیلتر نقطه‌ای با پارامترهای اختصاصی یک استراتژی.

    اگر پارامتری None باشد، از STRATEGY_FILTERS استفاده می‌شود.

    Args:
        opportunities: لیست Opportunity
        strategy_name: نام استراتژی
        R_min: بازنویسی حداقل R30
        M_min: بازنویسی حداقل M30
        score_threshold: بازنویسی حداقل امتیاز

    Returns:
        لیست فیلترشده (فقط استراتژی مشخص)
    """
    # ۱. فیلتر بر اساس نام استراتژی
    by_strategy = [
        opp for opp in opportunities
        if getattr(opp, 'strategy_name', '') == strategy_name
    ]

    if not by_strategy:
        return []

    # ۲. پارامترهای پیش‌فرض استراتژی
    defaults = STRATEGY_FILTERS.get(
        strategy_name,
        {
            "R_min": DEFAULT_R_MIN,
            "M_min": DEFAULT_M_MIN,
            "score": DEFAULT_SCORE_THRESHOLD,
        }
    )

    R_min = R_min if R_min is not None else defaults["R_min"]
    M_min = M_min if M_min is not None else defaults["M_min"]
    score_threshold = (
        score_threshold if score_threshold is not None
        else defaults["score"]
    )

    # ۳. اعمال فیلتر نقطه‌ای
    return apply_point_filters(
        by_strategy,
        R_min=R_min,
        M_min=M_min,
        score_threshold=score_threshold,
    )


# ═════════════════════════════════════════════════════════════
# API سطح بالا (اختیاری — برای SpreadAnalyzerWindow)
# ═════════════════════════════════════════════════════════════

def process_opportunities(
    opportunities: List[Opportunity],
    strategy_name: Optional[str] = None,
    R_min: Optional[float] = None,
    M_min: Optional[float] = None,
    score_threshold: Optional[float] = None,
    sort_by_score: bool = True,
) -> List[Opportunity]:
    """
    API یکپارچه: Enrich + Filter + Sort.

    این تابع، همه‌ی کارهای تحلیل نقطه‌ای را در یک فراخوانی انجام می‌دهد.

    Args:
        opportunities: لیست Opportunity (خام از ScannerEngine)
        strategy_name: اگر داده شود، فقط این استراتژی فیلتر می‌شود
        R_min: بازنویسی حداقل R30
        M_min: بازنویسی حداقل M30
        score_threshold: بازنویسی حداقل امتیاز
        sort_by_score: مرتب‌سازی نزولی بر اساس composite_score

    Returns:
        لیست Opportunity (Enriched + Filtered + Sorted)
    """
    if not opportunities:
        return []

    # ۱. Enrich
    enriched = enrich_all(opportunities)

    # ۲. Filter
    if strategy_name:
        filtered = filter_by_strategy(
            enriched, strategy_name,
            R_min=R_min, M_min=M_min, score_threshold=score_threshold,
        )
    else:
        filtered = apply_point_filters(
            enriched,
            R_min=R_min if R_min is not None else DEFAULT_R_MIN,
            M_min=M_min if M_min is not None else DEFAULT_M_MIN,
            score_threshold=(
                score_threshold if score_threshold is not None
                else DEFAULT_SCORE_THRESHOLD
            ),
        )

    # ۳. Sort
    if sort_by_score:
        filtered.sort(
            key=lambda o: float(
                getattr(o, 'metadata', {}).get('composite_score', 0.0) or 0.0
            ),
            reverse=True,
        )

    return filtered


def get_summary(opportunities: List[Opportunity]) -> Dict[str, Any]:
    """
    خلاصه‌ی آماری از Opportunity های Enriched.

    Returns:
        dict: خلاصه شامل تعداد، میانگین R30، میانگین M30، ...
    """
    if not opportunities:
        return {
            "total": 0,
            "avg_R30": 0.0,
            "avg_M30": 0.0,
            "avg_score": 0.0,
            "max_score": 0.0,
            "min_score": 0.0,
            "by_strategy": {},
        }

    R30_values = []
    M30_values = []
    score_values = []
    by_strategy: Dict[str, int] = {}

    for opp in opportunities:
        md = getattr(opp, 'metadata', {}) or {}
        try:
            R30_values.append(float(md.get('R30', 0.0) or 0.0))
            M30_values.append(float(md.get('M30', 0.0) or 0.0))
            score_values.append(float(md.get('composite_score', 0.0) or 0.0))
        except (ValueError, TypeError):
            continue

        strat = getattr(opp, 'strategy_name', 'unknown')
        by_strategy[strat] = by_strategy.get(strat, 0) + 1

    if not score_values:
        return {
            "total": len(opportunities),
            "avg_R30": 0.0,
            "avg_M30": 0.0,
            "avg_score": 0.0,
            "max_score": 0.0,
            "min_score": 0.0,
            "by_strategy": by_strategy,
        }

    return {
        "total": len(opportunities),
        "avg_R30": round(sum(R30_values) / len(R30_values), 2),
        "avg_M30": round(sum(M30_values) / len(M30_values), 2),
        "avg_score": round(sum(score_values) / len(score_values), 4),
        "max_score": round(max(score_values), 4),
        "min_score": round(min(score_values), 4),
        "by_strategy": by_strategy,
    }


# ═════════════════════════════════════════════════════════════
# توابع کمکی (private)
# ═════════════════════════════════════════════════════════════

def _extract_R30(opp: Opportunity) -> float:
    """
    استخراج R30 از returns_monthly_pct یا net_returns_closed.

    اگر مقدار موجود نبود، به metadata نگاه می‌کند.
    """
    # تلاش در فیلدهای مستقیم
    for attr in ('returns_monthly_pct', 'net_returns_closed'):
        returns = getattr(opp, attr, None)
        if returns is not None and len(returns) > 0:
            try:
                returns_arr = np.asarray(returns, dtype=float)
                positive = returns_arr[returns_arr > 0]
                if len(positive) > 0:
                    return float(np.max(positive))
                return float(np.max(returns_arr))
            except Exception:
                continue

    # تلاش در metadata
    md = getattr(opp, 'metadata', {}) or {}
    for key in ('returns_monthly_pct', 'net_returns_closed'):
        val = md.get(key)
        if val is not None and len(val) > 0:
            try:
                arr = np.asarray(val, dtype=float)
                positive = arr[arr > 0]
                if len(positive) > 0:
                    return float(np.max(positive))
                return float(np.max(arr))
            except Exception:
                continue

    return 0.0


def _calculate_raw_margin(opp: Opportunity) -> float:
    """
    حاشیه امنیت خام = فاصله تا نزدیک‌ترین سربه‌سر (به درصد).
    """
    S0 = float(getattr(opp, 'S0_stock', 0.0) or 0.0)
    if S0 <= 0:
        return 0.0

    be_points = getattr(opp, 'break_even_points', []) or []
    if not be_points:
        return 0.0

    try:
        distances = [
            abs(float(be) - S0)
            for be in be_points
            if be is not None
        ]
        if not distances:
            return 0.0
        return (min(distances) / S0) * 100
    except (ValueError, TypeError):
        return 0.0


def _get_sigma(opp: Opportunity) -> float:
    """
    استخراج sigma از metadata.

    ترتیب اولویت:
        1. volatility_used (از RiskEngine)
        2. HV_60 (نوسان تاریخی)
        3. implied_volatility (از Greeks)
        4. DEFAULT_SIGMA_FALLBACK
    """
    md = getattr(opp, 'metadata', {}) or {}
    for key in ('volatility_used', 'HV_60', 'implied_volatility'):
        val = md.get(key)
        if val is not None:
            try:
                v = float(val)
                if v > 0:
                    return v
            except (ValueError, TypeError):
                continue
    return DEFAULT_SIGMA_FALLBACK


def _calculate_m_risk(
    raw_margin_pct: float,
    sigma: float,
    days: float,
) -> float:
    """
    محاسبه M_risk.

    فرمول:
        M_risk = (raw_margin / 100) / (sigma * sqrt(T/365))
    """
    if sigma <= 0 or days <= 0:
        return 0.0

    raw_frac = raw_margin_pct / 100.0
    denom = sigma * math.sqrt(days / 365.0)
    return raw_frac / denom if denom > 0 else 0.0


def _calculate_cobb_douglas(
    R30: float,
    M30: float,
    prob_survival: float,
    liquidity_score: float,
    w_r: float = DEFAULT_W_R,
    w_m: float = DEFAULT_W_M,
) -> float:
    """
    محاسبه امتیاز نهایی Cobb-Douglas.

    فرمول:
        score_cd = (R30^w_r) * (M30^w_m)
        vol_factor = (liquidity/10)^0.3
        imbalance_factor = min(1, (M30/R30)^0.5)
        composite = score_cd * prob_survival * vol_factor * imbalance_factor
    """
    R30_safe = max(0.1, R30)
    M30_safe = max(0.1, M30)

    score_cd = (R30_safe ** w_r) * (M30_safe ** w_m)

    vol_factor = (
        (liquidity_score / 10.0) ** DEFAULT_VOL_QUALITY_POWER
        if liquidity_score > 0 else 1.0
    )

    ratio = M30_safe / max(0.1, R30_safe)
    imbalance_factor = min(1.0, ratio ** DEFAULT_IMBALANCE_POWER)

    return score_cd * prob_survival * vol_factor * imbalance_factor


def _passes_point_filter(
    opp: Opportunity,
    R_min: float,
    M_min: float,
    score_threshold: float,
    exclude_risk_free: bool,
) -> bool:
    """بررسی عبور یک Opportunity از فیلتر."""
    md = getattr(opp, 'metadata', {}) or {}

    if exclude_risk_free:
        regime = md.get('regime', 'NORMAL')
        if regime == 'RISK_FREE':
            return False

    try:
        R30 = float(md.get('R30', 0.0) or 0.0)
        M30 = float(md.get('M30', 0.0) or 0.0)
        score = float(md.get('composite_score', 0.0) or 0.0)
    except (ValueError, TypeError):
        return False

    return R30 >= R_min and M30 >= M_min and score >= score_threshold


def _set_defaults(opp: Opportunity) -> None:
    """مقادیر پیش‌فرض در صورت خطا."""
    md = getattr(opp, 'metadata', None)
    if md is None:
        return

    md.setdefault('break_even_first', None)
    md.setdefault('break_even_percent', 0.0)
    md.setdefault('R30', 0.0)
    md.setdefault('M30', 0.0)
    md.setdefault('raw_margin_percent', 0.0)
    md.setdefault('M_risk', 0.0)
    md.setdefault('prob_survival', 1.0)
    md.setdefault('composite_score', 0.0)


# ═════════════════════════════════════════════════════════════
# اجرای مستقل (تست)
# ═════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info("point_analyzer.py - self test")

    # ساخت یک Opportunity نمونه
    class _DummyContract:
        def __init__(self, ticker):
            self.ticker = ticker

    class _DummyLeg:
        def __init__(self, ticker, side, ratio):
            self.contract = _DummyContract(ticker)
            self.side = side
            self.ratio = ratio

    class _DummyOpp:
        def __init__(self):
            self.strategy_name = "bull_call_spread"
            self.underlying_ticker = "ضخودرو"
            self.S0_stock = 4500.0
            self.days_to_maturity = 25
            self.break_even_points = [4850.0]
            self.returns_monthly_pct = np.array([8.2, 5.0, -2.0, 10.0])
            self.liquidity_score = 75.0
            self.metadata = {}

    opp = _DummyOpp()
    enrich_opportunity(opp)

    logger.info("Enrichment result:")
    logger.info("  R30:              %.2f", opp.metadata['R30'])
    logger.info("  M30:              %.2f", opp.metadata['M30'])
    logger.info("  Break-even:       %s", opp.metadata['break_even_first'])
    logger.info("  Break-even %%:     %.2f",
                opp.metadata['break_even_percent'])
    logger.info("  M_risk:           %.2f", opp.metadata['M_risk'])
    logger.info("  Prob survival:    %.4f", opp.metadata['prob_survival'])
    logger.info("  Composite score:  %.4f", opp.metadata['composite_score'])

    # تست فیلتر
    filtered = apply_point_filters(
        [opp], R_min=5.0, M_min=10.0, score_threshold=0.5
    )
    logger.info("Filter result: %d opp(s) passed", len(filtered))

    # تست خلاصه
    summary = get_summary([opp])
    logger.info("Summary: %s", summary)
