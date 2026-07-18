# 0myStrategy/covered_call_analyzer.py
# -*- coding: utf-8 -*-

# تنظیم مسیر پروژه
from scipy.optimize import brentq
from scipy.stats import norm
import warnings
import logging
import numpy as np
import pandas as pd
import os
from data.downloader import MarketDownloader
from data.cleaner import DataCleaner
from config import (
    EXERCISE_TAX_RATE,
    get_symbol_market,
    get_symbol_kind,
    get_commission_rate,
    get_exercise_fee_rate)
from pathlib import Path
import sys
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

# ایمپورت ماژول‌های پروژه
warnings.filterwarnings('ignore')

# تنظیم لاگر
logger = logging.getLogger(__name__)

# =============================================
# نرخ بهره بدون ریسک ثابت
# =============================================
RISK_FREE_RATE = 0.30  # ۳۰ درصد


# ==========================================================================================
# ۱. توابع بلک-شولز و یونانی‌های مورد نیاز
# ==========================================================================================

def calculate_d1_d2(S, K, T, r, sigma):
    """
    محاسبه d1 و d2 برای فرمول بلک-شولز
    """
    if T <= 0 or sigma <= 0:
        return 10.0, 10.0 if S >= K else -10.0, -10.0

    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    return np.clip(d1, -10, 10), np.clip(d2, -10, 10)


def calculate_bsm_price(S, K, T, r, sigma):
    """
    محاسبه قیمت بلک-شولز برای اختیار خرید (CALL)

    Returns:
        float: قیمت تئوریک
    """
    if T <= 0:
        return max(0, S - K)

    if sigma <= 0:
        return max(0, S - K * np.exp(-r * T))

    d1, d2 = calculate_d1_d2(S, K, T, r, sigma)
    return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)


def calculate_delta(S, K, T, r, sigma):
    """
    محاسبه دلتا (Δ) - برای امتیازدهی

    Returns:
        float: دلتا بین 0 تا 1
    """
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0

    d1, _ = calculate_d1_d2(S, K, T, r, sigma)
    return np.clip(norm.cdf(d1), 0.0, 1.0)


def calculate_gamma(S, K, T, r, sigma):
    """
    محاسبه گاما (Γ) - برای تحلیل ریسک (اختیاری)

    Returns:
        float: گاما
    """
    if T <= 0 or sigma <= 0:
        return 0.0

    d1, _ = calculate_d1_d2(S, K, T, r, sigma)
    return norm.pdf(d1) / (S * sigma * np.sqrt(T))


def calculate_theta(S, K, T, r, sigma):
    """
    محاسبه تتا روزانه (Θ) - برای تحلیل سود گذشت زمان

    Returns:
        float: تتا روزانه
    """
    if T <= 0 or sigma <= 0:
        return 0.0

    d1, d2 = calculate_d1_d2(S, K, T, r, sigma)
    pdf_d1 = norm.pdf(d1)
    sqrt_t = np.sqrt(T)
    exp_rt = np.exp(-r * T)

    theta_yearly = -(S * pdf_d1 * sigma) / (2 * sqrt_t) - \
        r * K * exp_rt * norm.cdf(d2)
    return theta_yearly / 252  # تتا روزانه


def calculate_iv_from_price(S, K, T, r, market_price):
    """
    محاسبه نوسان ضمنی (IV) از قیمت بازار
    """
    if market_price <= 0 or T <= 0 or S <= 0 or K <= 0:
        return 0.45

    intrinsic = max(0, S - K)
    if market_price <= intrinsic + 1e-6:
        return 0.45

    def objective(sigma):
        return calculate_bsm_price(S, K, T, r, sigma) - market_price

    try:
        iv = brentq(objective, 0.01, 5.0, xtol=1e-6, maxiter=50)
        return np.clip(iv, 0.01, 5.0)
    except (ValueError, RuntimeError):
        # Fallback: جستجوی خطی
        best_sigma = 0.35
        best_diff = float('inf')
        for sigma in np.linspace(0.01, 5.0, 100):
            price = calculate_bsm_price(S, K, T, r, sigma)
            diff = abs(price - market_price)
            if diff < best_diff:
                best_diff = diff
                best_sigma = sigma
            if diff < 0.01:
                break
        return np.clip(best_sigma, 0.01, 5.0)


def add_bsm_and_greeks(df, r=RISK_FREE_RATE):
    """
    افزودن ستون‌های IV، Delta، Gamma، Theta و BS_Price به دیتافریم

    ستون‌های اضافه‌شده:
        - ImpliedVolatility: نوسان ضمنی
        - Delta: دلتا
        - Gamma: گاما
        - Theta: تتا روزانه
        - BS_Price: قیمت تئوریک بلک-شولز
    """
    df = df.copy()

    # ستون‌های خروجی با مقدار پیش‌فرض
    df['ImpliedVolatility'] = 0.45
    df['Delta'] = 0.50
    df['Gamma'] = 0.0
    df['Theta'] = 0.0
    df['BS_Price'] = 0.0

    total = len(df)

    for idx, row in df.iterrows():
        S = row['UnderlyingPrice']
        K = row['StrikePrice']
        T = row['DaysToMaturity'] / 252.0
        market_price = row['LastPrice'] if row['LastPrice'] > 0 else row['BidPrice']

        # محاسبه IV
        iv = calculate_iv_from_price(S, K, T, r, market_price)
        df.loc[idx, 'ImpliedVolatility'] = iv

        # محاسبه یونانی‌ها با IV
        sigma = iv if iv > 0 else 0.45
        df.loc[idx, 'Delta'] = calculate_delta(S, K, T, r, sigma)
        df.loc[idx, 'Gamma'] = calculate_gamma(S, K, T, r, sigma)
        df.loc[idx, 'Theta'] = calculate_theta(S, K, T, r, sigma)
        df.loc[idx, 'BS_Price'] = calculate_bsm_price(S, K, T, r, sigma)

        # نمایش پیشرفت
        if (idx + 1) % 100 == 0 or (idx + 1) == total:
            print(f"{idx + 1}/{total}")

    return df

# ==========================================================================================
# 2. توابع هسته محاسباتی مالی
# ==========================================================================================


def covered_call_with_fees(ticker, premium_call, stock_price, strike_price, contract_size,
                           opt_sell_commission, stock_buy_commission, exercise_fee_rate, exercise_tax_rate, days):

    # ====================== 1. کارمزدهای ورود (همیشه اعمال می‌شوند) ======================
    # کارمزد فروش اختیار
    option_fee = -round(premium_call * contract_size * opt_sell_commission, 0)
    # کارمزد خرید سهام
    stock_buy_fee = -round(stock_price * contract_size *
                           stock_buy_commission, 0)
    # کل کارمزد ورود به استراتژی
    entry_fees = option_fee + stock_buy_fee

    # ====================== 2. کارمزدهای خروج/اعمال  ======================
    exercise_fee = -round(strike_price * contract_size * exercise_fee_rate, 0)
    # مالیات اعمال
    exercise_tax = -round(strike_price * contract_size * exercise_tax_rate, 0)

    # ====================== 3. مبالغ اصلی ======================
    premium_received = premium_call * contract_size     # دریافتی از فروش اختیار
    stock_cost = -stock_price * contract_size           # ارزش خرید سهام

    # ====================== 4. سرمایه اولیه خالص ======================
    # سرمایه خالص درگیر (جریان نقدی اولیه)
    net_investment = stock_cost + premium_received + entry_fees

    # تحویل سهام در قیمت اعمال (دریافت وجه)
    strike_received = strike_price * contract_size

    # تحویل سهام در قیمت اعمال (دریافت وجه خالص)
    net_received = strike_received + exercise_fee + exercise_tax

    # ====================== 5. سود خالص ======================
    net_profit = net_received + net_investment

    # ====================== 6. درصد بازده ======================
    profit_percent = (round((net_profit / abs(net_investment))
                      * 100, 2) if net_investment != 0 else 0)
    monthly_return = round(profit_percent * (30 / days), 2)

    # ====================== 7. قیمت سربه‌سر (فقط سناریوی اصلی) ======================
    downside_protection = premium_received + \
        entry_fees + exercise_fee + exercise_tax

    # قیمتی که در آن سرمایه اولیه جبران شود
    break_even_price = round(
        stock_price - (downside_protection / contract_size), 0)

    # ====================== 8. درصد افت مجاز (فقط سناریوی اصلی) ======================
    max_drop_percent = round(
        ((stock_price - break_even_price) / stock_price) * 100, 2)

    return {
        'net_profit': net_profit,
        'monthly_return': monthly_return,
        'break_even_price': break_even_price,
        'max_drop_percent': max_drop_percent}


def score_covered_call_adapted(row):
    """
    سیستم امتیازدهی استراتژی Covered Call منطبق با ساختار ستون‌های سلول قبل
    """
    monthly_return = row.get('monthly_return_%', 0)
    max_drop = row.get('max_drop_%', 0)
    dte = row.get('days_to_maturity', 30)
    stock_price = row.get('stock_price', 1)
    strike = row.get('strike', 1)
    iv = row.get('IV', 0.45)
    delta = row.get('Delta', 0.50)

    # امتیاز بازده (سقف 12%)
    return_score = np.clip(monthly_return / 12.0, 0.0, 1.0)

    # امتیاز حاشیه امنیت (سقف 25%)
    protection_score = np.clip(max_drop / 25.0, 0.0, 1.0)

    # امتیاز تحمل نوسان (با IV)
    expected_move = 1.5 * iv * np.sqrt(dte / 365.0) * 100
    downside_score = np.clip(max_drop / expected_move,
                             0.0, 1.0) if expected_move > 0 else 1.0

    # امتیاز دلتا
    net_delta = abs(1.0 - delta)
    delta_score = np.exp(-2.0 * net_delta)

    # جریمه ITM
    moneyness = (stock_price - strike) / stock_price if stock_price > 0 else 0
    itm_penalty = (1.0 - np.exp(-6.0 * moneyness)) if moneyness > 0 else 0.0

    final_score = (
        0.30 * return_score +
        0.25 * protection_score +
        0.25 * downside_score +
        0.10 * delta_score -
        0.10 * itm_penalty)

    return round(np.clip(final_score * 100, 0, 100), 2)


# ==========================================================================================
# ۲. تابع اصلی - تمام مراحل از دانلود تا امتیازدهی
# ==========================================================================================

def analyze_covered_call(
        volatility_file: str = "daily_market_volatility.xlsx",
        output_file: str = "covered_call_results.xlsx",
        apply_final_filter: bool = True) -> pd.DataFrame:
    """
    اجرای کامل تحلیل استراتژی Covered Call

    مراحل:
        1. دانلود داده از بورس
        2. پاکسازی داده
        3. محاسبه IV و Delta (با استفاده از ماژول calculator)
        4. محاسبه کارمزدها و پارامترهای Covered Call
        5. امتیازدهی
        6. فیلتر نهایی
        7. ذخیره نتایج

    Args:
        volatility_file: مسیر فایل نوسان تاریخی (HV) - اختیاری
        output_file: نام فایل خروجی اکسل
        apply_final_filter: اعمال فیلتر نهایی max_drop_threshold

    Returns:
        pd.DataFrame: دیتافریم رتبه‌بندی‌شده
    """

    # =============================================
    # مرحله 1: دانلود داده
    # =============================================
    df_raw = MarketDownloader.from_tsetmc_direct()

    # =============================================
    # مرحله 2: پاکسازی داده
    # =============================================
    df_cleaned = DataCleaner.clean(df_raw)

    # =============================================
    # مرحله 3: افزودن ستون‌های مشتق
    # =============================================
    df_final = DataCleaner.add_derived_columns(df_cleaned)

    # =============================================
    # مرحله 4: محاسبه IV و یونانی‌ها (با نرخ بهره ثابت)
    # =============================================
    try:
        df_with_greeks = add_bsm_and_greeks(df_final, r=RISK_FREE_RATE)
    except Exception as e:
        return pd.DataFrame()

    # =============================================
    # مرحله 5: فیلتر قراردادهای CALL
    # =============================================

    is_call_mask = df_with_greeks['Type'].apply(
        lambda x: x.name == 'CALL' if hasattr(
            x, 'name') else str(x).upper() == 'CALL')

    filter_option = df_with_greeks[
        (df_with_greeks['DaysToMaturity'] > 2.0) & is_call_mask].copy()

    # حذف نمادهای خاص
    EXCLUDED_UNDERLYING = ['اهرم']
    EXCLUDED_NAME_PATTERN = ['1405/04', '1405-04']

    exclude_mask = (
        (filter_option['UnderlyingTicker'].isin(EXCLUDED_UNDERLYING)) &
        (filter_option['Name'].str.contains(
            '|'.join(EXCLUDED_NAME_PATTERN), na=False)))
    filter_option = filter_option[~exclude_mask].copy()

    # =============================================
    # مرحله 6: محاسبه Covered Call
    # =============================================

    results_fee = []
    for underlying_symbol, group in filter_option.groupby('UnderlyingTicker'):
        market = get_symbol_market(underlying_symbol)
        kind = get_symbol_kind(underlying_symbol)

        opt_sell_commission = get_commission_rate(market, 'option', False)
        stock_buy_commission = get_commission_rate(market, kind, True)
        exercise_fee_rate = get_exercise_fee_rate(market, kind)
        exercise_tax_rate = EXERCISE_TAX_RATE

        for _, item in group.iterrows():
            ticker = item['Ticker']
            strike_price = item['StrikePrice']
            premium_call = item['BidPrice']
            stock_price = item['UnderlyingPrice']
            contract_size = item['ContractSize']
            days = item['DaysToMaturity']

            # حذف قراردادهای بدون قیمت معتبر
            if premium_call <= 0 or stock_price <= 0:
                continue

            # محاسبات مالی
            cc_result = covered_call_with_fees(
                ticker, premium_call, stock_price, strike_price, contract_size,
                opt_sell_commission, stock_buy_commission,
                exercise_fee_rate, exercise_tax_rate, days)

            results_fee.append({
                'underlying': underlying_symbol,
                'option_symbol': ticker,
                'strike': strike_price,
                'premium': round(premium_call, 0),
                'stock_price': round(stock_price, 0),
                'net_profit': cc_result['net_profit'],
                'monthly_return_%': cc_result['monthly_return'],
                'break_even_price': cc_result['break_even_price'],
                'max_drop_%': cc_result['max_drop_percent'],
                'status': getattr(item['OptionStatus'], 'value', item['OptionStatus']) if 'OptionStatus' in item else 'MID',
                'days_to_maturity': days,
                'volume': int(item.get('Volume')),
                # ستون‌های محاسبه‌شده از بلک-شولز
                'IV': item.get('ImpliedVolatility'),
                'Delta': item.get('Delta'),
                'Gamma': item.get('Gamma'),
                'Theta': item.get('Theta'),
                'BS_Price': item.get('BS_Price')
            })

    result_df_fee = pd.DataFrame(results_fee)

    if result_df_fee.empty:
        return result_df_fee

    # =============================================
    # مرحله 7: بارگذاری HV (اختیاری)
    # =============================================
    if os.path.exists(volatility_file):
        try:
            df_vol = pd.read_excel(volatility_file)
            df_hv = df_vol[['UnderlyingTicker', 'Volatility']].rename(
                columns={'UnderlyingTicker': 'underlying', 'Volatility': 'HV'})
            result_df_fee = pd.merge(
                result_df_fee, df_hv, on='underlying', how='left')
            result_df_fee['HV'] = result_df_fee['HV'].fillna(0.45)
        except Exception as e:
            print(f"{e}")
    else:
        result_df_fee['HV'] = 0.45

    # =============================================
    # مرحله 8: امتیازدهی
    # =============================================
    result_df_fee['score'] = result_df_fee.apply(
        lambda row: score_covered_call_adapted(row, iv_col='IV', delta_col='Delta'), axis=1)

    result_df_fee = result_df_fee.sort_values(
        by='score', ascending=False).reset_index(drop=True)

    # چیدمان ستون‌ها
    ordered_columns = ['score'] + \
        [col for col in result_df_fee.columns if col != 'score']
    result_df_fee = result_df_fee[ordered_columns]

    # =============================================
    # مرحله 9: فیلتر نهایی
    # =============================================
    if apply_final_filter:
        result_df_fee['dte_factor'] = (
            result_df_fee['days_to_maturity'] / 30) ** 0.5
        result_df_fee['dte_factor'] = result_df_fee['dte_factor'].clip(
            lower=0.3, upper=2.5)
        result_df_fee['max_drop_threshold'] = 10.0 * \
            result_df_fee['dte_factor']

        result_df_fee = result_df_fee[
            result_df_fee['max_drop_%'] >= result_df_fee['max_drop_threshold']].copy()

        result_df_fee = result_df_fee.sort_values(
            by='score', ascending=False).reset_index(drop=True)

    # =============================================
    # مرحله 10: ذخیره نتایج
    # =============================================
    try:
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            result_df_fee.to_excel(
                writer, sheet_name='Scored_Results', index=False)

            # برگه مقایسه HV و IV
            if 'HV' in result_df_fee.columns:
                compare_df = result_df_fee[[
                    'option_symbol', 'underlying', 'HV', 'IV', 'Delta', 'score']].head(20)
                compare_df.to_excel(
                    writer, sheet_name='Top_20_HV_vs_IV', index=False)

    except Exception as e:
        print(f"{e}")

    # =============================================
    # نمایش نتایج
    # =============================================
    display_cols = ['option_symbol', 'underlying',
                    'monthly_return_%', 'max_drop_%', 'IV', 'Delta', 'score']
    available_cols = [c for c in display_cols if c in result_df_fee.columns]

    if available_cols:
        print(result_df_fee[available_cols].head(10).to_string(index=False))

    return result_df_fee


# ==========================================================================================
# ۳. اجرای مستقیم ماژول
# ==========================================================================================

if __name__ == "__main__":

    # تنظیمات
    VOLATILITY_FILE = "daily_market_volatility.xlsx"
    OUTPUT_FILE = "covered_call_results.xlsx"

    # اجرا
    df_result = analyze_covered_call(
        volatility_file=VOLATILITY_FILE,
        output_file=OUTPUT_FILE,
        apply_final_filter=True)
