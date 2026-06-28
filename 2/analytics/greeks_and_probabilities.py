# analytics/greeks_and_probabilities.py
# -*- coding: utf-8 -*-

"""
ماژول محاسبات یونانی‌ها و توزیع احتمال برای استراتژی‌های اختیار معامله
پشتیبانی از: دلتا، گاما، تتا روزانه، وگا، و توزیع لگ-نرمال
"""

import numpy as np
from scipy.stats import norm
from typing import Tuple, List, Dict, Optional, Union
import warnings


# ============================================================================
# بخش ۱: اعتبارسنجی و مدیریت خطا
# ============================================================================

def validate_inputs(
    S: float,
    K: float,
    t: float,
    r: float,
    sigma: float,
    option_type: Optional[str] = None
) -> None:
    if S <= 0:
        raise ValueError(f" قیمت پایه (S) باید مثبت باشد: {S}")
    if K <= 0:
        raise ValueError(f" قیمت اعمال (K) باید مثبت باشد: {K}")
    if t < 0:
        raise ValueError(f" زمان تا سررسید (t) نمی‌تواند منفی باشد: {t}")
    if t == 0:
        warnings.warn(" زمان تا سررسید صفر است (سررسید امروز)")
    if r < 0:
        warnings.warn(f" نرخ بهره (r) منفی است: {r}")
    if sigma <= 0:
        raise ValueError(f" نوسان‌پذیری (sigma) باید مثبت باشد: {sigma}")
    if option_type is not None:
        if option_type.lower() not in ['call', 'put']:
            raise ValueError(f" نوع آپشن نامعتبر: {option_type}")


def handle_numerical_issues(func):
    """دکوراتور پیشرفته برای کنترل پایداری عددی سیستم مالی"""
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            if isinstance(result, (int, float)):
                if not np.isfinite(result):
                    return 0.0
            elif isinstance(result, np.ndarray):
                result = np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)
            elif isinstance(result, dict):
                for key, value in result.items():
                    if isinstance(value, (int, float)) and not np.isfinite(value):
                        result[key] = 0.0
            return result
        except Exception as e:
            warnings.warn(f"⚠️ خطای محاسباتی در ران‌پایپ: {e}")
            return 0.0 if not func.__annotations__.get('return') == dict else {}
    return wrapper


# ============================================================================
# بخش ۲: محاسبات پایه بلک-شولز
# ============================================================================

@handle_numerical_issues
def calculate_d1_d2(
    S: float,
    K: float,
    t: float,
    r: float,
    sigma: float
) -> Tuple[float, float]:
    validate_inputs(S, K, t, r, sigma)
    
    # کنترل شرایط مرزی در سررسید لحظه‌ای
    if t < 1e-5 or sigma < 1e-5:
        if S >= K:
            return 10.0, 10.0  # کران بالا برای اجتناب از مقدار بی‌نهایت
        else:
            return -10.0, -10.0
            
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)
    
    # کلیپ اصولی d1 و d2 صرفاً برای پایداری توزیع نرمال
    d1 = np.clip(d1, -10, 10)
    d2 = np.clip(d2, -10, 10)
    
    return d1, d2


# ============================================================================
# بخش ۳: محاسبه یونانی‌های تک پایه (Leg)
# ============================================================================

@handle_numerical_issues
def calculate_leg_greeks(
    S: float,
    K: float,
    t: float,
    r: float,
    sigma: float,
    option_type: str
) -> Tuple[float, float, float]:
    validate_inputs(S, K, t, r, sigma, option_type)
    
    d1, d2 = calculate_d1_d2(S, K, t, r, sigma)
    
    pdf_d1 = norm.pdf(d1)
    cdf_d1 = norm.cdf(d1)
    cdf_d2 = norm.cdf(d2)
    cdf_neg_d2 = norm.cdf(-d2)
    
    # ۱. محاسبه دلتا
    if option_type.lower() == 'call':
        delta = cdf_d1
    else:
        delta = cdf_d1 - 1.0
    
    # ۲. محاسبه گاما
    if t > 1e-5 and sigma > 1e-5:
        gamma = pdf_d1 / (S * sigma * np.sqrt(t))
    else:
        gamma = 0.0
    
    # ۳. محاسبه تتا سالانه
    if t > 1e-5 and sigma > 1e-5:
        if option_type.lower() == 'call':
            theta_yearly = (- (S * pdf_d1 * sigma) / (2 * np.sqrt(t)) - r * K * np.exp(-r * t) * cdf_d2)
        else:
            theta_yearly = (- (S * pdf_d1 * sigma) / (2 * np.sqrt(t)) + r * K * np.exp(-r * t) * cdf_neg_d2)
    else:
        theta_yearly = 0.0
        
    theta_daily = theta_yearly / 252.0  # مبنای تقویم معاملاتی ایران
    
    # کلیپ ایمن انفرادی
    delta = np.clip(delta, -1.0, 1.0)
    gamma = np.clip(gamma, 0.0, 50.0)
    
    return delta, gamma, theta_daily


@handle_numerical_issues
def calculate_vega(S: float, K: float, t: float, r: float, sigma: float) -> float:
    validate_inputs(S, K, t, r, sigma)
    if t < 1e-5 or sigma < 1e-5:
        return 0.0
    d1, _ = calculate_d1_d2(S, K, t, r, sigma)
    vega = S * np.sqrt(t) * norm.pdf(d1) / 100.0  # اثر ۱٪ تغییر نوسان‌پذیری
    return np.clip(vega, 0.0, 10.0)


@handle_numerical_issues
def calculate_rho(S: float, K: float, t: float, r: float, sigma: float, option_type: str) -> float:
    validate_inputs(S, K, t, r, sigma, option_type)
    if t < 1e-5:
        return 0.0
    _, d2 = calculate_d1_d2(S, K, t, r, sigma)
    if option_type.lower() == 'call':
        rho = K * t * np.exp(-r * t) * norm.cdf(d2) / 100.0
    else:
        rho = -K * t * np.exp(-r * t) * norm.cdf(-d2) / 100.0
    return rho


@handle_numerical_issues
def calculate_full_greeks(S: float, K: float, t: float, r: float, sigma: float, option_type: str) -> Dict[str, float]:
    delta, gamma, theta_daily = calculate_leg_greeks(S, K, t, r, sigma, option_type)
    vega = calculate_vega(S, K, t, r, sigma)
    rho = calculate_rho(S, K, t, r, sigma, option_type)
    return {
        'delta': delta,
        'gamma': gamma,
        'theta_daily': theta_daily,
        'vega': vega,
        'rho': rho
    }


# ============================================================================
# بخش ۴: مدیریت احتمالات و پورتفوی استراتژی
# ============================================================================

@handle_numerical_issues
def get_price_step_probabilities(
    S0: float,
    pct_steps: np.ndarray,
    t: float,
    r: float,
    sigma: float,
    normalize: bool = True
) -> np.ndarray:
    validate_inputs(S0, K=S0, t=t, r=r, sigma=sigma)
    
    if not isinstance(pct_steps, np.ndarray):
        pct_steps = np.array(pct_steps, dtype=float)
        
    if t <= 1e-5:
        probs = np.zeros_like(pct_steps, dtype=float)
        zero_idx = np.argmin(np.abs(pct_steps))
        probs[zero_idx] = 1.0
        return probs
        
    target_prices = S0 * (1.0 + pct_steps / 100.0)
    target_prices = np.maximum(target_prices, 1e-3)
    
    log_S_ratio = np.log(target_prices / S0)
    numerator = log_S_ratio - (r - 0.5 * sigma ** 2) * t
    denominator = sigma * np.sqrt(t)
    
    pdf_values = (1.0 / (target_prices * denominator)) * norm.pdf(numerator / denominator)
    
    if normalize:
        sum_pdf = np.sum(pdf_values)
        return pdf_values / sum_pdf if sum_pdf > 0 else np.ones_like(pct_steps) / len(pct_steps)
    return pdf_values


@handle_numerical_issues
def calculate_strategy_greeks(
    legs: List[Dict[str, Union[float, int, str]]],
    current_price: float,
    days_to_maturity: int,
    risk_free_rate: float = 0.20,
    volatility: float = 0.35,
    include_rho: bool = True
) -> Dict[str, float]:
    if not legs:
        return {'delta': 0.0, 'gamma': 0.0, 'theta_daily': 0.0, 'vega': 0.0}
        
    t = days_to_maturity / 365.0
    
    # یونانی‌های تجمعی خالص بدون کلیپ مخرب سبد
    total = {'delta': 0.0, 'gamma': 0.0, 'theta_daily': 0.0, 'vega': 0.0}
    if include_rho:
        total['rho'] = 0.0
        
    for leg in legs:
        position = leg['position']  # 1 خرید، -1 فروش
        greeks = calculate_full_greeks(
            S=current_price,
            K=leg['strike_price'],
            t=t,
            r=risk_free_rate,
            sigma=volatility,
            option_type=leg['option_type']
        )
        
        total['delta'] += position * greeks['delta']
        total['gamma'] += position * greeks['gamma']
        total['theta_daily'] += position * greeks['theta_daily']
        total['vega'] += position * greeks['vega']
        if include_rho:
            total['rho'] += position * greeks['rho']
            
    return {k: round(v, 4) for k, v in total.items()}