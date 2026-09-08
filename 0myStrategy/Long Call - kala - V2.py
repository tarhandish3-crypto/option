# Long Call - kala.py
# -*- coding: utf-8 -*-

import sys
import time
import logging
import warnings
from pathlib import Path
import requests
import pandas as pd
import jdatetime
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

# Set project path
current_file_path = Path(__file__).resolve()
current_dir = current_file_path.parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

# =====================================================================
# Section 1: Initial Configurations & Mappings
# =====================================================================

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)

IME_BASE_URL = "https://cdn.ime.co.ir/realTimeServer/"

COMMODITY_TO_SYMBOL = {
    'KA': 'کهربا',
    'AB': 'آبان',
    'DN': 'دنا',
    'NQ': 'نقرابی',
    'LG ETC': 'طلا',
    'AY': 'عیار',
    'GZ': 'گنج',
    'ZT': 'زر',
    'ZR': 'زرگر',
    'NZ': 'نفیس',
    'DG': 'درخشان',
    'GoldBar': 'شمش طلا',
    'SilverBar': 'شمش نقره',
    'CU': 'مس کاتد',}

ASSET_TYPE_MAPPING = {
    'کهربا': 'صندوق طلا',
    'آبان': 'صندوق طلا',
    'دنا': 'صندوق طلا',
    'نقرابی': 'صندوق نقره',
    'کارآمد': 'صندوق طلا',
    'طلا': 'صندوق طلا',
    'عیار': 'صندوق طلا',
    'گنج': 'صندوق طلا',
    'زر': 'صندوق طلا',
    'زرگر': 'صندوق طلا',
    'نفیس': 'صندوق طلا',
    'درخشان': 'صندوق طلا',
    'شمش طلا': 'شمش طلا',
    'شمش نقره': 'شمش نقره',}

IME_COMMISSION = {
    'trade_buyer': 0.0012,
    'trade_seller': 0.0012,
    'exercise_buyer': 0.0014,
    'exercise_seller': 0.0014,}

IME_COMMISSION_BY_ASSET = {
    'سکه طلا': {
        'trade_buyer': 0.00136,
        'trade_seller': 0.00136,
        'exercise_buyer': 0.0014,
        'exercise_seller': 0.0014,
    },
    'صندوق طلا': {
        'trade_buyer': 0.0012,
        'trade_seller': 0.0012,
        'exercise_buyer': 0.0014,
        'exercise_seller': 0.0014,
    },
    'صندوق نقره': {
        'trade_buyer': 0.0012,
        'trade_seller': 0.0012,
        'exercise_buyer': 0.0014,
        'exercise_seller': 0.0014,
    },
    'default': {
        'trade_buyer': 0.0012,
        'trade_seller': 0.0012,
        'exercise_buyer': 0.0014,
        'exercise_seller': 0.0014,
    }}


def parse_persian_date(date_str: str) -> jdatetime.date:
    """
    تبدیل رشته تاریخ شمسی (مانند '1405/06/22' یا '1405/06/16 - 17:18:28') به شیء jdatetime.date
    """
    if not date_str or not isinstance(date_str, str):
        return None
    
    try:
        # اگر شامل زمان باشد، بخش تاریخ را جدا می‌کنیم
        clean_date_str = date_str.split('-')[0].strip()
        parts = clean_date_str.split('/')
        if len(parts) == 3:
            year, month, day = map(int, parts)
            return jdatetime.date(year, month, day)
    except Exception:
        pass
    return None

def calculate_days_to_maturity(maturity_date_str: str, order_date_str: str) -> int:
    """
    محاسبه فاصله روزهای بین تاریخ سررسید و تاریخ ثبت/سفارش به شمسی
    """
    d_maturity = parse_persian_date(maturity_date_str)
    d_order = parse_persian_date(order_date_str)
    
    if d_maturity and d_order:
        delta = (d_maturity - d_order).days
        return max(0, delta)
    return 0

def normalize_fa(text: str) -> str:
    """نرمال‌سازی کامل کاراکترهای عربی به فارسی و حذف فواصل اضافه"""
    if not isinstance(text, str):
        return text
    return (text.replace('ي', 'ی').replace('ك', 'ک')
            .replace('\u200c', ' ').strip())


def get_ime_commission(asset_type: str, is_buy: bool = True, is_exercise: bool = False):
    side = 'buyer' if is_buy else 'seller'
    key = f'exercise_{side}' if is_exercise else f'trade_{side}'
    if asset_type in IME_COMMISSION_BY_ASSET:
        return IME_COMMISSION_BY_ASSET[asset_type].get(key, IME_COMMISSION[key])
    return IME_COMMISSION_BY_ASSET['default'].get(key, IME_COMMISSION[key])


# =====================================================================
# Section 2: Fetching Real-Time Market Data via SignalR
# =====================================================================

def negotiate_ime(session):
    params = {
        "clientProtocol": "2.1",
        "connectionData": '[{"name":"marketshub"}]',
        "_": str(time.time()).replace(".", "")[:13],}
    response = session.get(IME_BASE_URL + "negotiate", params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    if not data.get("ConnectionToken"):
        raise RuntimeError("Failed to retrieve ConnectionToken.")
    return data


def connect_ime(session, connection_token):
    params = {
        "clientProtocol": "2.1",
        "connectionData": '[{"name":"marketshub"}]',
        "transport": "longPolling",
        "connectionToken": connection_token,}
    response = session.post(IME_BASE_URL + "connect", params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    message_id = data.get("C")
    if not message_id:
        raise RuntimeError("Failed to retrieve initial MessageId.")
    return data


def start_ime(session, connection_token):
    params = {
        "clientProtocol": "2.1",
        "connectionData": '[{"name":"marketshub"}]',
        "transport": "longPolling",
        "connectionToken": connection_token,
        "_": str(time.time()).replace(".", "")[:13],}
    response = session.post(IME_BASE_URL + "start", params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    if data.get("Response") != "started":
        raise RuntimeError(f"SignalR start failed: {data}")
    return data


def poll_ime(session, connection_token, message_id, timeout=30):
    params = {
        "clientProtocol": "2.1",
        "connectionData": '[{"name":"marketshub"}]',
        "transport": "longPolling",
        "connectionToken": connection_token,}
    response = session.post(
        IME_BASE_URL + "poll",
        params=params,
        data=f"messageId={message_id}",
        timeout=timeout,)
    response.raise_for_status()
    return response.json()


def process_market_hub_messages(messages: list) -> pd.DataFrame:
    """
    پردازش پیام‌های SignalR، استخراج داده‌های اختیار و صندوق‌های پایه،
    نرمال‌سازی متون و ادغام آن‌ها بر اساس CommodityGroup.
    """
    df_options = pd.DataFrame()
    df_funds = pd.DataFrame()

    for message in messages:
        msg_type = message.get("M")
        arguments = message.get("A", [])

        if not arguments or not isinstance(arguments[0], list):
            continue

        if msg_type == "updateMarketsInfo":
            df_options = pd.DataFrame(arguments[0])
        elif msg_type == "updateSandoqMarketsInfo":
            df_funds = pd.DataFrame(arguments[0])
        # elif msg_type == "updateCDCMarketsInfo":
        #     df_CDC_funds = pd.DataFrame(arguments[0])

    if df_options.empty:
        return pd.DataFrame()

    # نرمال‌سازی ستون‌های متنی
    for col in df_options.select_dtypes(include='object').columns:
        df_options[col] = df_options[col].apply(normalize_fa)

    if df_funds.empty:
        return df_options

    for col in df_funds.select_dtypes(include='object').columns:
        df_funds[col] = df_funds[col].apply(normalize_fa)

    # نگاشت نماد پایه بر اساس کد گروه کالا
    df_options['UnderlyingSymbol'] = df_options['CommodityGroup'].map(COMMODITY_TO_SYMBOL)
    
    # -----------------------------------------------------------------
    # فیلتر: حذف شمش طلا، شمش نقره، مس کاتد و نگه داشتن فقط صندوق‌های طلا
    # -----------------------------------------------------------------
    excluded_symbols = ['شمش طلا', 'شمش نقره', 'مس کاتد', 'GoldBar', 'SilverBar', 'CU']
    df_options = df_options[
        ~df_options['UnderlyingSymbol'].isin(excluded_symbols) & 
        ~df_options['CommodityGroup'].isin(excluded_symbols)].copy()
    # -----------------------------------------------------------------

    # انتخاب و تغییر نام ستون‌های مورد نیاز از صندوق‌های پایه
    funds_subset = df_funds[[
        'Symbol', 'Name', 'FinalPrice', 'LastPrice', 'DemandPrice1', 'OfferPrice1']].copy()

    funds_subset.rename(columns={
        'Symbol': 'UnderlyingSymbol',
        'Name': 'UnderlyingName',
        'FinalPrice': 'UnderlyingFinalPrice',
        'LastPrice': 'UnderlyingLastPrice',
        'DemandPrice1': 'UnderlyingBidPrice',
        'OfferPrice1': 'UnderlyingAskPrice',
    }, inplace=True)

    options_subset = df_options[[
        'ContractCode', 'UnderlyingSymbol', 'CallContractDescription', 'CallLastTradingPersianDate',
        'CallOrdersPersianDateTime','StrikePrice', 'CallBidPrice1', 'CallAskPrice1',
        'CallContractSize', 'CallLastTradedPrice', 'CallTradesCount', 'CallTradesVolume',
        'CallOpenInterests', 'CommodityGroup', 'ContractSubGroup']].copy()
    # ادغام دیتافریم اختیارها و صندوق‌های پایه
    df_merged = options_subset.merge(funds_subset, on='UnderlyingSymbol', how='left')

    numeric_cols = [
        'StrikePrice', 'CallContractSize', 'CallTradesVolume',
        'CallLastTradedPrice','StrikePrice', 'CallBidPrice1', 'CallAskPrice1',
        'UnderlyingFinalPrice', 'UnderlyingLastPrice', 'UnderlyingBidPrice', 'UnderlyingAskPrice']

    for col in numeric_cols:
        if col in df_merged.columns:
            df_merged[col] = pd.to_numeric(df_merged[col], errors='coerce')
    
    #فیلتر معاملاتی که حجم صفر دارند. یعنی معامله نشدند
    df_merged = df_merged[df_merged['CallTradesVolume'] > 0]
    
    return df_merged


def fetch_kala_data_realtime(timeout=30) -> pd.DataFrame:
    """دریافت دیتای لحظه‌ای از بورس کالا و پردازش آن"""
    print("Fetching Real-time Market Snapshot from IME...")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

    try:
        negotiate_data = negotiate_ime(session)
        connection_token = negotiate_data["ConnectionToken"]
        connect_data = connect_ime(session, connection_token)
        message_id = connect_data["C"]
        start_ime(session, connection_token)

        poll_data = poll_ime(session, connection_token, message_id, timeout=timeout)
        messages = poll_data.get("M", [])

        df_merged = process_market_hub_messages(messages)
        return df_merged

    finally:
        session.close()


# =====================================================================
# Section 3: Long Call Calculations
# =====================================================================

def long_call_with_fees_kala(premium_call, stock_price, strike_price, contract_size,
                             opt_buy_commission, exercise_fee_rate, days):
    premium_total = -round(premium_call * contract_size, 0)
    entry_fee = round(premium_total * opt_buy_commission, 0)
    initial_investment = premium_total + entry_fee

    intrinsic_value = max(0, stock_price - strike_price) * contract_size

    exercise_fee = 0
    if stock_price > strike_price:
        settlement_amount = strike_price * contract_size
        exercise_fee = -round(settlement_amount * exercise_fee_rate, 0)

    net_profit = intrinsic_value + initial_investment + exercise_fee
    profit_percent = round((net_profit / abs(initial_investment)) * 100, 2) if initial_investment != 0 else 0
    monthly_return = round(profit_percent * (30 / days), 2) if days > 0 else 0

    total_cost_per_share = premium_call + (abs(entry_fee) / contract_size) + (
        abs(exercise_fee) / contract_size) if stock_price > strike_price else premium_call
    break_even_price = round(strike_price + total_cost_per_share, 0)

    break_even_percent = round(((break_even_price - stock_price) / stock_price) * 100, 2) if stock_price > 0 else 0

    if stock_price > 0 and strike_price > 0:
        distance_to_strike = ((stock_price - strike_price) / stock_price) * 100
        max_loss_price_percent = round(distance_to_strike, 2) if distance_to_strike > 0 else 0.0
    else:
        max_loss_price_percent = 0.0

    if stock_price > strike_price:
        price_difference = stock_price - strike_price
        if price_difference > 0:
            total_premium_cost = premium_call * contract_size + abs(entry_fee)
            risk_percent = round((total_premium_cost / (price_difference * contract_size)) * 100, 2)
        else:
            risk_percent = 100.0
    else:
        risk_percent = 100.0

    return {
        'net_profit': net_profit,
        'profit_percent': profit_percent,
        'monthly_return': monthly_return,
        'break_even_price': break_even_price,
        'break_even_percent': break_even_percent,
        'intrinsic_value': intrinsic_value,
        'fees_total': entry_fee + exercise_fee,
        'max_loss_price_percent': max_loss_price_percent,
        'risk_percent': risk_percent,
    }


# =====================================================================
# Section 4: Running Strategy and Filtering
# =====================================================================

def run_long_call_kala_strategy(df_options, max_break_even_percent=25):
    print("Running Long Call strategy evaluation...")
    results_fee = []

    # گام اختصاصی: استخراج داده‌های مرتبط با Call و حذف بخش‌های ناپیوسته/پوت
    # در دیتای بورس کالا هر سطر شامل هر دو حالت کال و پوت است؛ بنابراین فقط موقعیت‌های کال معتبر جداسازی می‌شوند.
    df_calls = df_options.copy()

    for _, item in df_calls.iterrows():
        contract_description = item.get('CallContractCode') or item.get('ContractCode', '')
        strike_price = float(item.get('StrikePrice', 0))

        # تعیین قیمت پریمیوم خرید کال (اولین قیمت پیشنهاد فروش / یا آخرین قیمت معامله کال)
        raw_ask = item.get('CallAskPrice1')
        raw_last = item.get('CallLastTradedPrice')
        
        ask_price = float(raw_ask) if pd.notna(raw_ask) and raw_ask is not None else 0.0
        last_price = float(raw_last) if pd.notna(raw_last) and raw_last is not None else 0.0
        premium_call = ask_price if ask_price > 0 else last_price
        # عدم وجود فروشنده معتبر: رد کردن کامل ردیف
        if premium_call <= 0:
            continue
        

        # تعیین قیمت دارایی پایه
        stock_price = float(item.get('UnderlyingLastPrice', 0) or item.get('UnderlyingFinalPrice', 0))
        contract_size = float(item.get('CallContractSize', 1))
        
        maturity_date_str = str(item.get('CallLastTradingPersianDate'))
        order_date_str = str(item.get('CallOrdersPersianDateTime', ''))
        days = calculate_days_to_maturity(maturity_date_str, order_date_str)

        underlying_symbol = item.get('UnderlyingSymbol')

        # شرط ورود: وجود پریمیوم معتبر برای موقعیت کال، قیمت پایه و روزهای باقی‌مانده
        if premium_call <= 0 or stock_price <= 0:
            continue

        asset_type = ASSET_TYPE_MAPPING.get(underlying_symbol, 'default')
        opt_buy_commission = get_ime_commission(asset_type, is_buy=True, is_exercise=False)
        exercise_fee_rate = get_ime_commission(asset_type, is_buy=True, is_exercise=True)

        results = long_call_with_fees_kala(
            premium_call, stock_price, strike_price, contract_size,
            opt_buy_commission, exercise_fee_rate, days)

        max_loss_price_percent_scale = results['max_loss_price_percent'] * ((30 / days) ** 0.5)
        break_even_percent_scale = results['break_even_percent'] * ((30 / days) ** 0.5)

        results_fee.append({
            'underlying': underlying_symbol,
            'underlying_name': item.get('UnderlyingName', ''),
            'ContractCode': item.get('ContractCode', ''),
            'stock_price': round(stock_price, 0),
            'option_symbol': contract_description,
            'strike': strike_price,
            'premium': round(premium_call, 0),
            'net_profit': results['net_profit'],
            'profit_percent': results['profit_percent'],
            'monthly_return_%': results['monthly_return'],
            'break_even_price': results['break_even_price'],
            'break_even_percent': results['break_even_percent'],
            'break_even_percent_scale': round(break_even_percent_scale, 2),
            'max_loss_price_percent': results['max_loss_price_percent'],
            'max_loss_price_percent_scale': round(max_loss_price_percent_scale, 2),
            'risk_percent': results['risk_percent'],
            'days_to_maturity': days,
            'volume': int(item.get('CallTradesVolume') or 0),
        })

    result_df = pd.DataFrame(results_fee)

    if not result_df.empty:
        result_df_filtered = result_df[result_df['break_even_percent_scale'] <= max_break_even_percent].copy()
        result_df_filtered = result_df_filtered.sort_values(
            ['break_even_percent', 'monthly_return_%'],
            ascending=[True, True]).reset_index(drop=True)
    else:
        result_df_filtered = result_df

    return result_df_filtered


def save_kala_results_to_excel(result_df, filename="result_long_call_kala.xlsx"):
    header_font = Font(name='Segoe UI', size=11, bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='1F4E78', end_color='1F4E78', fill_type='solid')
    alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    body_font = Font(name='Segoe UI', size=10)
    gray_font = Font(color='808080', italic=True, name='Segoe UI', size=10)

    result_df = result_df.rename(columns={
        'underlying': 'نماد پایه',
        'underlying_name': 'نام دارایی پایه',
        'stock_price': 'قیمت نماد پایه',
        'option_symbol': 'نماد اختیار خرید',
        'strike': 'قیمت اعمال',
        'premium': 'پریمیوم (قیمت خرید)',
        'monthly_return_%': 'درصد سود ماهانه',
        'break_even_price': 'قیمت سربه‌سر',
        'break_even_percent': 'درصد فاصله تا نقطه سربه‌سر\n(هرچه کمتر = بهتر)',
        'break_even_percent_scale': 'مقیاس درصد فاصله تا نقطه سربه‌سر\n(هرچه کمتر = بهتر)(به نسبت 30 روز)',
        'max_loss_price_percent': 'درصد فاصله تا زیان حداکثری\n(هرچه بیشتر = امن‌تر)',
        'max_loss_price_percent_scale': 'مقیاس درصد فاصله تا زیان حداکثری\n(هرچه بیشتر = امن‌تر)(به نسبت 30 روز)',
        'volume': 'حجم معاملات روز جاری',
        'risk_percent': 'درصد ریسک نسبت به حاشیه امنیت\n(هرچه کمتر = بهتر)'
    })

    filepath = Path(__file__).parent / filename

    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        result_df.to_excel(writer, sheet_name='long_call_kala', index=False)
        worksheet = writer.sheets['long_call_kala']

        for col_idx in range(1, len(result_df.columns) + 1):
            cell = worksheet.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = alignment

        columns_list = result_df.columns.tolist()
        for row_idx, row in enumerate(result_df.itertuples(index=False), start=2):
            for col_idx, col_name in enumerate(columns_list, start=1):
                cell = worksheet.cell(row=row_idx, column=col_idx)
                val = row[col_idx - 1]
                if val is None or pd.isna(val):
                    cell.value = "-"
                    cell.font = gray_font
                else:
                    cell.font = body_font
                cell.alignment = alignment

        worksheet.auto_filter.ref = f"A1:{get_column_letter(len(result_df.columns))}{len(result_df) + 1}"
        worksheet.freeze_panes = 'A2'

        for col in worksheet.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                if cell.value:
                    text = str(cell.value)
                    line_length = max(len(line) for line in text.split('\n')) if '\n' in text else len(text)
                    if line_length > max_length:
                        max_length = line_length
            worksheet.column_dimensions[column].width = min(max_length + 5, 50)

    print(f"Results successfully saved to: {filepath}")
    return str(filepath)


# =====================================================================
# Section 5: Main Pipeline
# =====================================================================

def main():
    try:
        df_kala = fetch_kala_data_realtime(timeout=30)
        if df_kala.empty:
            print("No data received from IME SignalR endpoint.")
            return

        results = run_long_call_kala_strategy(df_kala, max_break_even_percent=12)

        if results.empty:
            print("No strategy opportunities found matching the specified filters.")
            return

        save_kala_results_to_excel(results, filename="result_long_call_kala.xlsx")

    except Exception as e:
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()