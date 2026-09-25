# 0myStrategy/volatility_calculate.py
# -*- coding: utf-8 -*-
"""
ماژول محاسبه نوسان، روند، و کمی‌سازی بنیاد نمادهای پایه.

هر بار اجرا:
    1) داده تاریخی شاخص کل را از TSETMC دانلود می‌کند.
    2) داده تاریخی هر نماد را دانلود می‌کند.
    3) محاسبات کامل (نوسان، روند، افت، بازگشت، RSI،
       خریداران، حمایت/مقاومت، بازدهی نسبی، بتا/آلفا) را انجام می‌دهد.
    4) VQ (VolatilityQualityScore) را محاسبه می‌کند.
    5) در Historical_Volatility.xlsx ذخیره می‌کند.

خروجی: Historical_Volatility.xlsx
"""

import pandas as pd
import numpy as np
import requests
import time
import random
from datetime import datetime
import jdatetime
from pathlib import Path
from scipy.signal import argrelextrema


# =============================================
# تنظیمات
# =============================================

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / 'Historical_Volatility.xlsx'

# دیکشنری نمادهای دارای قرارداد اختیار
SYMBOL_MAP = {
    'تاصيكو': '23293437377896568',
    'توان': '41927452991671109',
    'موج': '67141987086032267',
    'اهرم': '17914401175772326',
    'اطلس': '11427939669935844',
    'شپنا': '7745894403636165',
    'فزر': '8175784894140974',
    'وبملت': '778253364357513',
    'وتجارت': '63917421733088077',
    'طعام': '31230051169165044',
    'جوانه كوچك': '67455383896188985',
    'شستا': '2400322364771558',
    'خودرو': '65883838195688438',
    'فملي': '35425587644337450',
    'هم تراز': '51920757918600374',
    'ذوب': '71483646978964608',
    'وبصادر': '28320293733348826',
    'زرگر': '16817885126368964',
    'جواهر': '38544104313215500',
    'كهربا': '25559236668122210',
    'طلا': '46700660505281786',
    'درخشان': '61805666737517582',
    'بساما': '41625340598198551'
}

CODE_TO_SYMBOL = {v: k for k, v in SYMBOL_MAP.items()}


# =============================================
# توابع کمکی
# =============================================

def get_persian_date() -> str:
    """دریافت تاریخ شمسی جاری به فرمت YYYY-MM-DD"""
    now = datetime.now()
    persian_now = jdatetime.datetime.fromgregorian(datetime=now)
    return persian_now.strftime('%Y-%m-%d')


def get_headers() -> dict:
    """هدرهای HTTP برای درخواست به TSETMC."""
    return {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36'
        )
    }


# =============================================
# بخش ۱: دانلود داده شاخص کل
# =============================================

def download_index_history() -> pd.DataFrame:
    """
    دانلود تاریخچه کامل شاخص کل از TSETMC.


    خروجی: DataFrame با ستون‌های date, pClosing
    """
    url = f'https://cdn.tsetmc.com/api/Index/GetIndexB2History/32097828799138957'

    try:
        response = requests.get(url, headers=get_headers(), timeout=20)
        response.raise_for_status()
        data = response.json()

        index_list = data.get('indexB2', [])
        if not index_list:
            print("  WARNING: No index data received.")
            return pd.DataFrame()

        df = pd.DataFrame(index_list)
        df['dEven'] = df['dEven'].astype(str)
        df['date'] = pd.to_datetime(df['dEven'], format='%Y%m%d')
        df['pClosing'] = pd.to_numeric(df['xNivInuClMresIbs'], errors='coerce')

        df = df.sort_values('date').reset_index(drop=True)

        return df[['date', 'pClosing']]

    except Exception as e:
        print(f"  ERROR downloading index: {e}")
        return pd.DataFrame()


# =============================================
# بخش ۲: دانلود داده سهم
# =============================================

def download_price_history(stock_id: str) -> pd.DataFrame:
    """
    دانلود سابقه قیمت روزانه سهم.

    URL: GetClosingPriceDailyList/{stock_id}/0

    خروجی: DataFrame با ستون‌های date, pClosing, pMeOfShares
    """
    url = (
        f'https://cdn.tsetmc.com/api/ClosingPrice/'
        f'GetClosingPriceDailyList/{stock_id}/0')

    try:
        response = requests.get(url, headers=get_headers(), timeout=15)
        response.raise_for_status()
        data = response.json()

        daily_list = data.get('closingPriceDaily', [])
        if not daily_list:
            return pd.DataFrame()

        df = pd.DataFrame(daily_list)
        df['dEven'] = df['dEven'].astype(str)
        df['date'] = pd.to_datetime(df['dEven'], format='%Y%m%d')
        df = df.sort_values('date').reset_index(drop=True)
        df['pClosing'] = pd.to_numeric(df['pClosing'], errors='coerce')
        df['pMeOfShares'] = pd.to_numeric(
            df.get('pMeOfShares', 0), errors='coerce')
        df.dropna(subset=['pClosing'], inplace=True)
        df = df[df['pClosing'] > 0].reset_index(drop=True)

        return df[['date', 'pClosing', 'pMeOfShares']]

    except Exception:
        return pd.DataFrame()


# =============================================
# بخش ۳: محاسبات نوسان
# =============================================

def calculate_hv(df_hist: pd.DataFrame, window: int = 60) -> float:
    """محاسبه نوسان تاریخی سالانه با پنجره مشخص."""
    if len(df_hist) < window + 1:
        return np.nan
    df = df_hist.tail(window + 1).copy()
    df['log_return'] = np.log(df['pClosing'] / df['pClosing'].shift(1))
    daily_std = df['log_return'].std()
    if pd.isna(daily_std) or daily_std == 0:
        return np.nan
    return float(np.clip(daily_std * np.sqrt(252), 0.05, 2.00))


def calculate_volatility_ratio(
    df_hist: pd.DataFrame, short: int = 20, long: int = 60) -> float:
    """نسبت نوسان کوتاه‌مدت به بلندمدت."""
    hv_s = calculate_hv(df_hist, short)
    hv_l = calculate_hv(df_hist, long)
    if pd.isna(hv_s) or pd.isna(hv_l) or hv_l == 0:
        return np.nan
    return round(hv_s / hv_l, 4)


# =============================================
# بخش ۴: محاسبات روند
# =============================================

def calculate_trend_slope(df_hist: pd.DataFrame, window: int = 30) -> float:
    """شیب رگرسیون خطی قیمت (روی لگاریتم قیمت)."""
    if len(df_hist) < window:
        return np.nan
    df = df_hist.tail(window).copy()
    x = np.arange(len(df))
    y = np.log(df['pClosing'].values)
    if np.any(np.isnan(y)) or np.any(np.isinf(y)):
        return np.nan
    slope = np.polyfit(x, y, 1)[0]
    return round(float(slope), 6)


def calculate_long_trend(df_hist: pd.DataFrame) -> float:
    """روند بلندمدت (SMA50 - SMA200) / SMA200."""
    if len(df_hist) < 200:
        return np.nan
    sma_50 = df_hist['pClosing'].tail(50).mean()
    sma_200 = df_hist['pClosing'].tail(200).mean()
    if sma_200 == 0:
        return np.nan
    return round((sma_50 - sma_200) / sma_200, 4)


# =============================================
# بخش ۵: محاسبات افت
# =============================================

def calculate_max_drawdown(df_hist: pd.DataFrame, window: int = 60) -> float:
    """حداکثر افت در پنجره مشخص."""
    if len(df_hist) < window:
        return np.nan
    prices = df_hist.tail(window)['pClosing'].values
    running_max = np.maximum.accumulate(prices)
    drawdown = (prices - running_max) / running_max
    return round(float(drawdown.min()), 4)


def calculate_technical_decline(df_hist: pd.DataFrame) -> float:
    """
    تفکیک افت تکنیکال از بنیادی.

    فرمول:
        TechnicalDecline = (|MaxDD_20| - |MaxDD_120|) / |MaxDD_120|

    تفسیر:
        > 0.5  => افت تکنیکال (فرصت)
        < 0.0  => افت بنیادی (خطر)
    """
    maxdd_20 = calculate_max_drawdown(df_hist, 20)
    maxdd_120 = calculate_max_drawdown(df_hist, 120)
    if pd.isna(maxdd_20) or pd.isna(maxdd_120) or maxdd_120 == 0:
        return np.nan
    return round((abs(maxdd_20) - abs(maxdd_120)) / abs(maxdd_120), 4)


def calculate_recovery_strength(
    df_hist: pd.DataFrame, window: int = 60
) -> float:
    """بازگشت از کف در پنجره مشخص."""
    if len(df_hist) < window:
        return np.nan
    prices = df_hist.tail(window)['pClosing'].values
    price_now = prices[-1]
    price_min = prices.min()
    price_max = prices.max()
    if price_max == price_min:
        return np.nan
    return round((price_now - price_min) / (price_max - price_min), 4)


# =============================================
# بخش ۶: RSI
# =============================================

def calculate_rsi(df_hist: pd.DataFrame, window: int = 14) -> float:
    """شاخص قدرت نسبی (RSI)."""
    if len(df_hist) < window + 1:
        return np.nan
    df = df_hist.tail(window + 1).copy()
    delta = df['pClosing'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=window).mean().iloc[-1]
    avg_loss = loss.rolling(window=window).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(float(100 - (100 / (1 + rs))), 2)


# =============================================
# بخش ۷: قدرت خریداران
# =============================================

def calculate_buyer_strength(
    df_hist: pd.DataFrame, window: int = 30
) -> float:
    """
    قدرت خریداران (نسبت حجم روزهای صعودی به کل حجم).

    فرمول:
        BuyerStrength = sum(Volume_up) / sum(Volume_total)
    """
    if len(df_hist) < window:
        return np.nan
    df = df_hist.tail(window).copy()
    df['price_change'] = df['pClosing'].diff()
    df = df.dropna(subset=['price_change'])
    if df.empty or 'pMeOfShares' not in df.columns:
        return np.nan
    up_days = df[df['price_change'] > 0]
    total_volume = df['pMeOfShares'].sum()
    if total_volume == 0:
        return np.nan
    return round(float(up_days['pMeOfShares'].sum() / total_volume), 4)


# =============================================
# بخش ۸: حمایت و مقاومت
# =============================================

def find_support_resistance(
    df_hist: pd.DataFrame, window: int = 10, lookback: int = 120
) -> dict:
    """
    شناسایی نقاط حمایت و مقاومت.

    خروجی: دیکشنری شامل ۳ حمایت و ۳ مقاومت
    """
    empty = {
        'support_1': np.nan, 'support_2': np.nan, 'support_3': np.nan,
        'resistance_1': np.nan, 'resistance_2': np.nan, 'resistance_3': np.nan,
    }
    if len(df_hist) < lookback:
        return empty

    prices = df_hist.tail(lookback)['pClosing'].values
    peaks = argrelextrema(prices, np.greater, order=window)[0]
    troughs = argrelextrema(prices, np.less, order=window)[0]
    price_now = prices[-1]

    resistance_prices = sorted(
        [prices[i] for i in peaks if prices[i] > price_now]
    )
    support_prices = sorted(
        [prices[i] for i in troughs if prices[i] < price_now], reverse=True
    )

    return {
        'support_1': support_prices[0] if len(support_prices) > 0 else np.nan,
        'support_2': support_prices[1] if len(support_prices) > 1 else np.nan,
        'support_3': support_prices[2] if len(support_prices) > 2 else np.nan,
        'resistance_1': (
            resistance_prices[0] if len(resistance_prices) > 0 else np.nan
        ),
        'resistance_2': (
            resistance_prices[1] if len(resistance_prices) > 1 else np.nan
        ),
        'resistance_3': (
            resistance_prices[2] if len(resistance_prices) > 2 else np.nan
        ),
    }


def calculate_support_proximity(df_hist: pd.DataFrame) -> float:
    """نزدیکی قیمت فعلی به نزدیک‌ترین حمایت."""
    if df_hist.empty:
        return np.nan
    price_now = df_hist['pClosing'].iloc[-1]
    levels = find_support_resistance(df_hist)
    support = levels.get('support_1', np.nan)
    if pd.isna(support) or price_now == 0:
        return np.nan
    return round((price_now - support) / price_now, 4)


def calculate_resistance_proximity(df_hist: pd.DataFrame) -> float:
    """نزدیکی قیمت فعلی به نزدیک‌ترین مقاومت."""
    if df_hist.empty:
        return np.nan
    price_now = df_hist['pClosing'].iloc[-1]
    levels = find_support_resistance(df_hist)
    resistance = levels.get('resistance_1', np.nan)
    if pd.isna(resistance) or price_now == 0:
        return np.nan
    return round((resistance - price_now) / price_now, 4)


# =============================================
# بخش ۹: بازدهی نسبی و بتا/آلفا
# =============================================

def calculate_relative_return(
    stock_df: pd.DataFrame,
    index_df: pd.DataFrame,
    window_days: int = 252,
) -> float:
    """
    بازدهی نسبی سهم نسبت به شاخص.

    فرمول:
        RelativeReturn = R_stock - R_index
    """
    if stock_df.empty or index_df.empty:
        return np.nan
    if len(stock_df) < window_days or len(index_df) < window_days:
        return np.nan

    stock_ret = (
        stock_df['pClosing'].iloc[-1] /
        stock_df['pClosing'].iloc[-window_days] - 1
    )
    index_ret = (
        index_df['pClosing'].iloc[-1] /
        index_df['pClosing'].iloc[-window_days] - 1
    )
    return round(stock_ret - index_ret, 4)


def calculate_beta_alpha(
    stock_df: pd.DataFrame,
    index_df: pd.DataFrame,
    window_days: int = 252,
) -> tuple:
    """
    محاسبه بتا و آلفا با CAPM.

    فرمول:
        R_stock = alpha + beta × R_index + epsilon

    خروجی: (beta, alpha_annualized)
    """
    if stock_df.empty or index_df.empty:
        return np.nan, np.nan
    if len(stock_df) < 30 or len(index_df) < 30:
        return np.nan, np.nan

    # بازدهی روزانه
    stock_ret = np.log(
        stock_df['pClosing'] / stock_df['pClosing'].shift(1)
    ).dropna()
    index_ret = np.log(
        index_df['pClosing'] / index_df['pClosing'].shift(1)
    ).dropna()

    # هم‌ترازی بر اساس تاریخ
    stock_df_ret = pd.DataFrame({
        'date': stock_df['date'].iloc[1:].values[:len(stock_ret)],
        'stock_ret': stock_ret.values,
    })
    index_df_ret = pd.DataFrame({
        'date': index_df['date'].iloc[1:].values[:len(index_ret)],
        'index_ret': index_ret.values,
    })

    merged = pd.merge(stock_df_ret, index_df_ret, on='date', how='inner')
    merged = merged.tail(window_days)

    if len(merged) < 30:
        return np.nan, np.nan

    beta, alpha = np.polyfit(merged['index_ret'], merged['stock_ret'], 1)
    alpha_annual = alpha * 252

    return round(float(beta), 4), round(float(alpha_annual), 4)


# =============================================
# بخش ۱۰: VQ نهایی
# =============================================

def evaluate_volatility_quality(row: dict) -> float:
    """
    ارزیابی کیفیت نوسان (نسخه ۲).

    وزن‌ها:
        - RelativeReturn_1Y: 20%
        - LongTrend: 15%
        - Alpha: 10%
        - RecoveryStrength: 15%
        - TechnicalDecline: 10%
        - BuyerStrength: 10%
        - SupportProximity: 10%
        - HV_60: 5%
        - RSI_14: 5%
    """
    score = 5.0

    # ۱. بازدهی نسبی ۱ ساله (۲۰٪)
    rr1y = row.get('RelativeReturn_1Y', np.nan)
    if pd.notna(rr1y):
        if rr1y > 0.20:
            score += 2.5
        elif rr1y > 0.10:
            score += 1.5
        elif rr1y > 0.0:
            score += 0.5
        elif rr1y > -0.10:
            score -= 0.5
        else:
            score -= 2.0

    # ۲. روند بلندمدت (۱۵٪)
    lt = row.get('LongTrend', np.nan)
    if pd.notna(lt):
        if lt > 0.10:
            score += 1.5
        elif lt > 0.05:
            score += 1.0
        elif lt > 0.0:
            score += 0.5
        elif lt > -0.05:
            score -= 0.5
        else:
            score -= 1.5

    # ۳. آلفا (۱۰٪)
    alpha = row.get('Alpha', np.nan)
    if pd.notna(alpha):
        if alpha > 0.15:
            score += 1.5
        elif alpha > 0.05:
            score += 0.5
        elif alpha < -0.05:
            score -= 1.0

    # ۴. بازگشت از کف (۱۵٪)
    rs = row.get('RecoveryStrength', np.nan)
    if pd.notna(rs):
        if rs > 0.7:
            score += 1.5
        elif rs > 0.5:
            score += 0.5
        elif rs < 0.3:
            score -= 1.0

    # ۵. افت تکنیکال (۱۰٪)
    td = row.get('TechnicalDecline', np.nan)
    if pd.notna(td):
        if td > 0.5:
            score += 1.0
        elif td < 0.0:
            score -= 0.5

    # ۶. قدرت خریداران (۱۰٪)
    bs = row.get('BuyerStrength', np.nan)
    if pd.notna(bs):
        if bs > 0.6:
            score += 1.0
        elif bs < 0.4:
            score -= 0.5

    # ۷. نزدیکی به حمایت (۱۰٪)
    sp = row.get('SupportProximity', np.nan)
    if pd.notna(sp):
        if sp < 0.03:
            score += 1.0
        elif sp > 0.15:
            score -= 0.5

    # ۸. نوسان معقول (۵٪)
    hv = row.get('HV_60', np.nan)
    if pd.notna(hv):
        if 0.25 <= hv <= 0.50:
            score += 0.5
        elif hv > 0.70:
            score -= 0.5

    # ۹. RSI (۵٪)
    rsi = row.get('RSI_14', np.nan)
    if pd.notna(rsi):
        if 40 <= rsi <= 60:
            score += 0.5
        elif rsi > 80 or rsi < 20:
            score -= 0.5

    return round(max(0.0, min(10.0, score)), 2)


# =============================================
# بخش ۱۱: اجرای اصلی
# =============================================

def run_volatility_fetch(output_excel: str = None) -> pd.DataFrame:
    """
    اجرای کامل محاسبه پروفایل نوسان.

    هر بار اجرا:
        1) دانلود تاریخچه کامل شاخص کل
        2) دانلود و محاسبه پروفایل هر نماد
        3) ذخیره در فایل اکسل
    """

    persian_date = get_persian_date()

    print("=" * 65)
    print("Volatility Calculation with Index Integration")
    print("=" * 65)

    # ===== گام ۱: دانلود تاریخچه شاخص کل =====
    print("\n[1/2] Downloading index history...")
    index_history = download_index_history()

    # ===== گام ۲: محاسبه برای هر نماد =====
    print("\n[2/2] Calculating volatility profiles...")
    records = []
    total = len(SYMBOL_MAP)

    for idx, (symbol, code) in enumerate(SYMBOL_MAP.items(), 1):
        print(f"[{idx}/{total}] Processing: {symbol}")

        df_hist = download_price_history(code)

        if df_hist.empty or len(df_hist) < 20:
            records.append({
                'UnderlyingTicker': symbol,
                'InstrumentCode-UA': code,
                'CalculationDate': persian_date,
                'LastPrice': np.nan,
            })
            continue

        last_price = float(df_hist['pClosing'].iloc[-1])

        # بازدهی نسبی و بتا/آلفا
        if not index_history.empty and len(index_history) >= 252:
            beta, alpha = calculate_beta_alpha(df_hist, index_history, 252)
            rr_6m = calculate_relative_return(df_hist, index_history, 126)
            rr_1y = calculate_relative_return(df_hist, index_history, 252)
        else:
            beta, alpha = np.nan, np.nan
            rr_6m, rr_1y = np.nan, np.nan

        # پروفایل کامل
        profile = {
            'UnderlyingTicker': symbol,
            'InstrumentCode-UA': code,
            'CalculationDate': persian_date,
            'LastPrice': last_price,
            # نوسان
            'HV_20': calculate_hv(df_hist, 20),
            'HV_60': calculate_hv(df_hist, 60),
            'HV_120': calculate_hv(df_hist, 120),
            'VolatilityRatio': calculate_volatility_ratio(df_hist),
            # روند
            'TrendSlope': calculate_trend_slope(df_hist, 30),
            'LongTrend': calculate_long_trend(df_hist),
            # افت
            'MaxDrawdown_20': calculate_max_drawdown(df_hist, 20),
            'MaxDrawdown_60': calculate_max_drawdown(df_hist, 60),
            'MaxDrawdown_120': calculate_max_drawdown(df_hist, 120),
            # بازگشت
            'RecoveryStrength': calculate_recovery_strength(df_hist),
            'TechnicalDecline': calculate_technical_decline(df_hist),
            # RSI
            'RSI_14': calculate_rsi(df_hist, 14),
            # خریداران
            'BuyerStrength': calculate_buyer_strength(df_hist, 30),
            # حمایت/مقاومت
            'SupportProximity': calculate_support_proximity(df_hist),
            'ResistanceProximity': calculate_resistance_proximity(df_hist),
            # بازدهی نسبی و آلفا
            'RelativeReturn_6M': rr_6m,
            'RelativeReturn_1Y': rr_1y,
            'Beta': beta,
            'Alpha': alpha,
        }

        # سطوح حمایت/مقاومت
        levels = find_support_resistance(df_hist)
        profile.update(levels)

        # VQ
        profile['VolatilityQualityScore'] = evaluate_volatility_quality(
            profile)

        records.append(profile)

        # تاخیر بین درخواست‌ها
        if idx < total:
            time.sleep(random.uniform(0.3, 0.8))

    # ===== گام ۳: ذخیره در اکسل =====
    df_result = pd.DataFrame(records)

    if not df_result.empty:
        df_result = df_result.sort_values(
            by='VolatilityQualityScore', ascending=False
        ).reset_index(drop=True)

        df_result.to_excel(output_excel, index=False)
        print(f"\nResults saved to: {output_excel}")

        # چاپ خلاصه
        print("\n=== Top 15 by VQ ===")
        display_cols = [
            'UnderlyingTicker', 'RelativeReturn_1Y', 'Alpha',
            'LongTrend', 'RecoveryStrength', 'TechnicalDecline',
            'VolatilityQualityScore'
        ]
        display_cols = [c for c in display_cols if c in df_result.columns]
        print(df_result[display_cols].head(15).to_string(index=False))

    return df_result


# =============================================
# اجرای مستقیم ماژول
# =============================================

if __name__ == "__main__":
    df_volatility = run_volatility_fetch(output_excel=str(OUTPUT_FILE))
