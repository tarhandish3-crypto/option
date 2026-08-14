# 0myStrategy/volatility_calculate.py
# -*- coding: utf-8 -*-

"""
ماژول محاسبه و ذخیره نوسان تاریخی (Historical Volatility) نمادهای پایه
اجرای مستقل - فقط از لیست نمادهای مجاز استفاده می‌کند
"""

import pandas as pd
import numpy as np
import requests
import time
import random
from datetime import datetime
import jdatetime
from pathlib import Path

# =============================================
# دیکشنری نمادهای دارای قرارداد اختیار (فقط همین‌ها)
# =============================================

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
}

# دیکشنری معکوس
CODE_TO_SYMBOL = {v: k for k, v in SYMBOL_MAP.items()}


# =============================================
# تابع دریافت تاریخ شمسی جاری
# =============================================

def get_persian_date() -> str:
    """دریافت تاریخ شمسی جاری به فرمت YYYY-MM-DD"""
    now = datetime.now()
    persian_now = jdatetime.datetime.fromgregorian(datetime=now)
    return persian_now.strftime('%Y-%m-%d')

# =============================================
# تابع دانلود و محاسبه نوسان تاریخی
# =============================================


def download_and_calculate_volatility(stock_id: str, window_size: int) -> float:
    """
    دانلود مستقیم سابقه قیمت و محاسبه نوسان تاریخی سالانه
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    url = f'https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList/{stock_id}/0'

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        daily_list = data.get('closingPriceDaily', [])
        if not daily_list:
            return 0.45

        df_hist = pd.DataFrame(daily_list)
        df_hist['dEven'] = df_hist['dEven'].astype(str)
        df_hist['date'] = pd.to_datetime(df_hist['dEven'], format='%Y%m%d')
        df_hist = df_hist.sort_values('date').reset_index(drop=True)
        df_hist['pClosing'] = pd.to_numeric(
            df_hist['pClosing'], errors='coerce')
        df_hist.dropna(subset=['pClosing'], inplace=True)

        if len(df_hist) < 10:
            return 0.45

        df_window = df_hist.tail(window_size).copy()
        df_window['log_return'] = np.log(
            df_window['pClosing'] / df_window['pClosing'].shift(1))
        daily_std = df_window['log_return'].std()

        if pd.isna(daily_std) or daily_std == 0:
            return 0.45

        # سالانه‌سازی (۲۵۲ روز معاملاتی)
        annual_vol = daily_std * np.sqrt(252)
        return round(float(np.clip(annual_vol, 0.10, 1.00)), 4)

    except Exception:
        return 0.45


# =============================================
# اجرای اصلی - فقط از لیست نمادها استفاده می‌کند
# =============================================

def run_volatility_fetch(window_size: int = 60, output_excel: str = "daily_market_volatility.xlsx"):
    """
    اجرای محاسبه نوسان برای تمام نمادهای موجود در لیست

    Args:
        window_size: تعداد روزهای پنجره محاسباتی (پیش‌فرض ۶۰ روز)
        output_excel: نام فایل خروجی

    Returns:
        pd.DataFrame: دیتافریم نوسان‌ها
    """

    # دریافت تاریخ شمسی
    persian_date = get_persian_date()

    records = []
    total = len(SYMBOL_MAP)

    for idx, (symbol, code) in enumerate(SYMBOL_MAP.items(), 1):
        # محاسبه نوسان
        hv = download_and_calculate_volatility(code, window_size)

        records.append({
            'UnderlyingTicker': symbol,
            'InstrumentCode-UA': code,
            'WindowSize': window_size,
            'CalculationDate': persian_date,
            'Historical_Volatility': hv})

        # تاخیر بین درخواست‌ها (برای جلوگیری از بلاک شدن)
        if idx < total:
            time.sleep(random.uniform(0.3, 0.8))

    return pd.DataFrame(records)


# =============================================
# اجرای مستقیم ماژول
# =============================================

if __name__ == "__main__":

    # ===== تنظیمات =====
    WINDOW_SIZE = 60  # تعداد روزهای پنجره محاسباتی

    # ===== اجرا =====
    BASE_DIR = Path(__file__).resolve().parent
    OUTPUT_FILE = Path.joinpath(BASE_DIR, 'Historical_Volatility.xlsx')

    df_volatility = run_volatility_fetch(
        window_size=WINDOW_SIZE,
        output_excel=OUTPUT_FILE)

    df_volatility = df_volatility.sort_values(
        by='Historical_Volatility', ascending=False).reset_index(drop=True)
    df_volatility.to_excel(OUTPUT_FILE, index=False)
