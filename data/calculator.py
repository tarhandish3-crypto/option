# data/calculator.py
# -*- coding: utf-8 -*-

import numpy as np
import pandas as pd
import requests
from scipy.stats import norm
from scipy.optimize import brentq
from typing import Optional, Union
import logging
import urllib3
from functools import lru_cache

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger("OptionScanner.Data.Calculator")


# =====================================================
# کش دانلود سابقه قیمت
# =====================================================

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


# =====================================================
# توابع کمکی برای brentq
# =====================================================

def _bsm_price_for_iv(sigma: float, S: float, K: float, T: float, r: float, is_call: bool) -> float:
    """محاسبه قیمت Black-Scholes برای یک sigma مشخص"""
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

    مزایا نسبت به Newton-Raphson:
    - پایدارتر (حتی برای آپشن‌های ITM/OTM شدید)
    - بدون نیاز به محاسبه Vega
    - همیشه همگرا می‌شود (در بازه مشخص)
    - مناسب برای داده‌های پرت و حباب‌های قیمتی
    """
    # محدوده جستجو
    MIN_IV = 0.01   # ۱٪
    MAX_IV = 5.0    # ۵۰۰٪

    # اگر قیمت بازار کمتر از ارزش ذاتی باشد → IV نامعتبر
    intrinsic = max(0, (S - K) if is_call else (K - S))
    if market_price <= intrinsic + 0.01:
        return 0.0

    # اگر T خیلی کوچک باشد، از روش تقریبی استفاده کن
    if T < 1/365:  # کمتر از ۱ روز
        return 0.0

    try:
        # ✅ استفاده از Brent's method (پایدارتر از Newton)
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
        # اگر brentq همگرا نشد، از جستجوی خطی استفاده کن
        return _find_iv_linear(S, K, T, r, market_price, is_call)
    except Exception as e:
        logger.debug(f"IV calculation failed: {e}")
        return 0.0


def _find_iv_linear(S: float, K: float, T: float, r: float,
                    market_price: float, is_call: bool) -> float:
    """
    جستجوی خطی ساده برای IV (Fallback در صورت عدم همگرایی brentq)
    """
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


# =====================================================
# کلاس اصلی
# =====================================================

class FinancialCalculator:
    """
    محاسبه‌گرهای مالی پیشرفته با استفاده از Brent's method برای IV
    """

    @staticmethod
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

    @staticmethod
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
            if code_str != '':
                vol_dict[code] = _fetch_underlying_history_cached(
                    code_str, window_size)
            else:
                vol_dict[code] = 0.35

        df['Volatility'] = df[instrument_col].map(vol_dict).fillna(0.35)
        return df

    @staticmethod
    def bsm_price_vectorized(S: np.ndarray, K: np.ndarray, T: np.ndarray,
                             r: float, sigma: np.ndarray, is_call: np.ndarray) -> np.ndarray:
        """محاسبه قیمت تئوریک Black-Scholes به صورت برداری"""
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

    @staticmethod
    def calculate_greeks_vectorized(df: pd.DataFrame, r_f: float) -> pd.DataFrame:
        """محاسبه یونانی‌ها به صورت برداری"""
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

        delta_raw = np.where(is_call, norm.cdf(d1), norm.cdf(d1) - 1)
        gamma_raw = pdf_d1 / (S * sigma_safe * sqrt_t)
        vega_raw = (S * sqrt_t * pdf_d1) / 100

        theta_call = -(S * pdf_d1 * sigma_safe) / \
            (2 * sqrt_t) - r_f * K * exp_rt * norm.cdf(d2)
        theta_put = -(S * pdf_d1 * sigma_safe) / (2 * sqrt_t) + \
            r_f * K * exp_rt * norm.cdf(-d2)
        theta_raw = np.where(is_call, theta_call, theta_put) / 365

        rho_raw = np.where(is_call, K * T_safe * exp_rt *
                           norm.cdf(d2), -K * T_safe * exp_rt * norm.cdf(-d2)) / 100

        df['Delta'] = np.where(days_to_mat <= 0, np.where(is_call, np.where(
            S > K, 1.0, 0.0), np.where(S < K, -1.0, 0.0)), delta_raw)
        df['Gamma'] = np.where(days_to_mat <= 0, 0.0, gamma_raw)
        df['Vega'] = np.where(days_to_mat <= 0, 0.0, vega_raw)
        df['Theta'] = np.where(days_to_mat <= 0, 0.0, theta_raw)
        df['Rho'] = np.where(days_to_mat <= 0, 0.0, rho_raw)

        df['BS_Price'] = FinancialCalculator.bsm_price_vectorized(
            S, K, T, r_f, sigma, is_call)

        return df

    @staticmethod
    def calculate_implied_volatility_vectorized(df: pd.DataFrame, r_f: float) -> pd.DataFrame:
        """
        محاسبه نوسان ضمنی با استفاده از Brent's method (پایدار و مقاوم)

        مزایا نسبت به Newton-Raphson:
        - ✅ همیشه همگرا می‌شود
        - ✅ بدون نیاز به محاسبه Vega
        - ✅ مقاوم در برابر حباب‌های قیمتی
        - ✅ مناسب برای بورس ایران
        """
        if df.empty:
            return df
        df = df.copy()

        price_col = 'UnderlyingPrice' if 'UnderlyingPrice' in df.columns else 'UA_LastPrice'

        if 'MidPrice' not in df.columns:
            if 'BidPrice' in df.columns and 'AskPrice' in df.columns:
                df['MidPrice'] = np.where((df['BidPrice'] > 0) & (df['AskPrice'] > 0),
                                          (df['BidPrice'] + df['AskPrice']) / 2, df['LastPrice'])
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

        # آپشن‌های معتبر برای محاسبه IV
        # ✅ فقط آپشن‌هایی که قیمت بازار > ارزش ذاتی و سررسید > ۰ دارند
        valid_mask = (market_price > intrinsic_val + 0.01) & (days_to_mat > 1)

        # مقدار پیش‌فرض
        default_vol = df['Volatility'].values if 'Volatility' in df.columns else 0.35

        # ✅ استفاده از Brent's method برای محاسبه IV
        iv_values = np.full_like(market_price, 0.35, dtype=float)

        # آمار برای لاگ
        valid_count = 0
        high_iv_count = 0

        for idx in range(len(df)):
            if not valid_mask[idx]:
                iv_values[idx] = default_vol[idx]
                continue

            try:
                iv = _find_iv_brentq(
                    S=S[idx],
                    K=K[idx],
                    T=T[idx],
                    r=r_f,
                    market_price=market_price[idx],
                    is_call=is_call[idx]
                )

                if iv > 0:
                    iv_values[idx] = iv
                    valid_count += 1
                    if iv > 2.0:  # > ۲۰۰٪
                        high_iv_count += 1
                else:
                    iv_values[idx] = default_vol[idx]

            except Exception as e:
                logger.debug(f"IV calculation failed for index {idx}: {e}")
                iv_values[idx] = default_vol[idx]

        # ✅ محدود کردن نهایی
        iv_values = np.clip(iv_values, 0.01, 5.0)

        if high_iv_count > 0:
            logger.info(
                f"High IV detected: {high_iv_count} contracts > 200% (capped at 500%)")

        logger.debug(
            f"IV calculated for {valid_count} contracts using Brent's method")

        df['ImpliedVolatility'] = iv_values

        if 'Volatility' in df.columns:
            hv_safe = np.where(df['Volatility'] <= 0, 0.01, df['Volatility'])
            df['IV_HV_Ratio'] = df['ImpliedVolatility'] / hv_safe
            df['IV_HV_Ratio'] = np.clip(df['IV_HV_Ratio'], 0.1, 100.0)

        return df

    @staticmethod
    def calculate_all(df: pd.DataFrame, r_f: Optional[float] = None) -> pd.DataFrame:
        """محاسبه تمام شاخص‌ها"""
        if df.empty:
            return df

        if r_f is None:
            r_f = FinancialCalculator.get_risk_free_rate()

        df = FinancialCalculator.calculate_historical_volatility_vectorized(df)
        df = FinancialCalculator.calculate_greeks_vectorized(df, r_f)
        df = FinancialCalculator.calculate_implied_volatility_vectorized(
            df, r_f)

        logger.info(f"Calculated all metrics for {len(df)} contracts")
        return df
