# 0myStrategy/fetch_trade_history.py
# -*- coding: utf-8 -*-

"""
fetch_trade_history.py — دریافت و ذخیره ریزمعاملات آپشن‌ها از TSETMC
"""

import sys
import time
import random
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests


# --- مسیرها ---
CURRENT_DIR = Path(__file__).resolve().parent
TRADES_DIR = CURRENT_DIR / "trades"

# --- تنظیمات ---
DATE_STR = None              # اگر None باشد، تاریخ امروز
FORCE_DOWNLOAD = False       # اجبار به دریافت مجدد
MAX_WORKERS = 5

# --- API ---
TRADE_API_URL = "https://cdn.tsetmc.com/api/Trade/GetTrade/{ins_code}"
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:157.0) Gecko/20100101 Firefox/15'}

# --- پارامترها ---
TIMEOUT = 10
MAX_RETRIES = 3
RETRY_DELAY = 1.0
REQUEST_DELAY_MIN = 0.05     # حداقل تأخیر قبل از هر درخواست (ثانیه)
REQUEST_DELAY_MAX = 0.15     # حداکثر تأخیر قبل از هر درخواست (ثانیه)


# =====================================================================
# لیست نمادها (هاردکد شده)
# =====================================================================

OPTIONS_REGISTRY = {

    "فزر": {
        "ضفزر709": 6573852869802145,
        "ضفزر710": 54662177716411146,
        "ضفزر711": 3438605083824072,
        "ضفزر712": 7535706950108842,
        "ضفزر713": 67857105823670947,
        "ضفزر714": 54177218004140214,
        "ضفزر715": 64233268303852949,
        "ضفزر716": 2778794684742515,
        "ضفزر717": 55745177119669758,
        "ضفزر718": 53874633519758686,
        "ضفزر719": 60234627467194499,
        "ضفزر720": 67964779804257690,
        "ضفزر721": 29568819361894593,
        "ضفزر722": 55395635854601988,
        "ضفزر723": 60854777093814505,
        "ضفزر724": 21964422039707949,
        "ضفزر725": 18376143079003409,
        "ضفزر726": 2190046300039825,
        "ضفزر727": 17615432358331924,
        "ضفزر728": 23590905784855632,
        "ضفزر729": 2650251901841248,
        "ضفزر730": 66258007212510302,
        "ضفزر731": 17149736328226803,
        "ضفزر732": 51238480908939195,
        "ضفزر733": 28673857704870349,
        "ضفزر734": 10509303333969044,
        },
        }


def get_all_ins_codes():
    """جمع‌آوری همه insCodeها."""
    codes = {}
    for underlying, options in OPTIONS_REGISTRY.items():
        for ticker, code in options.items():
            codes[ticker] = code
    return codes


# =====================================================================
# دریافت یک نماد
# =====================================================================

def fetch_one_trade(ins_code, retries=MAX_RETRIES):
    """دریافت ریزمعاملات یک نماد."""
    url = TRADE_API_URL.format(ins_code=ins_code)

    # --- تأخیر تصادفی کوچک قبل از درخواست (ضد rate-limit) ---
    time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()

            data = response.json().get("trade")
            if not data:
                return None

            df = pd.json_normalize(data)

            # --- تبدیل hEven به time ---
            df['hEven'] = df['hEven'].astype(int).astype(str).str.zfill(6)
            df['time'] = pd.to_datetime(df['hEven'], format='%H%M%S').dt.time

            # --- مرتب‌سازی بر اساس nTran ---
            df = df.sort_values('nTran').reset_index(drop=True)

            # --- ستون‌های موردنیاز ---
            df['price'] = df['pTran'].astype(float)
            df['volume'] = df['qTitTran'].astype(int)
            df['insCode'] = ins_code

            return df[['insCode', 'nTran', 'hEven', 'time', 'price', 'volume', 'dEven']]

        except requests.RequestException as e:
            print(f"  [RETRY {attempt}/{retries}] insCode={ins_code}: {e}")
            if attempt < retries:
                time.sleep(RETRY_DELAY * attempt)
            else:
                return None
        except Exception as e:
            print(f"  [ERROR] insCode={ins_code}: {e}")
            return None

    return None


# =====================================================================
# ذخیره در CSV و Parquet
# =====================================================================

def save_trades(trades_dict, date_str):
    """ذخیره همه ریزمعاملات در CSV و Parquet."""
    folder = TRADES_DIR / date_str
    folder.mkdir(parents=True, exist_ok=True)

    saved = 0
    for ins_code, df in trades_dict.items():
        try:
            # --- CSV (برای مشاهده و ویرایش) ---
            csv_path = folder / f"trades_{ins_code}.csv"
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')

            # --- Parquet (برای بارگذاری سریع) ---
            pq_path = folder / f"trades_{ins_code}.parquet"
            df.to_parquet(pq_path, engine='pyarrow', compression='snappy', index=False)

            saved += 1
        except Exception as e:
            print(f"  [SAVE ERROR] insCode={ins_code}: {e}")

    return saved, folder


# =====================================================================
# تابع اصلی
# =====================================================================

def main():
    date_str = DATE_STR or datetime.now().strftime('%Y%m%d')
    folder = TRADES_DIR / date_str

    print("=" * 70)
    print(f"Fetch Trade History - Date: {date_str}")
    print("=" * 70)

    # --- بررسی trades موجود ---
    all_codes = get_all_ins_codes()

    if not FORCE_DOWNLOAD and folder.exists():
        existing = list(folder.glob("trades_*.parquet"))
        if len(existing) >= len(all_codes):
            print(f"\n[OK] Trade history already exists: {len(existing)} files")
            print(f"     Folder: {folder}")
            print(f"     Set FORCE_DOWNLOAD = True to re-download")
            return

    # --- دریافت ---
    print(f"\n[FETCH] Downloading {len(all_codes)} symbols...")
    print(f"        Workers: {MAX_WORKERS}")
    print(f"        Delay: {REQUEST_DELAY_MIN}-{REQUEST_DELAY_MAX}s")

    results = {}
    failed = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_info = {
            executor.submit(fetch_one_trade, code): (ticker, code)
            for ticker, code in all_codes.items()
        }

        for future in as_completed(future_to_info):
            ticker, code = future_to_info[future]
            try:
                df = future.result()
                if df is not None and not df.empty:
                    results[code] = df
                    print(f"  [OK]   {ticker} ({code}): {len(df)} trades")
                else:
                    failed.append(ticker)
                    print(f"  [WARN] {ticker} ({code}): empty")
            except Exception as e:
                failed.append(ticker)
                print(f"  [FAIL] {ticker} ({code}): {e}")

    # --- ذخیره ---
    if results:
        saved, folder = save_trades(results, date_str)
        print(f"\n[SAVE] Saved {saved} files (CSV + Parquet) to:")
        print(f"       {folder}")


if __name__ == "__main__":
    main()