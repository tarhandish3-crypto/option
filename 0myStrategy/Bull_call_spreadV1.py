# bull_call_spread_strategy.py
# -*- coding: utf-8 -*-

import sys
from pathlib import Path

# تنظیم مسیر پروژه
current_file_path = Path(__file__).resolve()
current_dir = current_file_path.parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

import math
from datetime import datetime
from config import (
    get_commission_rate,
    get_exercise_fee_rate,
    get_symbol_kind,
    get_symbol_market,
)
from data.cleaner import DataCleaner
from data.downloader import MarketDownloader
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
import pandas as pd


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
    days,
):
    """محاسبه سود/زیان استراتژی Bull Call Spread با احتساب دقیق کارمزدها."""

    # ========== ۱. محاسبه هزینه و پریمیوم ورود ==========
    long_premium_total = round(long_ask_premium * contract_size, 0)
    long_entry_fee = round(long_premium_total * opt_buy_commission, 0)

    short_premium_total = round(short_bid_premium * contract_size, 0)
    short_entry_fee = -round(short_premium_total * opt_sell_commission, 0)

    # بدهی خالص اولیه (Net Debit)
    net_debit = (long_premium_total + long_entry_fee) - (
        short_premium_total + short_entry_fee
    )

    # ========== ۲. کارمزدهای احتمال اعمال ==========
    long_exercise_fee = round(
        (long_strike * contract_size) * exercise_fee_rate, 0
    )
    short_exercise_fee = round(
        (short_strike * contract_size) * exercise_fee_rate, 0
    )

    # ========== ۳. تحلیل کف و سقف سود/زیان ==========
    min_profit_or_loss = -net_debit

    max_payoff = (short_strike - long_strike) * contract_size
    max_net_profit = (
        max_payoff - net_debit - long_exercise_fee - short_exercise_fee
    )

    # حالت ۱: کاملاً زیان‌ده (سقف هم منفی است) -> حذف
    if max_net_profit <= 0:
        return {'status': 'DISCARD'}

    capital_at_risk = max(1.0, net_debit)

    # حالت ۳: کاملاً در سود (حداقل سود در کف هم مثبت است - آربیتراژ)
    if min_profit_or_loss >= 0:
        return {
            'status': 'RISK_FREE',
            'capital_at_risk': 0,
            'max_net_profit': max_net_profit,
            'max_profit_percent': 'آربیتراژ (سود تضمینی)',
            'monthly_return': 'بی‌نهایت',
            'break_even_price': 'بدون نیاز (همیشه سود)',
            'break_even_percent': -999.0,
            'break_even_percent_scale': -999.0,
            'risk_reward_ratio': 'بی‌نهایت',
        }

    # حالت ۲: دارای نقطه سربه‌سر
    break_even_price = round(
        long_strike + ((net_debit + long_exercise_fee) / contract_size), 0
    )

    if stock_price > 0:
        break_even_percent = round(
            ((break_even_price - stock_price) / stock_price) * 100, 2
        )
    else:
        break_even_percent = 0.0

    # ========== ۴. تعدیل درصد سربه‌سر بر مبنای زمان (Time-Adjusted Scale) ==========
    if days < 1:
        days_safe = 1.0
    else:
        days_safe = float(days)

    # فرمول مقیاس‌پذیری بر اساس جذر زمان (نسبت به ۳۰ روز)
    time_factor = math.sqrt(days_safe / 30.0)
    if time_factor > 0:
        break_even_percent_scale = round(break_even_percent / time_factor, 2)
    else:
        break_even_percent_scale = break_even_percent

    max_profit_percent = round((max_net_profit / capital_at_risk) * 100, 2)
    monthly_return = round(max_profit_percent * (30 / days_safe), 2)
    risk_reward_ratio = round(max_net_profit / capital_at_risk, 2)

    return {
        'status': 'VALID',
        'capital_at_risk': capital_at_risk,
        'max_net_profit': max_net_profit,
        'max_profit_percent': max_profit_percent,
        'monthly_return': monthly_return,
        'break_even_price': break_even_price,
        'break_even_percent': break_even_percent,
        'break_even_percent_scale': break_even_percent_scale,
        'risk_reward_ratio': risk_reward_ratio,
    }


def load_and_filter_data():
    """بارگذاری داده‌ها از TSE و فیلتر کردن اختیارهای خرید (CALL)"""
    df_raw = MarketDownloader.from_tsetmc_direct()
    df_cleaned = DataCleaner.clean(df_raw)
    df_final = DataCleaner.add_derived_columns(df_cleaned)

    filter_option = df_final[
        (df_final['DaysToMaturity'] > 2.0)
        & (df_final['Type'].apply(lambda x: x.name == 'CALL'))
    ].copy()

    EXCLUDED_UNDERLYING = ['اهرم']
    EXCLUDED_NAME_PATTERN = ['1405/04', '1405-04']
    exclude_mask = (
        filter_option['UnderlyingTicker'].isin(EXCLUDED_UNDERLYING)
    ) & (
        filter_option['Name'].str.contains(
            '|'.join(EXCLUDED_NAME_PATTERN), na=False
        )
    )
    filter_option = filter_option[~exclude_mask].copy()

    return filter_option


def run_bull_call_spread_strategy(
    df_options, max_break_even_percent=15, min_rr_ratio=0.03
):
    """ترکیب دو ساقه خرید و فروش و مرتب‌سازی بر اساس درصد سربه‌سر تعدیل‌شده با زمان."""
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

                    if (
                        pd.isna(long_ask)
                        or long_ask <= 0
                        or pd.isna(short_bid)
                        or short_bid <= 0
                    ):
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
                        days=days,
                    )

                    if res['status'] == 'DISCARD':
                        continue

                    # فیلتر موقعیت‌های بسیار ضعیف از نظر R/R (قابل تنظیم)
                    if (
                        res['status'] != 'RISK_FREE'
                        and res['risk_reward_ratio'] < min_rr_ratio
                    ):
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
                        'break_even_percent_scale': res[
                            'break_even_percent_scale'
                        ],
                        'risk_reward_ratio': res['risk_reward_ratio'],
                        'days_to_maturity': days,
                        'long_volume': int(long_leg.get('Volume', 0)),
                        'short_volume': int(short_leg.get('Volume', 0)),
                    })

    column_order = [
        'underlying',
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

    result_df = pd.DataFrame(results_fee, columns=column_order)

    if result_df.empty:
        return result_df

    # ۱. فیلتر حداکثر درصد رشد تا سربه‌سر
    result_df_filtered = result_df[
        result_df['break_even_percent'] <= max_break_even_percent
    ].copy()

    # ۲. مرتب‌سازی (Sort) اصلی بر اساس «مقیاس تعدیل‌شده با زمان» (break_even_percent_scale)
    # با این سورت، موقعیت‌های نزدیک‌تر از نظر زمانی که حاشیه امن بالاتری دارند در بالای جدول قرار می‌گیرند.
    result_df_filtered = result_df_filtered.sort_values(
        by=['break_even_percent_scale', 'risk_reward_ratio'],
        ascending=[True, False],
    ).reset_index(drop=True)

    # ۳. قفل کردن ترتیب ستون‌ها
    result_df_filtered = result_df_filtered[column_order]

    # ۴. جایگزینی مقادیر خاص جهت نمایش زیبا در اکسل
    result_df_filtered['break_even_percent'] = result_df_filtered[
        'break_even_percent'
    ].replace(-999.0, 'بدون نیاز')
    result_df_filtered['break_even_percent_scale'] = result_df_filtered[
        'break_even_percent_scale'
    ].replace(-999.0, 'بدون نیاز')

    return result_df_filtered


def save_results_to_excel(
    result_df, filename="result_bull_call_spread.xlsx"
):
    """ذخیره نتایج در اکسل با حفظ کامل ترتیب و فرمت‌بندی استاندارد."""
    header_font = Font(name='Segoe UI', size=11, bold=True, color='FFFFFF')
    header_fill = PatternFill(
        start_color='203764', end_color='203764', fill_type='solid'
    )
    alignment = Alignment(
        horizontal='center', vertical='center', wrap_text=True
    )
    body_font = Font(name='Segoe UI', size=10)
    gray_font = Font(color='808080', italic=True, name='Segoe UI', size=10)

    rename_dict = {
        'underlying': 'نماد پایه',
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
        'risk_reward_ratio': 'نسبت سود به زیان (R/R)',
        'days_to_maturity': 'روز تا سررسید',
        'long_volume': 'حجم ساقه خرید',
        'short_volume': 'حجم ساقه فروش',
    }

    result_df_renamed = result_df.rename(columns=rename_dict)
    filepath = Path(__file__).parent / filename

    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        result_df_renamed.to_excel(
            writer, sheet_name='bull_call_spread', index=False
        )
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
            f"A1:{get_column_letter(len(result_df_renamed.columns))}{len(result_df_renamed) + 1}"
        )
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

    print(f"نتایج با موفقیت در فایل {filename} ذخیره شد.")
    return filename


def main():
    """تابع اصلی اجرای استراتژی Bull Call Spread"""
    try:
        filtered_data = load_and_filter_data()

        if filtered_data.empty:
            return

        # فیلترها: max_break_even_percent=15 و min_rr_ratio=0.03 (قابل تغییر به مقدار دلخواه)
        results = run_bull_call_spread_strategy(
            filtered_data, max_break_even_percent=15, min_rr_ratio=0.03
        )

        if results.empty:
            return

        save_results_to_excel(results)

    except Exception as e:
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()