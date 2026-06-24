# data/calculator.py

import numpy as np
import pandas as pd
import requests
from scipy.stats import norm
from typing import Optional
import logging
import urllib3
from functools import lru_cache

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logger = logging.getLogger("OptionScanner.Data.Calculator")

# برای عملکرد ۱۰۰٪ تضمینی لایه کش کامپایلر پایتون در اجراهای مکرر،
# تابع دانلود دیتای تاریخی دارایی پایه را به خارج از کلاس منتقل می‌کنیم.
@lru_cache(maxsize=256)
def _fetch_underlying_history_cached(instrument_code: str, window_size: int) -> float:
    """نسخه امن و کَش‌شونده دانلود سابقه قیمت سهم پایه بدون درگیر کردن آبجکت کلاس"""
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
        annual_vol = np.std(log_returns, ddof=1) * np.sqrt(240)  # ۲۴۰ روز معاملاتی ایران

        return float(annual_vol) if not np.isnan(annual_vol) else 0.35
    except Exception:
        return 0.35


class FinancialCalculator:
    """
    محاسبه‌گرهای مالی پیشرفته با قابلیت برداری ایمن و مدیریت بهینه حافظه پنهان
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
            return 0.30
        except Exception:
            return 0.30

    @staticmethod
    def calculate_historical_volatility_vectorized(df: pd.DataFrame, window_size: int = 30) -> pd.DataFrame:
        """محاسبه نوسان‌پذیری تاریخی دارایی‌های پایه با کشینگ صددرصدی لایه گلوبال"""
        if df.empty: return df
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
                # فراخوانی تابع کش‌شده گلوبال
                vol_dict[code] = _fetch_underlying_history_cached(code_str, window_size)
            else:
                vol_dict[code] = 0.35

        df['Volatility'] = df[instrument_col].map(vol_dict).fillna(0.35)
        return df

    @staticmethod
    def bsm_price_vectorized(S: np.ndarray, K: np.ndarray, T: np.ndarray,
                             r: float, sigma: np.ndarray, is_call: np.ndarray) -> np.ndarray:
        """محاسبه قیمت تئوریک Black-Scholes"""
        T_safe = np.where(T <= 0, 1e-5, T)
        sigma_safe = np.where(sigma <= 0, 1e-5, sigma)

        d1 = (np.log(S / K) + (r + 0.5 * sigma_safe ** 2) * T_safe) / (sigma_safe * np.sqrt(T_safe))
        d2 = d1 - sigma_safe * np.sqrt(T_safe)

        call_price = S * norm.cdf(d1) - K * np.exp(-r * T_safe) * norm.cdf(d2)
        put_price = K * np.exp(-r * T_safe) * norm.cdf(-d2) - S * norm.cdf(-d1)

        # آپشن‌های منقضی شده ارزش تئوریکشان بر اساس ارزش ذاتی صفر یا مثبت است
        intrinsic_val = np.where(is_call, np.maximum(0, S - K), np.maximum(0, K - S))
        return np.where(T <= 0, intrinsic_val, np.where(is_call, call_price, put_price))

    @staticmethod
    def calculate_greeks_vectorized(df: pd.DataFrame, r_f: float) -> pd.DataFrame:
        """محاسبه یونانی‌ها به صورت برداری مجهز به فیلتر روز سررسید"""
        if df.empty: return df
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

        # ایجاد کپی‌های امن برای جلوگیری از خطای تقسیم بر صفر ریاضی
        T_safe = np.where(T <= 0, 1e-5, T)
        sigma_safe = np.where(sigma <= 0, 1e-5, sigma)

        d1 = (np.log(S / K) + (r_f + 0.5 * sigma_safe ** 2) * T_safe) / (sigma_safe * np.sqrt(T_safe))
        d2 = d1 - sigma_safe * np.sqrt(T_safe)

        pdf_d1 = norm.pdf(d1)
        sqrt_t = np.sqrt(T_safe)
        exp_rt = np.exp(-r_f * T_safe)

        # محاسبه خام برداری
        delta_raw = np.where(is_call, norm.cdf(d1), norm.cdf(d1) - 1)
        gamma_raw = pdf_d1 / (S * sigma_safe * sqrt_t)
        vega_raw = (S * sqrt_t * pdf_d1) / 100
        
        theta_call = -(S * pdf_d1 * sigma_safe) / (2 * sqrt_t) - r_f * K * exp_rt * norm.cdf(d2)
        theta_put = -(S * pdf_d1 * sigma_safe) / (2 * sqrt_t) + r_f * K * exp_rt * norm.cdf(-d2)
        theta_raw = np.where(is_call, theta_call, theta_put) / 365
        
        rho_raw = np.where(is_call, K * T_safe * exp_rt * norm.cdf(d2), -K * T_safe * exp_rt * norm.cdf(-d2)) / 100

        # فیلتر فریز عددی روز سررسید: اگر آپشن منقضی شده یا روز آخر است، یونانی‌ها صفر می‌شوند
        # (به جز دلتا که در زمان سررسید برای ابزارهای درون‌سود ۱ یا ۱- و برای برون‌سود ۰ مایل است)
        df['Delta'] = np.where(days_to_mat <= 0, np.where(is_call, np.where(S > K, 1.0, 0.0), np.where(S < K, -1.0, 0.0)), delta_raw)
        df['Gamma'] = np.where(days_to_mat <= 0, 0.0, gamma_raw)
        df['Vega'] = np.where(days_to_mat <= 0, 0.0, vega_raw)
        df['Theta'] = np.where(days_to_mat <= 0, 0.0, theta_raw)
        df['Rho'] = np.where(days_to_mat <= 0, 0.0, rho_raw)

        # قیمت تئوریک
        df['BS_Price'] = FinancialCalculator.bsm_price_vectorized(S, K, T, r_f, sigma, is_call)

        return df

    @staticmethod
    def calculate_implied_volatility_vectorized(df: pd.DataFrame, r_f: float,
                                                max_iterations: int = 25,
                                                tolerance: float = 1e-4) -> pd.DataFrame:
        """محاسبه نوسان ضمنی با روش Newton-Raphson لایه محافظتی انقضا"""
        if df.empty: return df
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

        T_safe = np.where(T <= 0, 1e-5, T)
        iv_sigma = np.full_like(market_price, 0.35, dtype=float)

        intrinsic_val = np.where(is_call, np.maximum(0, S - K), np.maximum(0, K - S))
        # فیلتر آپشن‌های زنده و دارای حباب مثبت برای محاسبه IV
        valid_mask = (market_price > intrinsic_val) & (days_to_mat > 0)

        for _ in range(max_iterations):
            d1 = (np.log(S / K) + (r_f + 0.5 * iv_sigma ** 2) * T_safe) / (iv_sigma * np.sqrt(T_safe))
            d2 = d1 - iv_sigma * np.sqrt(T_safe)

            call_price = S * norm.cdf(d1) - K * np.exp(-r_f * T_safe) * norm.cdf(d2)
            put_price = K * np.exp(-r_f * T_safe) * norm.cdf(-d2) - S * norm.cdf(-d1)
            theo_price = np.where(is_call, call_price, put_price)

            vega = S * np.sqrt(T_safe) * norm.pdf(d1)
            vega = np.where(vega < 1e-4, 1e-4, vega)

            diff = theo_price - market_price
            iv_sigma_new = iv_sigma - diff / vega
            iv_sigma_new = np.clip(iv_sigma_new, 0.05, 2.0)

            if np.max(np.abs(iv_sigma_new - iv_sigma)) < tolerance:
                iv_sigma = iv_sigma_new
                break

            iv_sigma = iv_sigma_new

        default_vol = df['Volatility'].values if 'Volatility' in df.columns else 0.35
        df['ImpliedVolatility'] = np.where(valid_mask, iv_sigma, default_vol)

        if 'Volatility' in df.columns:
            df['IV_HV_Ratio'] = df['ImpliedVolatility'] / df['Volatility']

        return df

    @staticmethod
    def calculate_all(df: pd.DataFrame, r_f: Optional[float] = None) -> pd.DataFrame:
        if df.empty: return df

        if r_f is None:
            r_f = FinancialCalculator.get_risk_free_rate()

        df = FinancialCalculator.calculate_historical_volatility_vectorized(df)
        df = FinancialCalculator.calculate_greeks_vectorized(df, r_f)
        df = FinancialCalculator.calculate_implied_volatility_vectorized(df, r_f)

        logger.info(f"Calculated all metrics for {len(df)} contracts")
        return df