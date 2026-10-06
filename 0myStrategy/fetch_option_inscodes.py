# 0myStrategy/fetch_option_inscodes.py
# -*- coding: utf-8 -*-

"""
fetch_option_inscodes.py — استخراج insCode آپشن‌ها از TSETMC
سازگار با Jupyter Notebook و Python Script
"""

import re
import os
import json
import time
import random
from pathlib import Path
from urllib.parse import quote
from datetime import datetime
import pandas as pd

import requests


# =====================================================================
# مسیرها (سازگار با Jupyter و Script)
# =====================================================================

def _get_current_dir():
    """تشخیص مسیر جاری (سازگار با Jupyter و Script)."""
    try:
        # --- حالت Script ---
        return Path(__file__).resolve().parent
    except NameError:
        # --- حالت Jupyter ---
        return Path(os.getcwd())


CURRENT_DIR = _get_current_dir()
OUTPUT_JSON = CURRENT_DIR / "option_inscodes.json"
OUTPUT_CSV = CURRENT_DIR / "option_inscodes.csv"


# =====================================================================
# پیکربندی
# =====================================================================

# --- سال هدف (شمسی) ---
TARGET_YEAR = 1405

# --- نمادهای پایه و پیشوند آپشن‌ها ---
UNDERLYINGS = {
    "فزر": "ضفزر",
    # "فملي": "ضملي",
}

# --- API ---
SEARCH_API_URL = "https://cdn.tsetmc.com/api/Instrument/GetInstrumentSearch/{query}"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:157.0) Gecko/20100101 Firefox/157.0',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://tsetmc.ir/',
}

# --- پارامترها ---
TIMEOUT = 10
MAX_RETRIES = 3
RETRY_DELAY = 1.0
REQUEST_DELAY_MIN = 0.05
REQUEST_DELAY_MAX = 0.15


# =====================================================================
# استخراج از lVal30
# =====================================================================

def parse_expiry(lval30):
    """
    استخراج (year, month, day) از lVal30.
    پشتیبانی از سه فرمت:
        1. YYYYMMDD       →  14050722
        2. YYYY/MM/DD     →  1405/07/22
        3. YY/MM/DD       →  05/10/30  (تبدیل به 1405/10/30)
    """
    if not lval30:
        return None

    # --- فرمت ۱: YYYYMMDD ---
    match = re.search(r'-(\d{8})$', lval30)
    if match:
        d = match.group(1)
        try:
            return (int(d[0:4]), int(d[4:6]), int(d[6:8]))
        except (ValueError, IndexError):
            pass

    # --- فرمت ۲: YYYY/MM/DD ---
    match = re.search(r'-(\d{4})/(\d{1,2})/(\d{1,2})$', lval30)
    if match:
        try:
            return (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass

    # --- فرمت ۳: YY/MM/DD ---
    match = re.search(r'-(\d{2})/(\d{1,2})/(\d{1,2})$', lval30)
    if match:
        try:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            if year < 100:
                year = 1400 + year if year < 50 else 1300 + year
            return (year, month, day)
        except ValueError:
            pass

    return None


def parse_strike(lval30):
    """استخراج قیمت اعمال از lVal30."""
    if not lval30:
        return None
    match = re.search(r'-(\d+)-', lval30)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


# =====================================================================
# جستجوی یک query
# =====================================================================

def search_one_query(query, target_year):
    """یک query واحد به API جستجو."""
    url = SEARCH_API_URL.format(query=quote(query))

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json().get("instrumentSearch", [])
            if not data:
                return []

            results = []
            for item in data:
                # --- فیلتر ۱: فقط آپشن‌ها (بازار مشتقه) ---
                if item.get("flow") != 3:
                    continue

                lval30 = item.get("lVal30", "")
                expiry = parse_expiry(lval30)
                if expiry is None:
                    continue

                # --- فیلتر ۲: فقط سال هدف ---
                year, month, day = expiry
                if year != target_year:
                    continue

                ticker = item.get("lVal18AFC", "").strip()
                ins_code = (
                    item.get("insCode")
                    or item.get("insCode2")
                    or item.get("insCode3")
                    or item.get("insCode4"))
                if not ticker or not ins_code:
                    continue

                results.append({
                    'ticker': ticker,
                    'full_name': lval30,
                    'insCode': int(ins_code),
                    'strike': parse_strike(lval30),
                    'expiry_date': f"{year}/{month:02d}/{day:02d}",
                    'expiry_year': year,
                    'expiry_month': month,
                    'expiry_day': day,
                })

            return results

        except requests.RequestException:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY * attempt)
            else:
                return []
        except Exception:
            return []

    return []


# =====================================================================
# دریافت کامل آپشن‌های یک پیشوند (چند query)
# =====================================================================

def fetch_options_for_prefix(prefix, target_year):
    """دریافت همه آپشن‌های یک پیشوند با چند query (پوشش کامل)."""
    # --- ساخت لیست queryها ---
    queries = set()
    queries.add(prefix)                          # ضفزر
    for d in range(10):
        queries.add(f"{prefix}{d}")              # ضفزر0 ... ضفزر9
    queries = sorted(queries)

    all_options = {}   # {insCode: option}

    for query in queries:
        options = search_one_query(query, target_year)
        for opt in options:
            all_options[opt['insCode']] = opt
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

    # --- مرتب‌سازی ---
    result = list(all_options.values())
    result.sort(key=lambda x: (
        x['expiry_year'], x['expiry_month'], x['strike'] or 0
    ))

    return result


# =====================================================================
# ساخت registry
# =====================================================================

def build_registry(target_year):
    """ساخت registry کامل برای همه نمادهای پایه."""
    registry = {}

    for underlying, prefix in UNDERLYINGS.items():
        print(f"\n  -> {underlying} (prefix: {prefix})")
        options = fetch_options_for_prefix(prefix, target_year)

        if not options:
            print(f"    [WARN] No options found for {prefix}")
            continue

        # --- گروه‌بندی بر اساس ماه ---
        by_month = {}
        for opt in options:
            by_month.setdefault(opt['expiry_month'], []).append(opt)

        registry[underlying] = {
            'options': options,
            'by_month': dict(sorted(by_month.items())),
        }

        print(f"    [OK] {prefix}: {len(options)} unique options for year {target_year}")

    return registry


# =====================================================================
# ذخیره در JSON
# =====================================================================

def save_registry(registry, target_year):
    """ذخیره registry در JSON و CSV."""
    
    # --- ساخت ساختار ساده {underlying: {ticker: insCode}} ---
    simple_registry = {}
    for underlying, data in registry.items():
        simple_registry[underlying] = {
            opt['ticker']: opt['insCode']
            for opt in data['options']
        }
    
    # --- ذخیره JSON ---
    output = {
        'target_year': target_year,
        'created_at': datetime.now().isoformat(),
        'registry': simple_registry,
    }
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n[SAVE] JSON: {OUTPUT_JSON}")
    
    # --- ذخیره CSV (کامل با همه ستونها) ---
    rows = []
    for underlying, data in registry.items():
        for opt in data['options']:
            rows.append({
                'نماد پایه': underlying,
                'نام کامل': opt['full_name'],
                'نماد آپشن': opt['ticker'],
                'insCode': opt['insCode'],
                'قیمت اعمال': opt['strike'],
                'تاریخ اعمال': opt['expiry_date'],
                'سال': opt['expiry_year'],
                'ماه': opt['expiry_month'],
                'روز': opt['expiry_day'],
            })
    
    if rows:
        df = pd.DataFrame(rows)
        df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
        print(f"[SAVE] CSV:  {OUTPUT_CSV}")
    
    return OUTPUT_JSON, OUTPUT_CSV

# =====================================================================
# تابع اصلی (قابل فراخوانی از Jupyter)
# =====================================================================

def main():
    print("=" * 70)
    print(f"Fetch Option insCodes — Target Year: {TARGET_YEAR}")
    print("=" * 70)

    print("\n[SEARCH] Fetching option insCodes...")
    registry = build_registry(TARGET_YEAR)

    if not registry:
        print("\n[FAIL] No options found. Exiting.")
        return None

    total = sum(len(d['options']) for d in registry.values())
    print(f"\n[OK] Total: {total} options across {len(registry)} underlyings")

    save_registry(registry, TARGET_YEAR)
    return registry


# =====================================================================
# اجرای خودکار (فقط در Script، نه در Jupyter)
# =====================================================================

if __name__ == "__main__":
    main()