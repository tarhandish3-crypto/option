# data/calculator.py
# -*- coding: utf-8 -*-

"""
ماژول محاسبات پایه مالی - لایه Pure Functions

"""

import numpy as np
import pandas as pd
import requests
from scipy.stats import norm
from scipy.optimize import brentq
from typing import Optional, Union, Tuple, List, Dict
import logging
import urllib3
from functools import lru_cache
import warnings

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger("OptionScanner.Data.Calculator")


# =====================================================
# بخش ۱: اعتبارسنجی و مدیریت خطا
# =====================================================

def validate_inputs(
        S: float,
        K: float,
        t: float,
        r: float,
        sigma: float,
        option_type: Optional[str] = None) -> None:
    """
    اعتبارسنجی ورودی‌های محاسباتی

    Args:
        S: قیمت دارایی پایه
        K: قیمت اعمال
        t: زمان تا سررسید (سال)
        r: نرخ بهره بدون ریسک
        sigma: نوسان‌پذیری
        option_type: نوع اختیار ('call' یا 'put')

    Raises:
        ValueError: در صورت نامعتبر بودن ورودی‌ها
        Warning: در صورت شرایط مرزی
    """
    if S <= 0:
        raise ValueError(f"قیمت پایه (S) باید مثبت باشد: {S}")
    if K <= 0:
        raise ValueError(f"قیمت اعمال (K) باید مثبت باشد: {K}")
    if t < 0:
        raise ValueError(f"زمان تا سررسید (t) نمی‌تواند منفی باشد: {t}")
    if t == 0:
        warnings.warn("زمان تا سررسید صفر است (سررسید امروز)")
    if r < 0:
        warnings.warn(f"نرخ بهره (r) منفی است: {r}")
    if sigma <= 0:
        raise ValueError(f"نوسان‌پذیری (sigma) باید مثبت باشد: {sigma}")
    if option_type is not None:
        if option_type.lower() not in ['call', 'put']:
            raise ValueError(f"نوع آپشن نامعتبر: {option_type}")


def handle_numerical_issues(func):
    """
    دکوراتور برای کنترل پایداری عددی سیستم مالی

    ویژگی‌ها:
    - تبدیل NaN و Inf به 0
    - مدیریت استثناها
    - بازگشت مقادیر پیش‌فرض در صورت خطا
    """
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
            warnings.warn(f"خطای محاسباتی: {e}")
            return 0.0 if not func.__annotations__.get('return') == dict else {}
    return wrapper


# =====================================================
# بخش ۲: محاسبات پایه بلک-شولز
# =====================================================

@handle_numerical_issues
def calculate_d1_d2(
        S: float,
        K: float,
        t: float,
        r: float,
        sigma: float) -> Tuple[float, float]:
    """
    محاسبه d1 و d2 برای فرمول بلک-شولز

    Returns:
        Tuple[float, float]: (d1, d2)
    """
    validate_inputs(S, K, t, r, sigma)

    # کنترل شرایط مرزی در سررسید لحظه‌ای
    if t < 1e-5 or sigma < 1e-5:
        if S >= K:
            return 10.0, 10.0
        else:
            return -10.0, -10.0

    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * t) / (sigma * np.sqrt(t))
    d2 = d1 - sigma * np.sqrt(t)

    # کلیپ برای پایداری توزیع نرمال
    d1 = np.clip(d1, -10, 10)
    d2 = np.clip(d2, -10, 10)

    return d1, d2


@handle_numerical_issues
def calculate_bsm_price(
        S: float,
        K: float,
        t: float,
        r: float,
        sigma: float,
        option_type: str) -> float:
    """
    محاسبه قیمت تئوریک بلک-شولز برای یک قرارداد

    Args:
        option_type: 'call' یا 'put'

    Returns:
        float: قیمت تئوریک
    """
    validate_inputs(S, K, t, r, sigma, option_type)

    if t <= 0:
        intrinsic = max(0, (S - K) if option_type.lower()
                        == 'call' else (K - S))
        return intrinsic

    d1, d2 = calculate_d1_d2(S, K, t, r, sigma)

    if option_type.lower() == 'call':
        price = S * norm.cdf(d1) - K * np.exp(-r * t) * norm.cdf(d2)
    else:
        price = K * np.exp(-r * t) * norm.cdf(-d2) - S * norm.cdf(-d1)

    return max(0.0, price)


# =====================================================
# بخش ۳: محاسبه یونانی‌های تک پایه (Leg)
# =====================================================

@handle_numerical_issues
def calculate_delta(
        S: float,
        K: float,
        t: float,
        r: float,
        sigma: float,
        option_type: str) -> float:
    """
    محاسبه دلتا (حساسیت به تغییرات قیمت پایه)

    Returns:
        float: دلتا (بین -1 و 1)
    """
    validate_inputs(S, K, t, r, sigma, option_type)

    if t <= 0:
        if option_type.lower() == 'call':
            return 1.0 if S > K else 0.0
        else:
            return -1.0 if S < K else 0.0

    d1, _ = calculate_d1_d2(S, K, t, r, sigma)
    delta = norm.cdf(d1) if option_type.lower(
    ) == 'call' else norm.cdf(d1) - 1.0

    return np.clip(delta, -1.0, 1.0)


@handle_numerical_issues
def calculate_gamma(
        S: float,
        K: float,
        t: float,
        r: float,
        sigma: float) -> float:
    """
    محاسبه گاما (نرخ تغییر دلتا)

    Returns:
        float: گاما (همیشه مثبت)
    """
    validate_inputs(S, K, t, r, sigma)

    if t <= 0 or sigma <= 0:
        return 0.0

    d1, _ = calculate_d1_d2(S, K, t, r, sigma)
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(t))

    return np.clip(gamma, 0.0, 50.0)


@handle_numerical_issues
def calculate_theta(
        S: float,
        K: float,
        t: float,
        r: float,
        sigma: float,
        option_type: str,
        days_per_year: int = 252) -> float:
    """
    محاسبه تتا روزانه (حساسیت به گذشت زمان)

    Args:
        days_per_year: تعداد روزهای معاملاتی در سال (ایران: 252)

    Returns:
        float: تتا روزانه
    """
    validate_inputs(S, K, t, r, sigma, option_type)

    if t <= 0 or sigma <= 0:
        return 0.0

    d1, d2 = calculate_d1_d2(S, K, t, r, sigma)
    pdf_d1 = norm.pdf(d1)
    sqrt_t = np.sqrt(t)
    exp_rt = np.exp(-r * t)

    if option_type.lower() == 'call':
        theta_yearly = -(S * pdf_d1 * sigma) / (2 * sqrt_t) - \
            r * K * exp_rt * norm.cdf(d2)
    else:
        theta_yearly = -(S * pdf_d1 * sigma) / (2 * sqrt_t) + \
            r * K * exp_rt * norm.cdf(-d2)

    return theta_yearly / days_per_year


@handle_numerical_issues
def calculate_vega(
        S: float,
        K: float,
        t: float,
        r: float,
        sigma: float) -> float:
    """
    محاسبه وگا (تغییر قیمت به ازای ۱٪ تغییر در نوسان)

    Returns:
        float: وگا (به ازای ۱٪ تغییر)
    """
    validate_inputs(S, K, t, r, sigma)

    if t <= 0 or sigma <= 0:
        return 0.0

    d1, _ = calculate_d1_d2(S, K, t, r, sigma)
    vega = S * np.sqrt(t) * norm.pdf(d1) / 100.0

    return np.clip(vega, 0.0, 10.0)


@handle_numerical_issues
def calculate_rho(
        S: float,
        K: float,
        t: float,
        r: float,
        sigma: float,
        option_type: str) -> float:
    """
    محاسبه رو (تغییر قیمت به ازای ۱٪ تغییر در نرخ بهره)

    Returns:
        float: رو (به ازای ۱٪ تغییر)
    """
    validate_inputs(S, K, t, r, sigma, option_type)

    if t <= 0:
        return 0.0

    _, d2 = calculate_d1_d2(S, K, t, r, sigma)
    exp_rt = np.exp(-r * t)

    if option_type.lower() == 'call':
        rho = K * t * exp_rt * norm.cdf(d2) / 100.0
    else:
        rho = -K * t * exp_rt * norm.cdf(-d2) / 100.0

    return rho


@handle_numerical_issues
def calculate_full_greeks(
        S: float,
        K: float,
        t: float,
        r: float,
        sigma: float,
        option_type: str) -> Dict[str, float]:
    """
    محاسبه تمام یونانی‌ها برای یک قرارداد

    Returns:
        Dict[str, float]: شامل delta, gamma, theta, vega, rho
    """
    return {
        'delta': calculate_delta(S, K, t, r, sigma, option_type),
        'gamma': calculate_gamma(S, K, t, r, sigma),
        'theta': calculate_theta(S, K, t, r, sigma, option_type),
        'vega': calculate_vega(S, K, t, r, sigma),
        'rho': calculate_rho(S, K, t, r, sigma, option_type)
    }


# =====================================================
# بخش ۴: نوسان ضمنی (Implied Volatility)
# =====================================================

def _bsm_price_for_iv(sigma: float, S: float, K: float, T: float, r: float, is_call: bool) -> float:
    """محاسبه قیمت Black-Scholes برای یک sigma مشخص (داخلی)"""
    if sigma <= 0:
        sigma = 1e-6
    if T <= 0:
        T = 1e-5

    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if is_call:
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

    return price


def _iv_objective(sigma: float, S: float, K: float, T: float, r: float,
                  market_price: float, is_call: bool) -> float:
    """تابع هدف برای brentq: تفاوت قیمت بازار و قیمت تئوریک"""
    theo = _bsm_price_for_iv(sigma, S, K, T, r, is_call)
    return theo - market_price


def _find_iv_brentq(S: float, K: float, T: float, r: float,
                    market_price: float, is_call: bool) -> float:
    """
    محاسبه نوسان ضمنی با استفاده از Brent's method
    """
    MIN_IV = 0.01
    MAX_IV = 5.0

    intrinsic = max(0, (S - K) if is_call else (K - S))
    if market_price <= intrinsic + 0.01:
        return 0.0

    if T < 1/365:
        return 0.0

    try:
        iv = brentq(
            _iv_objective,
            MIN_IV,
            MAX_IV,
            args=(S, K, T, r, market_price, is_call),
            xtol=1e-6,
            maxiter=50
        )
        return float(iv)
    except ValueError:
        return _find_iv_linear(S, K, T, r, market_price, is_call)
    except Exception:
        return 0.0


def _find_iv_linear(S: float, K: float, T: float, r: float,
                    market_price: float, is_call: bool) -> float:
    """جستجوی خطی برای IV (Fallback)"""
    MIN_IV = 0.01
    MAX_IV = 5.0
    STEPS = 100

    best_sigma = 0.35
    best_diff = float('inf')

    for i in range(STEPS + 1):
        sigma = MIN_IV + (MAX_IV - MIN_IV) * i / STEPS
        theo = _bsm_price_for_iv(sigma, S, K, T, r, is_call)
        diff = abs(theo - market_price)

        if diff < best_diff:
            best_diff = diff
            best_sigma = sigma

        if diff < 0.01:
            break

    return best_sigma


@handle_numerical_issues
def calculate_implied_volatility(
        S: float,
        K: float,
        T: float,
        r: float,
        market_price: float,
        option_type: str) -> float:
    """
    محاسبه نوسان ضمنی برای یک قرارداد

    Returns:
        float: نوسان ضمنی (بین 0.01 و 5.0)
    """
    validate_inputs(S, K, T, r, 0.35, option_type)
    is_call = option_type.lower() == 'call'

    iv = _find_iv_brentq(S, K, T, r, market_price, is_call)
    return np.clip(iv, 0.01, 5.0)


# =====================================================
# بخش ۵: احتمالات و توزیع
# =====================================================

@handle_numerical_issues
def calculate_price_step_probabilities(
        S0: float,
        pct_steps: np.ndarray,
        t: float,
        r: float,
        sigma: float,
        normalize: bool = True) -> np.ndarray:
    """
    محاسبه توزیع احتمال قیمت در زمان t با استفاده از توزیع لگ-نرمال

    Args:
        S0: قیمت فعلی
        pct_steps: مراحل درصدی (مثلاً [-10, -5, 0, 5, 10])
        t: زمان تا سررسید (سال)
        r: نرخ بهره بدون ریسک
        sigma: نوسان‌پذیری
        normalize: آیا توزیع نرمال‌سازی شود؟

    Returns:
        np.ndarray: توزیع احتمال برای هر مرحله
    """
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

    pdf_values = (1.0 / (target_prices * denominator)) * \
        norm.pdf(numerator / denominator)

    if normalize:
        sum_pdf = np.sum(pdf_values)
        return pdf_values / sum_pdf if sum_pdf > 0 else np.ones_like(pct_steps) / len(pct_steps)
    return pdf_values


@handle_numerical_issues
def calculate_probability_of_profit(
        S0: float,
        K: float,
        t: float,
        r: float,
        sigma: float,
        option_type: str,
        entry_price: float) -> float:
    """
    محاسبه احتمال سودآوری برای یک قرارداد

    Args:
        entry_price: قیمت ورودی (قیمت خرید یا فروش)

    Returns:
        float: احتمال سودآوری (بین 0 و 1)
    """
    validate_inputs(S0, K, t, r, sigma, option_type)

    if option_type.lower() == 'call':
        break_even = K + entry_price
        d_break_even = (np.log(S0 / break_even) + (r - 0.5 *
                        sigma**2) * t) / (sigma * np.sqrt(t))
        return 1 - norm.cdf(d_break_even)
    else:  # PUT
        break_even = K - entry_price
        d_break_even = (np.log(S0 / break_even) + (r - 0.5 *
                        sigma**2) * t) / (sigma * np.sqrt(t))
        return norm.cdf(d_break_even)


# =====================================================
# بخش ۶: محاسبات برداری (Vectorized) برای پردازش انبوه
# =====================================================

# --------------------------------------------
# ۶-۱: کش دانلود سابقه قیمت
# --------------------------------------------

@lru_cache(maxsize=256)
def _fetch_underlying_history_cached(instrument_code: str, window_size: int) -> float:
    """نسخه امن و کَش‌شونده دانلود سابقه قیمت سهم پایه"""
    if not instrument_code or pd.isna(instrument_code):
        return 0.35

    url = f'https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceHistory/{instrument_code}'
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=3, verify=False)
        data = response.json().get('closingPriceHistory', [])

        if not data or len(data) < window_size + 1:
            return 0.35

        df = pd.DataFrame(data)
        prices = df['pClosing'].tail(window_size + 1).values

        log_returns = np.log(prices[1:] / prices[:-1])
        annual_vol = np.std(log_returns, ddof=1) * np.sqrt(240)

        return float(annual_vol) if not np.isnan(annual_vol) else 0.35
    except Exception:
        return 0.35


# --------------------------------------------
# ۶-۲: توابع برداری
# --------------------------------------------

def bsm_price_vectorized(
        S: np.ndarray,
        K: np.ndarray,
        T: np.ndarray,
        r: float,
        sigma: np.ndarray,
        is_call: np.ndarray) -> np.ndarray:
    """
    محاسبه قیمت تئوریک Black-Scholes به صورت برداری

    Args:
        S: آرایه قیمت‌های پایه
        K: آرایه قیمت‌های اعمال
        T: آرایه زمان‌های تا سررسید (سال)
        r: نرخ بهره
        sigma: آرایه نوسان‌پذیری
        is_call: آرایه بولین (True برای CALL)

    Returns:
        np.ndarray: آرایه قیمت‌های تئوریک
    """
    T_safe = np.where(T <= 0, 1e-5, T)
    sigma_safe = np.where(sigma <= 0, 1e-5, sigma)

    d1 = (np.log(S / K) + (r + 0.5 * sigma_safe ** 2)
          * T_safe) / (sigma_safe * np.sqrt(T_safe))
    d2 = d1 - sigma_safe * np.sqrt(T_safe)

    call_price = S * norm.cdf(d1) - K * np.exp(-r * T_safe) * norm.cdf(d2)
    put_price = K * np.exp(-r * T_safe) * norm.cdf(-d2) - S * norm.cdf(-d1)

    intrinsic_val = np.where(is_call, np.maximum(
        0, S - K), np.maximum(0, K - S))
    return np.where(T <= 0, intrinsic_val, np.where(is_call, call_price, put_price))


def calculate_greeks_vectorized(df: pd.DataFrame, r_f: float) -> pd.DataFrame:
    """
    محاسبه یونانی‌ها به صورت برداری
    """
    if df.empty:
        return df

    df = df.copy()
    price_col = 'UnderlyingPrice' if 'UnderlyingPrice' in df.columns else 'UA_LastPrice'

    S = df[price_col].values.astype(float)
    K = df['StrikePrice'].values.astype(float)
    days_to_mat = df['DaysToMaturity'].values.astype(float)
    T = days_to_mat / 365.0

    if 'Volatility' in df.columns:
        sigma = df['Volatility'].values.astype(float)
    else:
        sigma = np.full(len(df), 0.35, dtype=float)

    is_call = (df['Type'] == 'Call').values

    T_safe = np.where(T <= 0, 1e-5, T)
    sigma_safe = np.where(sigma <= 0, 1e-5, sigma)

    d1 = (np.log(S / K) + (r_f + 0.5 * sigma_safe ** 2)
          * T_safe) / (sigma_safe * np.sqrt(T_safe))
    d2 = d1 - sigma_safe * np.sqrt(T_safe)

    pdf_d1 = norm.pdf(d1)
    sqrt_t = np.sqrt(T_safe)
    exp_rt = np.exp(-r_f * T_safe)

    # محاسبه یونانی‌ها
    delta_raw = np.where(is_call, norm.cdf(d1), norm.cdf(d1) - 1)
    gamma_raw = pdf_d1 / (S * sigma_safe * sqrt_t)
    vega_raw = (S * sqrt_t * pdf_d1) / 100

    theta_call = -(S * pdf_d1 * sigma_safe) / (2 * sqrt_t) - \
        r_f * K * exp_rt * norm.cdf(d2)
    theta_put = -(S * pdf_d1 * sigma_safe) / (2 * sqrt_t) + \
        r_f * K * exp_rt * norm.cdf(-d2)
    theta_raw = np.where(is_call, theta_call, theta_put) / 365

    rho_raw = np.where(is_call, K * T_safe * exp_rt * norm.cdf(d2),
                       -K * T_safe * exp_rt * norm.cdf(-d2)) / 100

    # اعمال شرایط مرزی
    df['Delta'] = np.where(days_to_mat <= 0,
                           np.where(is_call, np.where(S > K, 1.0, 0.0),
                                    np.where(S < K, -1.0, 0.0)),
                           delta_raw)
    df['Gamma'] = np.where(days_to_mat <= 0, 0.0, gamma_raw)
    df['Vega'] = np.where(days_to_mat <= 0, 0.0, vega_raw)
    df['Theta'] = np.where(days_to_mat <= 0, 0.0, theta_raw)
    df['Rho'] = np.where(days_to_mat <= 0, 0.0, rho_raw)
    df['BS_Price'] = bsm_price_vectorized(S, K, T, r_f, sigma, is_call)

    # کلیپ نهایی برای پایداری
    df['Delta'] = np.clip(df['Delta'], -1.0, 1.0)
    df['Gamma'] = np.clip(df['Gamma'], 0.0, 50.0)
    df['Vega'] = np.clip(df['Vega'], 0.0, 10.0)

    return df


def calculate_implied_volatility_vectorized(df: pd.DataFrame, r_f: float) -> pd.DataFrame:
    """
    محاسبه نوسان ضمنی به صورت برداری با استفاده از Brent's method
    """
    if df.empty:
        return df

    df = df.copy()
    price_col = 'UnderlyingPrice' if 'UnderlyingPrice' in df.columns else 'UA_LastPrice'

    # محاسبه قیمت میانه
    if 'MidPrice' not in df.columns:
        if 'BidPrice' in df.columns and 'AskPrice' in df.columns:
            df['MidPrice'] = np.where((df['BidPrice'] > 0) & (df['AskPrice'] > 0),
                                      (df['BidPrice'] + df['AskPrice']) / 2,
                                      df['LastPrice'])
        else:
            df['MidPrice'] = df['LastPrice']

    S = df[price_col].values.astype(float)
    K = df['StrikePrice'].values.astype(float)
    days_to_mat = df['DaysToMaturity'].values.astype(float)
    T = days_to_mat / 365.0
    market_price = df['MidPrice'].values.astype(float)
    is_call = (df['Type'] == 'Call').values

    # ارزش ذاتی
    intrinsic_val = np.where(is_call, np.maximum(
        0, S - K), np.maximum(0, K - S))
    valid_mask = (market_price > intrinsic_val + 0.01) & (days_to_mat > 1)

    default_vol = df['Volatility'].values if 'Volatility' in df.columns else np.full(
        len(df), 0.35, dtype=float)
    iv_values = np.full_like(market_price, 0.35, dtype=float)

    valid_count = 0
    for idx in range(len(df)):
        if not valid_mask[idx]:
            iv_values[idx] = default_vol[idx]
            continue

        iv = _find_iv_brentq(
            S=S[idx],
            K=K[idx],
            T=T[idx],
            r=r_f,
            market_price=market_price[idx],
            is_call=is_call[idx])
        iv_values[idx] = iv if iv > 0 else default_vol[idx]
        valid_count += 1

    iv_values = np.clip(iv_values, 0.01, 5.0)
    df['ImpliedVolatility'] = iv_values

    if 'Volatility' in df.columns:
        hv_safe = np.where(df['Volatility'] <= 0, 0.01, df['Volatility'])
        df['IV_HV_Ratio'] = np.clip(
            df['ImpliedVolatility'] / hv_safe, 0.1, 100.0)

    logger.debug(
        f"IV calculated for {valid_count} contracts using Brent's method")
    return df


def calculate_historical_volatility_vectorized(df: pd.DataFrame, window_size: int = 30) -> pd.DataFrame:
    """محاسبه نوسان‌پذیری تاریخی دارایی‌های پایه"""
    if df.empty:
        return df

    df = df.copy()
    instrument_col = 'InstrumentCode-UA' if 'InstrumentCode-UA' in df.columns else 'UA_InstrumentCode'

    if instrument_col not in df.columns:
        df['Volatility'] = 0.35
        return df

    unique_codes = df[instrument_col].dropna().unique()
    vol_dict = {}

    for code in unique_codes:
        code_str = str(code).strip()
        vol_dict[code] = _fetch_underlying_history_cached(
            code_str, window_size) if code_str else 0.35

    df['Volatility'] = df[instrument_col].map(vol_dict).fillna(0.35)
    return df


def get_risk_free_rate() -> float:
    """دریافت نرخ بهره بدون ریسک از API بانک مرکزی"""
    try:
        url = 'https://www.cbi.ir/api/v1/InterestRate/List'
        response = requests.get(url, timeout=3, verify=False)
        if response.status_code == 200:
            data = response.json()
            if data and 'InterbankOnedayDepositRate' in data[0]:
                return float(data[0]['InterbankOnedayDepositRate']) / 100
        return 0.24
    except Exception:
        return 0.24


def calculate_all(df: pd.DataFrame, r_f: Optional[float] = None) -> pd.DataFrame:
    """محاسبه تمام شاخص‌ها به صورت یکجا"""
    if df.empty:
        return df

    if r_f is None:
        r_f = get_risk_free_rate()

    df = calculate_historical_volatility_vectorized(df)
    df = calculate_greeks_vectorized(df, r_f)
    df = calculate_implied_volatility_vectorized(df, r_f)

    logger.info(f"Calculated all metrics for {len(df)} contracts")
    return df
