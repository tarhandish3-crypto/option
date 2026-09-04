# -*- coding: utf-8 -*-
"""
تشخیص نمادهای در صف خرید و فروش
"""

import logging
from typing import Optional, List, Dict, Any

import requests
import pandas as pd

logger = logging.getLogger("OptionScanner.Data.MarketQueue")

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36'
}

PRICE_URL = "http://old.tsetmc.com/tsev2/data/MarketWatchPlus.aspx"


def get_supply_demand_data(datas: str) -> Optional[pd.DataFrame]:
    """
    پردازش داده‌های صف خرید و فروش
    
    Parameters:
        datas (str): رشته حاوی داده‌های صف خرید و فروش
        
    Returns:
        pd.DataFrame: دیتافریم شامل اطلاعات صف خرید و فروش
    """
    try:
        datas = datas.split('@')[3].split(';')
    except Exception as e:
        logger.warning(f"Error parsing supply/demand data: {e}")
        return None
    
    if len(datas) < 100:
        return None
    
    rows = []
    for data in datas:
        sub_data = data.split(',')
        if len(sub_data) == 8:
            rows.append(sub_data)
    
    if len(rows) < 100:
        return None
    
    df = pd.DataFrame(rows)
    df.columns = ['id', 'row', 2, 3, 4, 5, 6, 7]
    df.set_index(df['id'], inplace=True)
    df.drop(columns=['id'], inplace=True)
    
    groups = df.groupby('row')
    
    try:
        df1 = groups.get_group('1')
        df1.columns = ['row', 'zo1', 'zd1', 'pd1', 'po1', 'qd1', 'qo1']
        df1 = df1.drop(columns=['row'])
        df1 = df1.apply(pd.to_numeric, errors='coerce')
        return df1
    except KeyError:
        return None


def get_price_data() -> Optional[pd.DataFrame]:
    """
    دریافت داده‌های قیمت از tsetmc
    
    Returns:
        pd.DataFrame: دیتافریم شامل اطلاعات قیمت و صف خرید/فروش
    """
    import time
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            datas = requests.get(PRICE_URL, headers=HEADERS, timeout=10).text
            break
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                logger.warning(f"Timeout on attempt {attempt + 1}, retrying...")
                time.sleep(1)
                continue
            logger.error(f"Error fetching price data after {max_retries} attempts: timeout")
            return None
        except Exception as e:
            logger.error(f"Error fetching price data: {e}")
            return None
    
    rows_df = get_supply_demand_data(datas)
    if rows_df is None:
        return None
    
    datas = datas.split(';')
    if len(datas) < 100:
        return None
    
    all_data = {}
    for data in datas:
        sub_data = data.split(',')
        length = len(sub_data)
        if length >= 20:
            if length not in all_data:
                all_data[length] = []
            all_data[length].append(sub_data)
    
    if not all_data:
        return None
    
    best_length = max(all_data.keys(), key=lambda x: len(all_data[x]))
    data_list = all_data[best_length]
    
    if len(data_list) < 100:
        return None
    
    df = pd.DataFrame(data_list)
    
    standard_columns = [
        'id', 'code', 'symbol', 'name', 'HHMMSS', 'pf', 'pc', 'pl',
        'tno', 'tvol', 'tval', 'pmin', 'pmax', 'py', 'eps', 'bvol',
        'extra1', 'extra2', 'industry_code', 'tmax', 'tmin', 'z', 'cs', 'nav'
    ]
    
    extra_columns = ['extra7', 'extra8', 'extra9', 'extra10']
    all_columns = standard_columns + extra_columns
    
    df.columns = all_columns[:len(df.columns)]
    
    # حذف سطرهای نامعتبر
    df = df[~df['symbol'].str.contains(r'\d', na=False)]
    
    df.set_index('id', inplace=True)
    
    # ترکیب با داده‌های صف
    df = pd.concat([df, rows_df], axis=1)
    
    # تبدیل به عددی
    numeric_cols = ['pf', 'pc', 'pl', 'tno', 'tvol', 'tval', 'pmin', 'pmax', 'py', 'eps', 'bvol', 'tmax', 'tmin', 'z', 'nav']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    return df


def get_buy_queue_symbols() -> List[Dict[str, Any]]:
    """
    دریافت لیست نمادهای در صف خرید
    
    Returns:
        List[Dict]: لیست دیکشنری‌های شامل اطلاعات نمادهای صف خرید
    """
    price_df = get_price_data()
    if price_df is None or price_df.empty:
        logger.warning("No price data available")
        return []
    
    # نمادهای در صف خرید:
    # قیمت آخر = سقف مجاز
    # قیمت صف خرید = 0 یا بیشتر از سقف مجاز
    buy_queue = price_df[
        (price_df['pl'] == price_df['tmax']) & 
        ((price_df['po1'] == 0) | (price_df['po1'] > price_df['tmax']))
    ]
    
    result = []
    for idx, row in buy_queue.iterrows():
        result.append({
            'id': str(idx),
            'symbol': row.get('symbol', ''),
            'name': row.get('name', ''),
            'price': row.get('pl', 0),
            'queue_volume': row.get('qd1', 0),
            'queue_count': row.get('qd1', 0),
        })
    
    logger.info(f"Found {len(result)} symbols in buy queue")
    return result


def get_sell_queue_symbols() -> List[Dict[str, Any]]:
    """
    دریافت لیست نمادهای در صف فروش
    
    Returns:
        List[Dict]: لیست دیکشنری‌های شامل اطلاعات نمادهای صف فروش
    """
    price_df = get_price_data()
    if price_df is None or price_df.empty:
        logger.warning("No price data available")
        return []
    
    # نمادهای در صف فروش:
    # قیمت آخر = کف مجاز
    # قیمت صف فروش = 0 یا کمتر از کف مجاز
    sell_queue = price_df[
        (price_df['pl'] == price_df['tmin']) & 
        ((price_df['pd1'] == 0) | (price_df['pd1'] < price_df['tmin']))
    ]
    
    result = []
    for idx, row in sell_queue.iterrows():
        result.append({
            'id': str(idx),
            'symbol': row.get('symbol', ''),
            'name': row.get('name', ''),
            'price': row.get('pl', 0),
            'queue_volume': row.get('qo1', 0),
            'queue_count': row.get('qo1', 0),
        })
    
    logger.info(f"Found {len(result)} symbols in sell queue")
    return result


def filter_by_option_symbols(queue_symbols: List[Dict[str, Any]], option_symbols: List[str]) -> List[Dict[str, Any]]:
    """
    فیلتر کردن نمادهای صف بر اساس نمادهای دارای قرارداد اختیار
    
    Args:
        queue_symbols: لیست نمادهای صف خرید/فروش
        option_symbols: لیست نمادهای دارای قرارداد اختیار
        
    Returns:
        List[Dict]: لیست نمادهای صف که قرارداد اختیار دارند
    """
    option_set = set(s.upper() for s in option_symbols)
    filtered = [s for s in queue_symbols if s['symbol'].upper() in option_set]
    logger.info(f"Filtered {len(filtered)} option symbols from {len(queue_symbols)} queue symbols")
    return filtered
