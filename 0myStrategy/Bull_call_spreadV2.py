# bull_call_spread_strategy.py
# -*- coding: utf-8 -*-

import sys
from pathlib import Path

# تنظیم مسیر پروژه جهت دسترسی به ماژول‌های ریشه
current_file_path = Path(__file__).resolve()
current_dir = current_file_path.parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

import math
from datetime import datetime
from config import (
    EXERCISE_TAX_RATE,
    get_commission_rate,
    get_exercise_fee_rate,
    get_symbol_kind,
    get_symbol_market,)
from data.cleaner import DataCleaner
from data.downloader import MarketDownloader
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
import pandas as pd


RISK_FREE_BREAK_EVEN_SENTINEL = -999.0
RISK_FREE_RETURN_SENTINEL = 999999.0


def bull_call_spread_analysis(
    stock_price,
    long_strike,
    long_ask_premium,
    short_strike,
    short_bid_premium,
    contract_size,
    opt_buy_commission,
    opt_sell_commission,
    exercise_fee_rate,
    exercise_tax_rate,
    days,):
    """محاسبه پارامترهای استراتژی با اعمال جریمه منطقه زیان و تعدیل زمان سررسید.
    """

    # ۱. پریمیوم و کارمزد ورود
    long_premium_total = round(long_ask_premium * contract_size, 0)
    long_entry_fee = round(long_premium_total * opt_buy_commission, 0)

    short_premium_total = round(short_bid_premium * contract_size, 0)
    short_entry_fee = -round(short_premium_total * opt_sell_commission, 0)

    net_debit = (long_premium_total + long_entry_fee) - (short_premium_total + short_entry_fee)

    # ۲. کارمزدهای اعمال + مالیات نقل و انتقال سهم (فقط برای لگ فروش)
    long_exercise_fee = round(
        (long_strike * contract_size) * exercise_fee_rate, 0)
    short_exercise_fee = round(
        (short_strike * contract_size) * exercise_fee_rate, 0)

    short_transfer_tax = round((short_strike * contract_size) * exercise_tax_rate, 0)
    short_total_exercise_cost = short_exercise_fee + short_transfer_tax
    total_exercise_costs = long_exercise_fee + short_total_exercise_cost

    # ۳. تحلیل سقف و کف سود و زیان
    min_profit_or_loss = -net_debit
    max_payoff = (short_strike - long_strike) * contract_size
    max_net_profit = max_payoff - net_debit - total_exercise_costs

    if max_net_profit <= 0:
        return {'status': 'DISCARD'}

    capital_at_risk = max(1.0, net_debit)
    days_safe = max(1.0, float(days))

    # حالت آربیتراژ (بدون ریسک)
    if min_profit_or_loss >= 0:
        return {
            'status': 'RISK_FREE',
            'capital_at_risk': 0,
            'max_net_profit': max_net_profit,
            'max_profit_percent': 'Arbitrage',
            'monthly_return': RISK_FREE_RETURN_SENTINEL,
            'break_even_price': 'Risk Free',
            'break_even_percent': RISK_FREE_BREAK_EVEN_SENTINEL,
            'break_even_percent_scale': RISK_FREE_BREAK_EVEN_SENTINEL,
            'risk_reward_ratio': 'Infinite',
        }

    # ۴. محاسبه قیمت و درصد سربه‌سر
    break_even_price = long_strike + (
        (net_debit + long_exercise_fee) / contract_size)

    if stock_price > 0:
        break_even_percent = round(
            ((break_even_price - stock_price) / stock_price) * 100, 2)
    else:
        break_even_percent = 0.0

    # ۵. ضریب تعدیل زمانی برای مقیاس کردن درصد رشد تا سربه‌سر بر حسب زمان
    time_factor = math.sqrt(days_safe / 30.0)

    # ۶. سایر شاخص‌ها
    break_even_percent_scale = round(break_even_percent / time_factor, 2)
    max_profit_percent = round((max_net_profit / capital_at_risk) * 100, 2)
    monthly_return = round(max_profit_percent * (30 / days_safe), 2)
    risk_reward_ratio = round(max_net_profit / capital_at_risk, 2)

    return {
        'status': 'VALID',
        'capital_at_risk': capital_at_risk,
        'max_net_profit': max_net_profit,
        'max_profit_percent': max_profit_percent,
        'monthly_return': monthly_return,
        'break_even_price': round(break_even_price, 0),
        'break_even_percent': break_even_percent,
        'break_even_percent_scale': break_even_percent_scale,
        'risk_reward_ratio': risk_reward_ratio,
    }


def load_and_filter_data():
    """بارگذاری داده‌های بازار و فیلتر اولیه اختیارهای خرید (CALL)."""
    df_raw = MarketDownloader.from_tsetmc_direct()
    df_cleaned = DataCleaner.clean(df_raw)
    df_final = DataCleaner.add_derived_columns(df_cleaned)

    filter_option = df_final[
        (df_final['DaysToMaturity'] > 0.0)
        & (df_final['Type'].apply(lambda x: x.name == 'CALL'))].copy()

    EXCLUDED_UNDERLYING = ['اهرم']
    EXCLUDED_NAME_PATTERN = ['1405/04', '1405-04']
    exclude_mask = (
        filter_option['UnderlyingTicker'].isin(EXCLUDED_UNDERLYING)) & (
        filter_option['Name'].str.contains(
            '|'.join(EXCLUDED_NAME_PATTERN), na=False))
    filter_option = filter_option[~exclude_mask].copy()

    return filter_option


def calculate_composite_score(df):
    """محاسبه امتیاز کامپوزیت با نرمال‌سازی Min-Max شاخص‌های اصلی."""
    if df.empty:
        return df

    df = df.copy()

    # استخراج کمترین حجم معاملات بین دو ساقه
    df['min_volume'] = df[['long_volume', 'short_volume']].min(axis=1)
    risk_free_mask = df['break_even_percent_scale'] == RISK_FREE_BREAK_EVEN_SENTINEL
    df_normal = df[~risk_free_mask].copy()
    df_risk_free = df[risk_free_mask].copy()

    # تابع کمک‌کننده نرمال‌سازی Min-Max بین 0 تا 1
    def normalize(series, invert=False):
        min_val = series.min()
        max_val = series.max()
        if max_val == min_val:
            return pd.Series(0.5, index=series.index)
        norm = (series - min_val) / (max_val - min_val)
        return 1.0 - norm if invert else norm

    if not df_normal.empty:
        # نرمال‌سازی سه بعد
        # ۱. حاشیه امنیت (هر چه منفی‌تر باشد بهتر است -> invert=True)
        norm_safety = normalize(df_normal['break_even_percent_scale'], invert=True)

        # ۲. بازدهی ماهانه
        norm_return = normalize(df_normal['monthly_return_%'], invert=False)

        # ۳. نقدشوندگی (حداقل حجم)
        norm_volume = normalize(df_normal['min_volume'], invert=False)

        # محاسبه امتیاز نهایی کامپوزیت با وزن‌های تعدیل‌شده
        df_normal['composite_score'] = round(
            (0.3 * norm_safety)
            + (0.6 * norm_return)
            + (0.1 * norm_volume), 4,)

    if not df_risk_free.empty:
        df_risk_free['composite_score'] = 1.0

    return pd.concat([df_normal, df_risk_free]).sort_index()


def run_bull_call_spread_strategy(df_options, max_break_even_percent, min_monthly_return, min_rr_ratio):
    """اجرای استراتژی و رتبه‌بندی نهایی بر اساس امتیاز کامپوزیت."""
    results_fee = []

    for underlying_symbol, group in df_options.groupby('UnderlyingTicker'):
        market = get_symbol_market(underlying_symbol)
        kind = get_symbol_kind(underlying_symbol)

        opt_buy_commission = get_commission_rate(market, 'option', True)
        opt_sell_commission = get_commission_rate(market, 'option', False)
        exercise_fee_rate = get_exercise_fee_rate(market, kind)

        for days, sub_group in group.groupby('DaysToMaturity'):
            sub_group_sorted = sub_group.sort_values('StrikePrice')
            options_list = sub_group_sorted.to_dict('records')
            n = len(options_list)

            for i in range(n):
                for j in range(i + 1, n):
                    long_leg = options_list[i]
                    short_leg = options_list[j]

                    stock_price = long_leg['UnderlyingPrice']
                    contract_size = long_leg['ContractSize']

                    long_ask = long_leg.get('AskPrice', 0)
                    short_bid = short_leg.get('BidPrice', 0)

                    if (pd.isna(long_ask)
                        or long_ask <= 0
                        or pd.isna(short_bid)
                        or short_bid <= 0):
                        continue

                    res = bull_call_spread_analysis(
                        stock_price=stock_price,
                        long_strike=long_leg['StrikePrice'],
                        long_ask_premium=long_ask,
                        short_strike=short_leg['StrikePrice'],
                        short_bid_premium=short_bid,
                        contract_size=contract_size,
                        opt_buy_commission=opt_buy_commission,
                        opt_sell_commission=opt_sell_commission,
                        exercise_fee_rate=exercise_fee_rate,
                        exercise_tax_rate=EXERCISE_TAX_RATE,
                        days=days,)

                    if res['status'] == 'DISCARD':
                        continue

                    if (res['status'] != 'RISK_FREE'
                        and res['risk_reward_ratio'] < min_rr_ratio):
                        continue

                    results_fee.append({
                        'underlying': underlying_symbol,
                        'stock_price': round(stock_price, 0),
                        'long_option_symbol': long_leg['Ticker'],
                        'long_strike': long_leg['StrikePrice'],
                        'long_ask_premium': round(long_ask, 0),
                        'short_option_symbol': short_leg['Ticker'],
                        'short_strike': short_leg['StrikePrice'],
                        'short_bid_premium': round(short_bid, 0),
                        'capital_at_risk': res['capital_at_risk'],
                        'max_net_profit': res['max_net_profit'],
                        'max_profit_percent': res['max_profit_percent'],
                        'monthly_return_%': res['monthly_return'],
                        'break_even_price': res['break_even_price'],
                        'break_even_percent': res['break_even_percent'],
                        'break_even_percent_scale': res['break_even_percent_scale'],
                        'risk_reward_ratio': res['risk_reward_ratio'],
                        'days_to_maturity': days,
                        'long_volume': int(long_leg.get('Volume', 0)),
                        'short_volume': int(short_leg.get('Volume', 0)),
                    })

    if not results_fee:
        return pd.DataFrame()

    result_df = pd.DataFrame(results_fee)

    # فیلتر سقف درصد رشد تا سربه‌سر
    result_df_filtered = result_df[
        result_df['break_even_percent_scale'] <= max_break_even_percent].copy()
    result_df_filtered = result_df_filtered[
        result_df_filtered['monthly_return_%'] >= min_monthly_return].copy()


    if result_df_filtered.empty:
        return result_df_filtered

    # محاسبه امتیاز ترکیبی (Composite Score)
    result_df_filtered = calculate_composite_score(result_df_filtered)

    # مرتب‌سازی نزولی بر اساس Composite Score
    result_df_filtered = result_df_filtered.sort_values(
        by=['break_even_percent_scale', 'monthly_return_%'], ascending=[True, False]).reset_index(drop=True)

    # چیدمان مرتب ستون‌ها
    column_order = [
        'underlying',
        'composite_score',
        'stock_price',
        'long_option_symbol',
        'long_strike',
        'long_ask_premium',
        'short_option_symbol',
        'short_strike',
        'short_bid_premium',
        'capital_at_risk',
        'max_net_profit',
        'max_profit_percent',
        'monthly_return_%',
        'break_even_price',
        'break_even_percent',
        'break_even_percent_scale',
        'risk_reward_ratio',
        'days_to_maturity',
        'long_volume',
        'short_volume',
    ]

    result_df_filtered = result_df_filtered[column_order]

    result_df_filtered['break_even_percent'] = result_df_filtered[
        'break_even_percent'
    ].replace(RISK_FREE_BREAK_EVEN_SENTINEL, 'Risk Free')
    result_df_filtered['break_even_percent_scale'] = result_df_filtered[
        'break_even_percent_scale'
    ].replace(RISK_FREE_BREAK_EVEN_SENTINEL, 'Risk Free')
    result_df_filtered['monthly_return_%'] = result_df_filtered[
        'monthly_return_%'
    ].replace(RISK_FREE_RETURN_SENTINEL, 'Infinite')

    return result_df_filtered


def save_results_to_excel(result_df, filename="result_bull_call_spread.xlsx"):
    """ذخیره نتایج خروجی در فایل اکسل با فرمت‌بندی استاندارد."""
    header_font = Font(name='Segoe UI', size=11, bold=True, color='FFFFFF')
    header_fill = PatternFill(
        start_color='203764', end_color='203764', fill_type='solid')
    alignment = Alignment(
        horizontal='center', vertical='center', wrap_text=True)
    body_font = Font(name='Segoe UI', size=10)
    gray_font = Font(color='808080', italic=True, name='Segoe UI', size=10)

    rename_dict = {
        'underlying': 'نماد پایه',
        'composite_score': 'امتیاز جامع انتخاب\n(Composite Score)',
        'stock_price': 'قیمت سهم',
        'long_option_symbol': 'نماد خرید (Long Call)',
        'long_strike': 'قیمت اعمال خرید',
        'long_ask_premium': 'پریمیوم خرید (Ask)',
        'short_option_symbol': 'نماد فروش (Short Call)',
        'short_strike': 'قیمت اعمال فروش',
        'short_bid_premium': 'پریمیوم فروش (Bid)',
        'capital_at_risk': 'سرمایه درگیر (حداکثر زیان)',
        'max_net_profit': 'حداکثر سود خالص',
        'max_profit_percent': 'درصد حداکثر بازدهی',
        'monthly_return_%': 'درصد سود ماهانه',
        'break_even_price': 'قیمت سربه‌سر',
        'break_even_percent': 'درصد رشد تا سربه‌سر',
        'break_even_percent_scale': 'مقیاس درصد رشد تا سربه‌سر\n(تعدیل‌شده با زمان)',
        'spread_area_score': 'امتیاز مساحت سود اسکیل‌شده\n(Spread Area Score)',
        'risk_reward_ratio': 'نسبت سود به زیان (R/R)',
        'days_to_maturity': 'روز تا سررسید',
        'long_volume': 'حجم ساقه خرید',
        'short_volume': 'حجم ساقه فروش',
    }

    result_df_renamed = result_df.rename(columns=rename_dict)
    filepath = Path(__file__).parent / filename

    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        result_df_renamed.to_excel(
            writer, sheet_name='bull_call_spread', index=False)
        worksheet = writer.sheets['bull_call_spread']

        for col_idx in range(1, len(result_df_renamed.columns) + 1):
            cell = worksheet.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = alignment

        for row_idx in range(2, len(result_df_renamed) + 2):
            for col_idx in range(1, len(result_df_renamed.columns) + 1):
                cell = worksheet.cell(row=row_idx, column=col_idx)
                val = cell.value

                if val is None or pd.isna(val) or val == "":
                    cell.value = "-"
                    cell.font = gray_font
                else:
                    cell.font = body_font
                cell.alignment = alignment

        worksheet.auto_filter.ref = (
            f"A1:{get_column_letter(len(result_df_renamed.columns))}{len(result_df_renamed) + 1}")
        worksheet.freeze_panes = 'A2'

        for col in worksheet.columns:
            max_length = 0
            column = col[0].column_letter

            for cell in col:
                if cell.value:
                    text = str(cell.value)
                    if '\n' in text:
                        lines = text.split('\n')
                        line_length = max(len(line) for line in lines)
                    else:
                        line_length = len(text)

                    if line_length > max_length:
                        max_length = line_length

            adjusted_width = min(max_length + 5, 50)
            worksheet.column_dimensions[column].width = adjusted_width

    print(f"Results successfully saved to {filename}")
    return filename


def main():
    """تابع اصلی جهت اجرای استراتژی."""
    try:
        filtered_data = load_and_filter_data()

        if filtered_data.empty:
            print("No market data found.")
            return

        results = run_bull_call_spread_strategy(
            filtered_data, max_break_even_percent=-10, min_monthly_return=5, min_rr_ratio=0.03)

        if results.empty:
            print("No valid strategy setups found after filtering.")
            return

        save_results_to_excel(results)

    except Exception as e:
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()