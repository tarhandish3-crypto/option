# options_strategy_runner.py
# -*- coding: utf-8 -*-

import sys
import math
from pathlib import Path
from datetime import datetime
import pandas as pd
from openpyxl.utils import get_column_letter
from openpyxl.styles import PatternFill, Font, Alignment

# تنظیم مسیر پروژه
current_file_path = Path(__file__).resolve()
current_dir = current_file_path.parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

from data.downloader import MarketDownloader
from data.cleaner import DataCleaner
from config import (
    get_commission_rate,
    get_exercise_fee_rate,
    get_symbol_kind,
    get_symbol_market,
    EXERCISE_TAX_RATE,  # نرخ مالیات تسویه/اعمال سمت فروشنده سهم
)


# ============================================================================
# ۱. تابع مستقیم محاسبه وجه تضمین (تضمین اولیه و مسدودی سمات)
# ============================================================================

def calculate_tse_margin(
    option_type: str,
    stock_price: float,
    strike_price: float,
    premium: float,
    contract_size: int = 1000,
    asset_kind: str = 'stock') -> dict:
    """
    محاسبه مستقیم وجه تضمین اولیه و مسدودی براساس فرمول رسمی سمات (بورس تهران)
    """
    opt_type = option_type.upper()
    margin_coeff = 0.15 if asset_kind.lower() == 'etf' else 0.20

    if opt_type == 'CALL':
        otm_amount = max(0, strike_price - stock_price)
    elif opt_type == 'PUT':
        otm_amount = max(0, stock_price - strike_price)

    strike_minus_otm = strike_price - otm_amount
    stock_margin = margin_coeff * stock_price
    base_per_share = max(strike_minus_otm, stock_margin)

    initial_margin_per_share = math.ceil(base_per_share / 10000.0) * 10000.0
    initial_margin_total = round(initial_margin_per_share * contract_size, 0)
    total_premium = round(premium * contract_size, 0)
    required_margin_total = max(0, initial_margin_total - total_premium)

    return {
        'initial_margin': initial_margin_total,
        'required_margin': required_margin_total,
        'initial_margin_per_share': initial_margin_per_share,
    }


# ============================================================================
# ۲. توابع محاسباتی استراتژی‌ها با اعمال EXERCISE_TAX_RATE
# ============================================================================

def calc_long_call(premium, stock_price, strike_price, contract_size, buy_commission, exercise_fee_rate, days):
    """
    محاسبه Long Call: خریدار سهم در زمان اعمال (بدون مالیات فروش سهم)
    """
    premium_total = round(premium * contract_size, 0)
    entry_fee = -round(premium_total * buy_commission, 0)
    cost_basis = premium_total + abs(entry_fee)

    intrinsic_value = max(0, stock_price - strike_price) * contract_size
    exercise_fee = 0
    if stock_price > strike_price:
        settlement_amount = strike_price * contract_size
        exercise_fee = -round(settlement_amount * exercise_fee_rate, 0)

    net_profit = intrinsic_value - cost_basis + exercise_fee
    profit_percent = round((net_profit / cost_basis) * 100, 2) if cost_basis > 0 else 0.0

    days_adj = max(days, 1.0)
    monthly_return = round(profit_percent * (30 / days_adj), 2)

    break_even_price = round(strike_price + (cost_basis / contract_size), 0)
    break_even_percent = round(((break_even_price - stock_price) / stock_price) * 100, 2) if stock_price > 0 else 0.0

    return {
        'net_profit': net_profit,
        'profit_percent': profit_percent,
        'monthly_return': monthly_return,
        'break_even_price': break_even_price,
        'break_even_percent': break_even_percent,
        'capital_at_risk': cost_basis,
        'fees_total': entry_fee + exercise_fee
    }


def calc_long_put(premium, stock_price, strike_price, contract_size, buy_commission, exercise_fee_rate, exercise_tax_rate, days):
    """
    محاسبه Long Put: خریدار اختیار فروش (در اعمال، شما فروشنده سهم هستید و مشمول EXERCISE_TAX_RATE می‌شوید)
    """
    premium_total = round(premium * contract_size, 0)
    entry_fee = -round(premium_total * buy_commission, 0)
    cost_basis = premium_total + abs(entry_fee)

    intrinsic_value = max(0, strike_price - stock_price) * contract_size
    exercise_fee = 0
    exercise_tax = 0

    if stock_price < strike_price:
        settlement_amount = strike_price * contract_size
        exercise_fee = -round(settlement_amount * exercise_fee_rate, 0)
        exercise_tax = -round(settlement_amount * exercise_tax_rate, 0)

    total_exercise_costs = exercise_fee + exercise_tax
    net_profit = intrinsic_value - cost_basis + total_exercise_costs
    profit_percent = round((net_profit / cost_basis) * 100, 2) if cost_basis > 0 else 0.0

    days_adj = max(days, 1.0)
    monthly_return = round(profit_percent * (30 / days_adj), 2)

    total_cost_per_share = (cost_basis + abs(total_exercise_costs)) / contract_size
    break_even_price = round(strike_price - total_cost_per_share, 0)
    break_even_percent = round(((stock_price - break_even_price) / stock_price) * 100, 2) if stock_price > 0 else 0.0

    return {
        'net_profit': net_profit,
        'profit_percent': profit_percent,
        'monthly_return': monthly_return,
        'break_even_price': break_even_price,
        'break_even_percent': break_even_percent,
        'capital_at_risk': cost_basis,
        'fees_total': entry_fee + total_exercise_costs
    }


def calc_short_call(premium, stock_price, strike_price, contract_size, sell_commission, exercise_fee_rate, exercise_tax_rate, days, asset_kind):
    """
    محاسبه Short Call: فروشنده اختیار خرید (در اعمال، شما فروشنده سهم هستید و مشمول EXERCISE_TAX_RATE می‌شوید)
    """
    premium_total = round(premium * contract_size, 0)
    entry_fee = -round(premium_total * sell_commission, 0)

    margin_info = calculate_tse_margin(
        option_type='CALL', stock_price=stock_price, strike_price=strike_price,
        premium=premium, contract_size=contract_size, asset_kind=asset_kind
    )
    capital_at_risk = margin_info['required_margin']

    initial_cash_flow = premium_total + entry_fee
    intrinsic_liability = max(0, stock_price - strike_price) * contract_size

    exercise_fee = 0
    exercise_tax = 0

    if stock_price > strike_price:
        settlement_amount = strike_price * contract_size
        exercise_fee = -round(settlement_amount * exercise_fee_rate, 0)
        exercise_tax = -round(settlement_amount * exercise_tax_rate, 0)

    total_exercise_costs = exercise_fee + exercise_tax
    net_profit = initial_cash_flow - intrinsic_liability + total_exercise_costs
    profit_percent = round((net_profit / capital_at_risk) * 100, 2) if capital_at_risk > 0 else 0.0

    days_adj = max(days, 1.0)
    monthly_return = round(profit_percent * (30 / days_adj), 2)

    total_credit_per_share = premium - (abs(entry_fee) / contract_size)
    if stock_price > strike_price:
        total_credit_per_share -= abs(total_exercise_costs) / contract_size

    break_even_price = round(strike_price + total_credit_per_share, 0)
    break_even_percent = round(((break_even_price - stock_price) / stock_price) * 100, 2) if stock_price > 0 else 0.0
    otm_percent = round(((strike_price - stock_price) / stock_price) * 100, 2) if stock_price > 0 else 0.0

    return {
        'net_profit': net_profit,
        'profit_percent': profit_percent,
        'monthly_return': monthly_return,
        'break_even_price': break_even_price,
        'break_even_percent': break_even_percent,
        'initial_margin': margin_info['initial_margin'],
        'required_margin': capital_at_risk,
        'otm_percent': otm_percent,
        'fees_total': entry_fee + total_exercise_costs
    }


def calc_short_put(premium, stock_price, strike_price, contract_size, sell_commission, exercise_fee_rate, days, asset_kind):
    """
    محاسبه Short Put: خریدار سهم در زمان اعمال (بدون مالیات فروش سهم)
    """
    premium_total = round(premium * contract_size, 0)
    entry_fee = -round(premium_total * sell_commission, 0)

    margin_info = calculate_tse_margin(
        option_type='PUT', stock_price=stock_price, strike_price=strike_price,
        premium=premium, contract_size=contract_size, asset_kind=asset_kind
    )
    capital_at_risk = margin_info['required_margin']

    initial_cash_flow = premium_total + entry_fee
    intrinsic_liability = max(0, strike_price - stock_price) * contract_size

    exercise_fee = 0
    if stock_price < strike_price:
        settlement_amount = strike_price * contract_size
        exercise_fee = -round(settlement_amount * exercise_fee_rate, 0)

    net_profit = initial_cash_flow - intrinsic_liability + exercise_fee
    profit_percent = round((net_profit / capital_at_risk) * 100, 2) if capital_at_risk > 0 else 0.0

    days_adj = max(days, 1.0)
    monthly_return = round(profit_percent * (30 / days_adj), 2)

    total_credit_per_share = premium - (abs(entry_fee) / contract_size)
    if stock_price < strike_price:
        total_credit_per_share -= abs(exercise_fee) / contract_size

    break_even_price = round(strike_price - total_credit_per_share, 0)
    break_even_percent = round(((stock_price - break_even_price) / stock_price) * 100, 2) if stock_price > 0 else 0.0
    otm_percent = round(((stock_price - strike_price) / stock_price) * 100, 2) if stock_price > 0 else 0.0

    return {
        'net_profit': net_profit,
        'profit_percent': profit_percent,
        'monthly_return': monthly_return,
        'break_even_price': break_even_price,
        'break_even_percent': break_even_percent,
        'initial_margin': margin_info['initial_margin'],
        'required_margin': capital_at_risk,
        'otm_percent': otm_percent,
        'fees_total': entry_fee + exercise_fee
    }


# ============================================================================
# ۳. دریافت و پاکسازی داده‌ها
# ============================================================================

def load_market_data():
    """بارگذاری داده‌ها از TSE و اعمال فیلترهای استاندارد"""
    try:
        df_raw = MarketDownloader.from_tsetmc_direct()
    except Exception as e:
        print(f"Error fetching data from TSETMC server: {e}")
        return pd.DataFrame()

    if df_raw is None or df_raw.empty:
        print("No market data received from TSETMC server.")
        return pd.DataFrame()

    df_cleaned = DataCleaner.clean(df_raw)
    df_final = DataCleaner.add_derived_columns(df_cleaned)

    df_filtered = df_final[df_final['DaysToMaturity'] > 0.0].copy()

    EXCLUDED_UNDERLYING = ['اهرم']
    EXCLUDED_NAME_PATTERN = ['1405/04', '1405-04']
    exclude_mask = (
        df_filtered['UnderlyingTicker'].isin(EXCLUDED_UNDERLYING)
    ) & (
        df_filtered['Name'].str.contains('|'.join(EXCLUDED_NAME_PATTERN), na=False)
    )
    return df_filtered[~exclude_mask].copy()


# ============================================================================
# ۴. پردازش هم‌زمان چهار استراتژی
# ============================================================================

def run_all_strategies(df_market):
    """اجرای الگوریتم استراتژی‌های چهارگانه روی داده‌های بازار"""
    df_call = df_market[df_market['Type'].apply(lambda x: x.name == 'CALL')].copy()
    df_put = df_market[df_market['Type'].apply(lambda x: x.name == 'PUT')].copy()

    long_call_list, short_call_list = [], []
    long_put_list, short_put_list = [], []

    # --- A. پردازش اختیار خرید (CALL) ---
    for underlying, group in df_call.groupby('UnderlyingTicker'):
        market = get_symbol_market(underlying)
        kind = get_symbol_kind(underlying)

        buy_comm = get_commission_rate(market, 'option', True)
        sell_comm = get_commission_rate(market, 'option', False)
        ex_fee = get_exercise_fee_rate(market, kind)

        for _, item in group.iterrows():
            ticker, strike = item['Ticker'], item['StrikePrice']
            stock_price, contract_size, days = item['UnderlyingPrice'], item['ContractSize'], item['DaysToMaturity']
            vol = int(item.get('Volume', 0))

            ask_price = item.get('AskPrice', 0)
            bid_price = item.get('BidPrice', 0)

            # 1. Long Call
            if ask_price and not pd.isna(ask_price) and ask_price > 0:
                res_lc = calc_long_call(ask_price, stock_price, strike, contract_size, buy_comm, ex_fee, days)
                long_call_list.append({
                    'underlying': underlying, 'stock_price': round(stock_price), 'option_symbol': ticker,
                    'strike': strike, 'premium': round(ask_price), 'net_profit': res_lc['net_profit'],
                    'profit_percent': res_lc['profit_percent'], 'monthly_return_%': res_lc['monthly_return'],
                    'break_even_price': res_lc['break_even_price'], 'break_even_percent': res_lc['break_even_percent'],
                    'capital_at_risk': res_lc['capital_at_risk'], 'days_to_maturity': days, 'volume': vol
                })

            # 2. Short Call
            prem_sc = bid_price if (bid_price and not pd.isna(bid_price) and bid_price > 0) else ask_price
            if prem_sc and not pd.isna(prem_sc) and prem_sc > 0:
                res_sc = calc_short_call(
                    prem_sc, stock_price, strike, contract_size, sell_comm,
                    ex_fee, EXERCISE_TAX_RATE, days, kind
                )
                short_call_list.append({
                    'underlying': underlying, 'stock_price': round(stock_price), 'option_symbol': ticker,
                    'strike': strike, 'premium': round(prem_sc), 'net_profit': res_sc['net_profit'],
                    'profit_percent': res_sc['profit_percent'], 'monthly_return_%': res_sc['monthly_return'],
                    'break_even_price': res_sc['break_even_price'], 'break_even_percent': res_sc['break_even_percent'],
                    'otm_percent': res_sc['otm_percent'], 'initial_margin': res_sc['initial_margin'],
                    'required_margin': res_sc['required_margin'], 'days_to_maturity': days, 'volume': vol
                })

    # --- B. پردازش اختیار فروش (PUT) ---
    for underlying, group in df_put.groupby('UnderlyingTicker'):
        market = get_symbol_market(underlying)
        kind = get_symbol_kind(underlying)

        buy_comm = get_commission_rate(market, 'option', True)
        sell_comm = get_commission_rate(market, 'option', False)
        ex_fee = get_exercise_fee_rate(market, kind)

        for _, item in group.iterrows():
            ticker, strike = item['Ticker'], item['StrikePrice']
            stock_price, contract_size, days = item['UnderlyingPrice'], item['ContractSize'], item['DaysToMaturity']
            vol = int(item.get('Volume', 0))

            ask_price = item.get('AskPrice', 0)
            bid_price = item.get('BidPrice', 0)

            # 3. Long Put
            if ask_price and not pd.isna(ask_price) and ask_price > 0:
                res_lp = calc_long_put(
                    ask_price, stock_price, strike, contract_size, buy_comm,
                    ex_fee, EXERCISE_TAX_RATE, days
                )
                long_put_list.append({
                    'underlying': underlying, 'stock_price': round(stock_price), 'option_symbol': ticker,
                    'strike': strike, 'premium': round(ask_price), 'net_profit': res_lp['net_profit'],
                    'profit_percent': res_lp['profit_percent'], 'monthly_return_%': res_lp['monthly_return'],
                    'break_even_price': res_lp['break_even_price'], 'break_even_percent': res_lp['break_even_percent'],
                    'capital_at_risk': res_lp['capital_at_risk'], 'days_to_maturity': days, 'volume': vol
                })

            # 4. Short Put
            prem_sp = bid_price if (bid_price and not pd.isna(bid_price) and bid_price > 0) else ask_price
            if prem_sp and not pd.isna(prem_sp) and prem_sp > 0:
                res_sp = calc_short_put(prem_sp, stock_price, strike, contract_size, sell_comm, ex_fee, days, kind)
                short_put_list.append({
                    'underlying': underlying, 'stock_price': round(stock_price), 'option_symbol': ticker,
                    'strike': strike, 'premium': round(prem_sp), 'net_profit': res_sp['net_profit'],
                    'profit_percent': res_sp['profit_percent'], 'monthly_return_%': res_sp['monthly_return'],
                    'break_even_price': res_sp['break_even_price'], 'break_even_percent': res_sp['break_even_percent'],
                    'otm_percent': res_sp['otm_percent'], 'initial_margin': res_sp['initial_margin'],
                    'required_margin': res_sp['required_margin'], 'days_to_maturity': days, 'volume': vol
                })

    def sort_df(df_data):
        df = pd.DataFrame(df_data)
        if not df.empty:
            return df.sort_values(by=['monthly_return_%'], ascending=False).reset_index(drop=True)
        return df

    return {
        'long_call': sort_df(long_call_list),
        'short_call': sort_df(short_call_list),
        'long_put': sort_df(long_put_list),
        'short_put': sort_df(short_put_list)
    }


# ============================================================================
# ۵. خروجی اکسل در یک فایل واحد با شیت‌های مجزا و اضافه کردن فیلتر
# ============================================================================

def export_to_excel_files(results_dict):
    """ذخیره تمام استراتژی‌ها در یک فایل اکسل واحد شامل شیت‌های مجزا همراه با فیلتر سرستون‌ها"""
    header_font = Font(name='Segoe UI', size=11, bold=True, color='FFFFFF')
    alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    body_font = Font(name='Segoe UI', size=10)

    color_scheme = {
        'long_call': '1E6B39',   # سبز
        'short_call': '4C2882',  # بنفش
        'long_put': 'A61C1C',    # قرمز
        'short_put': '1F497D'    # آبی
    }

    rename_dict = {
        'underlying': 'نماد پایه',
        'stock_price': 'قیمت سهم',
        'option_symbol': 'نماد اختیار',
        'strike': 'قیمت اعمال',
        'premium': 'پریمیوم (قیمت)',
        'net_profit': 'سود خالص (ریال)',
        'profit_percent': 'درصد سود کل',
        'monthly_return_%': 'درصد سود ماهانه',
        'break_even_price': 'قیمت سربه‌سر',
        'break_even_percent': 'فاصله تا سربه‌سر (%)',
        'capital_at_risk': 'سرمایه درگیر (خرید)',
        'initial_margin': 'وجه تضمین اولیه',
        'required_margin': 'وجه تضمین مسدودی (سرمایه درگیر)',
        'otm_percent': 'درصد OTM بودن',
        'days_to_maturity': 'روز تا سررسید',
        'volume': 'حجم معاملات'
    }

    file_name = "options_strategies_result.xlsx"
    filepath = Path(__file__).parent / file_name

    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        for strategy_name, df in results_dict.items():
            if df.empty:
                continue

            df_renamed = df.rename(columns=rename_dict)
            df_renamed.to_excel(writer, sheet_name=strategy_name, index=False)
            ws = writer.sheets[strategy_name]

            # اضافه کردن استایل سرستون
            fill = PatternFill(start_color=color_scheme.get(strategy_name, '1F497D'),
                               end_color=color_scheme.get(strategy_name, '1F497D'), 
                               fill_type='solid')
            
            for col_idx in range(1, len(df_renamed.columns) + 1):
                cell = ws.cell(row=1, column=col_idx)
                cell.font, cell.fill, cell.alignment = header_font, fill, alignment

            # تنظیم عرض ستون‌ها و استایل داده‌ها
            for col in ws.columns:
                max_len = max(len(str(cell.value or '')) for cell in col)
                ws.column_dimensions[col[0].column_letter].width = min(max_len + 5, 40)
                for cell in col:
                    if cell.row > 1:
                        cell.font, cell.alignment = body_font, alignment

            # فعال‌سازی AutoFilter روی تمام سرستون‌ها
            ws.auto_filter.ref = ws.dimensions

    print(f"Result file saved successfully: {file_name}")


# ============================================================================
# ۶. نقطه ورود اصلی (Main)
# ============================================================================

def main():
    df_market = load_market_data()

    if df_market.empty:
        print("No market data found or server error.")
        return

    results = run_all_strategies(df_market)
    export_to_excel_files(results)


if __name__ == "__main__":
    main()