# Long Call - kala.py
# -*- coding: utf-8 -*-


import sys
from pathlib import Path

# تنظیم مسیر پروژه
current_file_path = Path(__file__).resolve()
current_dir = current_file_path.parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

import warnings
import logging
import requests
import pandas as pd
import re
import jdatetime
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

# =====================================================================
# بخش 1: تنظیمات اولیه
# =====================================================================

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)

RISK_FREE_RATE = 0.30  # ۳۰ درصد

# =====================================================================
# بخش 2: توابع استخراج داده از بورس کالا
# =====================================================================


def extract_strike_from_description(description: str) -> float:
    """
    استخراج قیمت اعمال از توضیحات قرارداد
    مثال: '... با قیمت اعمال 22,000 ریال' -> 22000
    """
    if pd.isna(description):
        return 0.0

    desc = str(description)

    # الگوی قیمت اعمال: اعداد با کاما یا بدون کاما
    pattern = r'قیمت اعمال\s*([\d,،]+)'

    match = re.search(pattern, desc)
    if match:
        # حذف تمام کاماها (فارسی و انگلیسی)
        strike_str = match.group(1).replace(',', '').replace('،', '')
        try:
            return float(strike_str)
        except:
            return 0.0

    return 0.0


def extract_fund_name(description: str) -> str:
    """
    استخراج نام دارایی پایه از توضیحات قرارداد
    بر اساس ساختار: قرارداد اختیار معامله [خرید/فروش] [دارایی پایه] سررسید ...
    """
    if pd.isna(description):
        return ""

    desc = str(description)

    # حذف عبارت ابتدایی
    cleaned = re.sub(r'^قرارداد اختیار معامله (خرید|فروش)\s+', '', desc)
    cleaned = re.sub(r'واحدهای سرمایه گذاری\s+', '', cleaned)

    # استخراج تا کلمه "سررسید"
    match = re.search(r'^(.*?)\s+سررسید', cleaned)
    if match:
        return match.group(1).strip()

    return ""


def extract_option_type(contract_code: str) -> str:
    """
    تشخیص نوع اختیار از روی کد قرارداد
    """
    if pd.isna(contract_code):
        return 'Unknown'

    code = str(contract_code)

    if 'C' in code and 'P' not in code:
        return 'Call'
    elif 'P' in code:
        return 'Put'
    else:
        return 'Unknown'


def calculate_days_to_maturity(delivery_date: str, last_trade_date: str) -> int:
    """
    محاسبه تعداد روزهای مانده تا سررسید
    """
    if pd.isna(delivery_date) or pd.isna(last_trade_date):
        return 0

    try:
        # تبدیل تاریخ شمسی به میلادی
        delivery_parts = delivery_date.split('/')
        last_trade_parts = last_trade_date.split('/')

        delivery_gregorian = jdatetime.date(
            int(delivery_parts[0]),
            int(delivery_parts[1]),
            int(delivery_parts[2])).togregorian()

        last_trade_gregorian = jdatetime.date(
            int(last_trade_parts[0]),
            int(last_trade_parts[1]),
            int(last_trade_parts[2])).togregorian()

        # اختلاف به روز
        delta = delivery_gregorian - last_trade_gregorian
        return delta.days

    except:
        return 0


def summarize_contract(group, last_market_date):
    """
    خلاصه‌سازی داده‌های هر قرارداد
    """
    # مرتب‌سازی بر اساس تاریخ (جدیدترین آخر)
    group = group.sort_values('DT_en', ascending=False)

    # پیدا کردن ردیف مربوط به آخرین روز بازار
    latest_day_row = group[group['DT_en'] == last_market_date]

    if not latest_day_row.empty:
        # اگر در آخرین روز بازار معامله داشته، از آن استفاده کن
        latest = latest_day_row.iloc[0].copy()
    else:
        # اگر در آخرین روز بازار معامله نداشته،
        # از آخرین روزی که معامله داشته استفاده کن
        latest = group.iloc[0].copy()

        # اما تاریخ را به آخرین روز بازار تغییر بده
        # و حجم و ارزش را صفر کن (چون در آن روز معامله نداشته)
        latest['TradesVolume'] = 0
        latest['TradesValue'] = 0
        latest['DT_en'] = last_market_date

    # تبدیل آخرین روز به دیکشنری
    summary = latest.to_dict()

    # محاسبه مجموع و میانگین
    total_volume = group['TradesVolume'].sum()
    days_count = len(group)

    # میانگین روزانه
    summary['AvgTradesVolume'] = round(
        total_volume / days_count, 0) if days_count > 0 else 0

    return pd.Series(summary)


def fetch_kala_data(from_date='1405/05/15', to_date='1406/5/22'):
    """
    دریافت داده‌های اختیار معامله از بورس کالا
    """
    print("Fetching data from IME (Bours Kala)...")

    url = "https://www.ime.co.ir/subsystems/ime/option/optionboarddata.ashx"

    params = {
        'f': from_date,
        't': to_date,
        'c': '-1',
        'ot': '0',
        'lang': '8',
        'order': 'asc',
        'offset': '0',
    }

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:153.0) Gecko/20100101 Firefox/153.0',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Pragma': 'no-cache',
    }

    # درخواست GET با استفاده از Session برای حفظ کوکی‌ها
    session = requests.Session()
    response = session.get(url, params=params, headers=headers)

    # بررسی وضعیت درخواست
    response.raise_for_status()

    # تبدیل به JSON
    response_data = response.json()

    rows = response_data.get('rows', [])
    df_rows = pd.DataFrame(rows)

    if df_rows.empty:
        print("No data received from IME.")
        return df_rows

    # افزودن ستون‌های محاسباتی
    df_rows['StrikePrice'] = df_rows['ContractDescription'].apply(
        extract_strike_from_description)
    df_rows['AssetName'] = df_rows['ContractDescription'].apply(
        extract_fund_name)
    df_rows['OptionType'] = df_rows['ContractCode'].apply(extract_option_type)
    df_rows['DaysToMaturity'] = df_rows.apply(
        lambda row: calculate_days_to_maturity(row['DeliveryDate'], row['DT']), axis=1)
    df_rows['DT_en'] = pd.to_datetime(df_rows['DT_en'], errors='coerce')

    # محاسبه آخرین روز معاملاتی کل بازار
    last_market_date = df_rows['DT_en'].max()

    # خلاصه‌سازی هر قرارداد
    df_rows = df_rows.groupby('ContractCode', group_keys=False).apply(
        lambda g: summarize_contract(g, last_market_date), include_groups=False).reset_index(drop=True)

    # حذف قراردادهای بدون معامله
    df_rows = df_rows[df_rows['AvgTradesVolume'] > 0]

    # مرتب‌سازی
    df_rows = df_rows.sort_values(
        ['AssetName', 'OptionType', 'StrikePrice'],
        ascending=[True, True, True]).reset_index(drop=True)

    print(f"Total records: {len(df_rows)}")
    print(f"Unique assets: {len(df_rows['AssetName'].unique())}")

    return df_rows


# =====================================================================
# بخش 3: تابع محاسبه Long Call برای بورس کالا (هماهنگ با نسخه اصلی)
# =====================================================================

def long_call_with_fees_kala(premium_call, stock_price, strike_price, contract_size,
                             opt_buy_commission, exercise_fee_rate, days):
    """
    محاسبه بازده استراتژی Long Call برای بورس کالا با احتساب کارمزدها
    (هماهنگ با تابع long_call_with_fees در نسخه اصلی)
    """
    # ========== 1. محاسبه هزینه‌های ورود ==========
    premium_total = -round(premium_call * contract_size, 0)
    entry_fee = round(premium_total * opt_buy_commission, 0)

    # ========== 2. سرمایه اولیه ==========
    initial_investment = premium_total + entry_fee

    # ========== 3. محاسبه سود ناخالص در سررسید ==========
    intrinsic_value = max(0, stock_price - strike_price) * contract_size

    # ========== 4. کارمزد اعمال ==========
    exercise_fee = 0
    if stock_price > strike_price:
        settlement_amount = strike_price * contract_size
        exercise_fee = -round(settlement_amount * exercise_fee_rate, 0)

    # ========== 5. سود خالص نهایی ==========
    net_profit = intrinsic_value + initial_investment + exercise_fee

    # ========== 6. بازده درصدی ==========
    profit_percent = round((net_profit / abs(initial_investment))
                           * 100, 2) if initial_investment != 0 else 0
    monthly_return = round(profit_percent * (30 / days), 2)

    # ========== 7. نقطه سربه‌سر ==========
    total_cost_per_share = premium_call + (abs(entry_fee) / contract_size) + (
        abs(exercise_fee) / contract_size) if stock_price > strike_price else premium_call
    break_even_price = round(strike_price + total_cost_per_share, 0)

    # ========== 8. درصد فاصله تا نقطه سربه‌سر ==========
    if break_even_price != 0:
        break_even_percent = round(
            ((break_even_price - stock_price) / stock_price) * 100, 2)
    else:
        break_even_percent = 0

    return {
        'net_profit': net_profit,
        'profit_percent': profit_percent,
        'monthly_return': monthly_return,
        'break_even_price': break_even_price,
        'break_even_percent': break_even_percent,
        'intrinsic_value': intrinsic_value,
        'fees_total': entry_fee + exercise_fee
    }


# =====================================================================
# بخش 4: توابع اصلی اجرای استراتژی (هماهنگ با نسخه اصلی)
# =====================================================================

def load_and_filter_kala_data(from_date='1405/05/15', to_date='1406/5/22'):
    """
    بارگذاری و فیلتر کردن داده‌های بورس کالا
    (هماهنگ با تابع load_and_filter_data در نسخه اصلی)
    """
    # 1. دریافت داده از بورس کالا
    df_kala = fetch_kala_data(from_date, to_date)

    if df_kala.empty:
        print("No data received from IME.")
        return pd.DataFrame()

    # 2. فیلتر کردن CALL
    df_call = df_kala[df_kala['OptionType'] == 'Call'].copy()

    # فیلتر بر اساس روز تا سررسید
    df_call = df_call[df_call['DaysToMaturity'] > 2.0].copy()

    # حذف قراردادهای بدون قیمت معتبر
    df_call = df_call[df_call['LastPrice'] > 0].copy()
    df_call = df_call[df_call['StrikePrice'] > 0].copy()

    print(f"Call options after filtering: {len(df_call)}")

    return df_call


def run_long_call_kala_strategy(df_options, max_break_even_percent=12):
    """
    اجرای استراتژی Long Call روی داده‌های بورس کالا
    (هماهنگ با تابع run_long_call_strategy در نسخه اصلی)
    """
    print("Running Long Call strategy for Kala...")

    # نرخ‌های کارمزد (برای بورس کالا)
    OPT_BUY_COMMISSION = 0.0003  # 0.03%
    EXERCISE_FEE_RATE = 0.0003   # 0.03%

    results_fee = []

    for _, item in df_options.iterrows():
        # استخراج اطلاعات
        ticker = item.get('ContractCode', '')
        strike_price = item.get('StrikePrice', 0)
        premium_call = item.get('LastPrice', 0)  # قیمت آخرین معامله
        stock_price = item.get('UnderlyingPrice', 0)
        contract_size = 1  # اندازه قرارداد در بورس کالا معمولاً 1 است
        days = item.get('DaysToMaturity', 0)
        asset_name = item.get('AssetName', '')

        if premium_call <= 0 or stock_price <= 0 or days <= 0:
            continue

        # محاسبات با کارمزد (همانند نسخه اصلی)
        results = long_call_with_fees_kala(
            premium_call, stock_price, strike_price, contract_size,
            OPT_BUY_COMMISSION, EXERCISE_FEE_RATE, days)

        # ذخیره نتایج (همانند نسخه اصلی)
        results_fee.append({
            'underlying': asset_name,
            'stock_price': round(stock_price, 0),
            'option_symbol': ticker,
            'strike': strike_price,
            'premium': round(premium_call, 0),
            'stock_price': round(stock_price, 0),
            'net_profit': results['net_profit'],
            'profit_percent': results['profit_percent'],
            'monthly_return_%': results['monthly_return'],
            'break_even_price': results['break_even_price'],
            'break_even_percent': results['break_even_percent'],
            'days_to_maturity': days,
            'volume': int(item.get('AvgTradesVolume', 0))
        })

    result_df = pd.DataFrame(results_fee)
    print(f"Initial results: {len(result_df)}")

    # فیلتر بر اساس درصد فاصله تا نقطه سربه‌سر (همانند نسخه اصلی)
    if not result_df.empty:
        result_df_filtered = result_df[result_df['break_even_percent']
                                       <= max_break_even_percent].copy()
        result_df_filtered = result_df_filtered.sort_values(
            ['break_even_percent', 'monthly_return_%'],
            ascending=[True, True]
        ).reset_index(drop=True)
        print(f"Filtered results: {len(result_df_filtered)}")
    else:
        result_df_filtered = result_df

    return result_df_filtered


def save_kala_results_to_excel(result_df, filename="result_long_call_kala.xlsx"):
    """
    ذخیره نتایج بورس کالا در فایل اکسل
    (هماهنگ با تابع save_results_to_excel در نسخه اصلی)
    """
    # تنظیمات استایل
    header_font = Font(name='Segoe UI', size=11, bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='1F4E78',
                              end_color='1F4E78', fill_type='solid')
    alignment = Alignment(horizontal='center',
                          vertical='center', wrap_text=True)
    body_font = Font(name='Segoe UI', size=10)
    gray_font = Font(color='808080', italic=True, name='Segoe UI', size=10)

    # ذخیره در پوشه 0myStrategy
    filepath = Path(__file__).parent / filename

    print(f"Saving results to: {filepath}")

    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        result_df.to_excel(writer, sheet_name='long_call_kala', index=False)
        worksheet = writer.sheets['long_call_kala']

        # اعمال استایل به هدر
        for col_idx in range(1, len(result_df.columns) + 1):
            cell = worksheet.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = alignment

        # اعمال استایل به بدنه
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

        # تنظیم خودکار عرض ستون‌ها
        for col in worksheet.columns:
            max_len = 0
            for cell in col:
                val = str(cell.value or '')
                actual_len = sum(2 if ord(c) > 128 else 1 for c in val)
                if actual_len > max_len:
                    max_len = actual_len
            col_letter = get_column_letter(col[0].column)
            worksheet.column_dimensions[col_letter].width = min(
                (max_len + 4), 50)

        # اعمال فیلتر و Freeze Panes
        worksheet.auto_filter.ref = f"A1:{get_column_letter(len(result_df.columns))}{len(result_df) + 1}"
        worksheet.freeze_panes = 'A2'

    print(f"Result saved: {filepath}")
    return str(filepath)


def main():
    """
    تابع اصلی اجرای استراتژی Long Call برای بورس کالا
    (هماهنگ با تابع main در نسخه اصلی)
    """
    try:
        # 1. بارگذاری و فیلتر داده‌ها
        filtered_data = load_and_filter_kala_data(
            from_date='1405/05/15',
            to_date='1406/5/22')

        if filtered_data.empty:
            print("No data found.")
            return

        # 2. اجرای استراتژی
        results = run_long_call_kala_strategy(
            filtered_data, max_break_even_percent=12)

        if results.empty:
            print("No results found.")
            return

        # 3. ذخیره نتایج
        save_kala_results_to_excel(
            results,
            filename="result_long_call_kala.xlsx")

    except Exception as e:
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
