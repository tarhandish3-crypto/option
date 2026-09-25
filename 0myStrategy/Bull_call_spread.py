# bull_call_spread_strategy.py
# -*- coding: utf-8 -*-
"""
استراتژی Bull Call Spread با چارچوب تصمیم‌گیری چندلایه.

معماری این ماژول:

    1) بارگذاری داده بازار (Download + Clean + Derive)
    2) بارگذاری پروفایل نوسان از Historical_Volatility.xlsx
    3) Merge بر اساس UnderlyingTicker
    4) سه رژیم موازی (RISK_FREE / NEAR_EXPIRY / NORMAL)
    5) فیلتر سخت (سود، حاشیه، M_risk واقعی)
    6) امتیازدهی ترکیبی:
           Score = R^w_R × M^w_M × Φ(M_risk)
                 × VolQualityFactor
                 × ImbalanceFactor
    7) رتبه‌بندی و تصمیم
    8) ذخیره در اکسل

نکات کلیدی:
    - M_risk با استفاده از HV_60 واقعی هر نماد محاسبه می‌شود.
    - Z-Score = M_30 / (HV_60 × sqrt(T/365)).
    - ضریب عدم‌تعادل: ImbalanceFactor = min(1, (M/R)^0.5)
      که موقعیت‌های نامتعادل (M << R) را جریمه می‌کند.
    - ضریب کیفیت نوسان: (VolQuality/10)^0.3
    - RSI به‌عنوان ضریب امتیازدهی حذف شده است چون در بازار ایران
      قابل اعتماد نیست. اگر نیاز به فیلتر RSI دارید، در ماژول
      volatility_calculate.py اعمال کنید.
"""

import sys
from pathlib import Path

current_file_path = Path(__file__).resolve()
current_dir = current_file_path.parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

import math

import numpy as np
import pandas as pd
from scipy.stats import norm

from config import (
    EXERCISE_TAX_RATE,
    get_commission_rate,
    get_exercise_fee_rate,
    get_symbol_kind,
    get_symbol_market,
)
from data.cleaner import DataCleaner
from data.downloader import MarketDownloader
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


# ============================================================
# ثابت‌های Sentinel
# ============================================================
RISK_FREE_BREAK_EVEN_SENTINEL = -999.0
RISK_FREE_RETURN_SENTINEL = 999999.0
RISK_FREE_SCORE_SENTINEL = 999999.0
NEAR_EXPIRY_SCORE_BASE = RISK_FREE_SCORE_SENTINEL - 111111.0
NEAR_EXPIRY_PROB_SURVIVAL = 0.95


# ============================================================
# پارامترهای پیش‌فرض
# ============================================================

# --- رژیم عادی (NORMAL) ---
DEFAULT_MIN_MONTHLY_RETURN = 6.0
DEFAULT_MIN_MARGIN_FLOOR = 15.0
DEFAULT_MARGIN_PERCENTILE = 60
DEFAULT_MIN_RR_RATIO = 0.1
DEFAULT_W_R = 0.4
DEFAULT_W_M = 0.6
DEFAULT_SIGMA_FALLBACK = 0.30
DEFAULT_MIN_M_RISK = 2.0
DEFAULT_DECISION_THRESHOLD = 3.0

# --- ضریب کیفیت نوسان ---
DEFAULT_VOL_QUALITY_POWER = 0.3

# --- ضریب عدم‌تعادل (Anti-Imbalance) ---
DEFAULT_IMBALANCE_POWER = 0.5

# --- رژیم نزدیک سررسید ---
NEAR_EXPIRY_THRESHOLD_DAYS = 1.0
NEAR_EXPIRY_MIN_RETURN = 1.5
NEAR_EXPIRY_MIN_MARGIN = 2.0
NEAR_EXPIRY_W_R = 0.6
NEAR_EXPIRY_W_M = 0.4
T_DISPLAY_EPSILON = 0.02

# --- مسیر فایل نوسان ---
VOLATILITY_FILE_NAME = "Historical_Volatility.xlsx"


# ============================================================
# لایه ۱: محاسبه پارامترهای هر اسپرد
# ============================================================
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
    days,
):
    """
    محاسبه پارامترهای استراتژی Bull Call Spread با کارمزد و مالیات.

    خروجی شامل:
        - capital_at_risk, max_net_profit, max_profit_percent
        - monthly_return (R_30 خطی)
        - break_even_price, break_even_percent, break_even_percent_scale
        - risk_reward_ratio
        - is_near_expiry, raw_return_percent, raw_margin_percent
    """
    # ۱. پریمیوم و کارمزد ورود
    long_premium_total = round(long_ask_premium * contract_size, 0)
    long_entry_fee = round(long_premium_total * opt_buy_commission, 0)

    short_premium_total = round(short_bid_premium * contract_size, 0)
    short_entry_fee = -round(short_premium_total * opt_sell_commission, 0)

    net_debit = (long_premium_total + long_entry_fee) - (
        short_premium_total + short_entry_fee
    )

    # ۲. کارمزدهای اعمال + مالیات انتقال
    # توجه: کارمزد اعمال در هر دو سمت پرداخت می‌شود، اما مالیات انتقال
    # فقط در سمتی که سهم تحویل داده می‌شود (اینجا: Short).
    long_exercise_fee = round((long_strike * contract_size) * exercise_fee_rate, 0)
    short_exercise_fee = round((short_strike * contract_size) * exercise_fee_rate, 0)
    short_transfer_tax = round((short_strike * contract_size) * exercise_tax_rate, 0)

    short_total_exercise_cost = short_exercise_fee + short_transfer_tax
    total_exercise_costs = long_exercise_fee + short_total_exercise_cost

    # ۳. تحلیل سود و زیان
    min_profit_or_loss = -net_debit
    max_payoff = (short_strike - long_strike) * contract_size
    max_net_profit = max_payoff - net_debit - total_exercise_costs

    if max_net_profit <= 0 or net_debit <= 0:
        return {'status': 'DISCARD'}

    capital_at_risk = max(1.0, net_debit)
    days_raw = float(days)
    is_near_expiry = days_raw <= NEAR_EXPIRY_THRESHOLD_DAYS

    # حالت آربیتراژ (بدون ریسک)
    if min_profit_or_loss >= 0:
        return {
            'status': 'RISK_FREE',
            'is_near_expiry': False,
            'capital_at_risk': 0,
            'max_net_profit': max_net_profit,
            'max_profit_percent': 'Arbitrage',
            'monthly_return': RISK_FREE_RETURN_SENTINEL,
            'break_even_price': 'Risk Free',
            'break_even_percent': RISK_FREE_BREAK_EVEN_SENTINEL,
            'break_even_percent_scale': RISK_FREE_BREAK_EVEN_SENTINEL,
            'risk_reward_ratio': 'Infinite',
            'raw_return_percent': None,
            'raw_margin_percent': None,
        }

    # ۴. سربه‌سر
    break_even_price = long_strike + ((net_debit + long_exercise_fee) / contract_size)

    if stock_price > 0:
        break_even_percent = round(
            ((break_even_price - stock_price) / stock_price) * 100, 2
        )
    else:
        break_even_percent = 0.0

    # مقادیر خام (بدون ماهانه‌سازی)
    max_profit_percent = round((max_net_profit / capital_at_risk) * 100, 2)
    raw_return_percent = max_profit_percent
    raw_margin_percent = -break_even_percent
    risk_reward_ratio = round(max_net_profit / capital_at_risk, 2)

    # ۵. مقیاس‌بندی زمانی
    days_safe_for_display = max(T_DISPLAY_EPSILON, days_raw)
    time_factor = math.sqrt(days_safe_for_display / 30.0)

    break_even_percent_scale = round(break_even_percent / time_factor, 2)
    monthly_return = round(max_profit_percent * (30 / days_safe_for_display), 2)

    return {
        'status': 'VALID',
        'is_near_expiry': is_near_expiry,
        'capital_at_risk': capital_at_risk,
        'max_net_profit': max_net_profit,
        'max_profit_percent': max_profit_percent,
        'monthly_return': monthly_return,
        'break_even_price': round(break_even_price, 0),
        'break_even_percent': break_even_percent,
        'break_even_percent_scale': break_even_percent_scale,
        'risk_reward_ratio': risk_reward_ratio,
        'raw_return_percent': raw_return_percent,
        'raw_margin_percent': raw_margin_percent,
    }


# ============================================================
# لایه ۰: بارگذاری داده بازار
# ============================================================
def load_and_filter_data():
    """بارگذاری داده‌های بازار و فیلتر اولیه اختیارهای خرید (CALL)."""
    df_raw = MarketDownloader.from_tsetmc_direct()
    df_cleaned = DataCleaner.clean(df_raw)
    df_final = DataCleaner.add_derived_columns(df_cleaned)

    filter_option = df_final[
        (df_final['DaysToMaturity'] >= 0.0)
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


# ============================================================
# لایه ۰.۵: بارگذاری پروفایل نوسان
# ============================================================
def load_volatility_profile():
    """
    بارگذاری پروفایل نوسان از Historical_Volatility.xlsx.

    فقط ستون‌های موردنیاز برای امتیازدهی بارگذاری می‌شوند:
        - HV_60 (برای محاسبه Z-Score)
        - VolatilityQualityScore (برای ضریب کیفیت)
    """
    filepath = current_dir / VOLATILITY_FILE_NAME

    if not filepath.exists():
        print(f"WARNING: Volatility file not found: {filepath}")
        return pd.DataFrame()

    try:
        df_vol = pd.read_excel(filepath)
        required_cols = ['UnderlyingTicker', 'HV_60']
        missing = [c for c in required_cols if c not in df_vol.columns]
        if missing:
            print(f"WARNING: Missing columns: {missing}")
            return pd.DataFrame()

        df_vol = df_vol.rename(columns={'UnderlyingTicker': 'underlying'})

        keep_cols = ['underlying', 'HV_60']
        if 'VolatilityQualityScore' in df_vol.columns:
            keep_cols.append('VolatilityQualityScore')

        return df_vol[keep_cols].copy()

    except Exception as e:
        print(f"ERROR loading volatility file: {e}")
        return pd.DataFrame()


# ============================================================
# لایه ۱ (تکمیلی): افزودن M_30 و M_risk
# ============================================================
def add_margin30_column(df):
    """استخراج M_30 از break_even_percent_scale."""
    df = df.copy()
    risk_free_mask = df['break_even_percent_scale'] == RISK_FREE_BREAK_EVEN_SENTINEL
    df['margin30'] = -df['break_even_percent_scale'].astype(float)
    df.loc[risk_free_mask, 'margin30'] = np.inf
    df['is_risk_free'] = risk_free_mask
    return df


def add_margin_risk_column(df):
    """
    محاسبه M_risk و Z_score با استفاده از HV_60 واقعی.

    فرمول:
        M_risk = (M_raw / 100) / (HV_60 × sqrt(T/365))
        Z_score = M_risk
    """
    df = df.copy()
    if 'margin30' not in df.columns:
        df = add_margin30_column(df)

    risk_free_mask = df['is_risk_free']
    raw_margin_fraction = df['raw_margin_percent'].astype(float) / 100.0

    if 'HV_60' in df.columns:
        sigma = df['HV_60'].fillna(DEFAULT_SIGMA_FALLBACK).clip(
            lower=0.05, upper=2.0
        )
    else:
        sigma = pd.Series(DEFAULT_SIGMA_FALLBACK, index=df.index)

    T = df['days_to_maturity'].astype(float).clip(lower=T_DISPLAY_EPSILON)
    df['M_risk'] = raw_margin_fraction / (sigma * np.sqrt(T / 365.0))
    df.loc[risk_free_mask, 'M_risk'] = np.inf
    df['Z_score'] = df['M_risk']

    return df


# ============================================================
# لایه ۲: فیلتر سخت‌گیرانه
# ============================================================
def apply_hard_constraints(
    df,
    min_monthly_return,
    min_margin_floor,
    margin_percentile,
    min_m_risk,
    near_expiry_min_return=NEAR_EXPIRY_MIN_RETURN,
    near_expiry_min_margin=NEAR_EXPIRY_MIN_MARGIN,
):
    """
    فیلتر سخت‌گیرانه:

        RISK_FREE    -> بدون فیلتر
        NEAR_EXPIRY  -> فیلتر ساده روی مقادیر خام
        NORMAL       -> سه شرط:
                            1) R_30 >= min_monthly_return
                            2) M_30 >= max(min_margin_floor, Percentile)
                            3) M_risk >= min_m_risk (Z-Score)

    نکته: فیلترهای نوسان (HV, RSI, Trend) در ماژول
    volatility_calculate.py اعمال می‌شوند.
    """
    if df.empty:
        return df

    df = add_margin30_column(df)

    risk_free_mask = df['is_risk_free']
    near_expiry_mask = df['is_near_expiry'].fillna(False) & (~risk_free_mask)
    normal_mask = ~(risk_free_mask | near_expiry_mask)

    df_rf = df[risk_free_mask].copy()
    df_near = df[near_expiry_mask].copy()
    df_normal = df[normal_mask].copy()

    # --- NEAR_EXPIRY ---
    if not df_near.empty:
        df_near = df_near[
            (df_near['raw_return_percent'] >= near_expiry_min_return)
            & (df_near['raw_margin_percent'] >= near_expiry_min_margin)
        ].copy()

    # --- NORMAL ---
    if not df_normal.empty:
        # شرط ۱: حداقل بازده
        df_normal = df_normal[
            df_normal['monthly_return_%'] >= min_monthly_return
        ].copy()

        if not df_normal.empty:
            # شرط ۲: حداقل حاشیه (آستانه پویا)
            dynamic_threshold = np.percentile(
                df_normal['margin30'], margin_percentile
            )
            effective_margin_min = max(min_margin_floor, dynamic_threshold)

            df_normal = df_normal[
                df_normal['margin30'] >= effective_margin_min
            ].copy()

        # شرط ۳: M_risk (Z-Score)
        if not df_normal.empty:
            df_normal = add_margin_risk_column(df_normal)
            df_normal = df_normal[df_normal['M_risk'] >= min_m_risk].copy()

    return pd.concat([df_rf, df_near, df_normal])


# ============================================================
# لایه ۳: امتیازدهی (بدون RSI)
# ============================================================
def calculate_composite_score(
    df,
    w_r=DEFAULT_W_R,
    w_m=DEFAULT_W_M,
    vol_quality_power=DEFAULT_VOL_QUALITY_POWER,
    imbalance_power=DEFAULT_IMBALANCE_POWER,
):
    """
    امتیازدهی نهایی با ضرایب ترکیبی:

        Score = R^w_R × M^w_M × Φ(M_risk)
              × VolQualityFactor
              × ImbalanceFactor

    که:
        ImbalanceFactor = min(1, (M/R)^imbalance_power)
        VolFactor       = (VolQuality/10)^vol_quality_power

    نکته: ضریب RSI حذف شده است چون در بازار ایران قابل اعتماد نیست.
    اگر می‌خواهید RSI را فیلتر کنید، در ماژول volatility_calculate.py
    این کار را انجام دهید.
    """
    if df.empty:
        return df

    df = df.copy()
    if 'margin30' not in df.columns:
        df = add_margin30_column(df)

    risk_free_mask = df['is_risk_free']
    near_expiry_mask = df['is_near_expiry'].fillna(False) & (~risk_free_mask)
    normal_mask = ~(risk_free_mask | near_expiry_mask)

    df_rf = df[risk_free_mask].copy()
    df_near = df[near_expiry_mask].copy()
    df_normal = df[normal_mask].copy()

    # ===== RISK_FREE =====
    if not df_rf.empty:
        df_rf['prob_survival'] = 1.0
        df_rf['M_risk'] = np.inf
        df_rf['score_cobb_douglas'] = RISK_FREE_SCORE_SENTINEL
        df_rf['score_crra'] = RISK_FREE_SCORE_SENTINEL
        df_rf['vol_quality_factor'] = 1.0
        df_rf['imbalance_factor'] = 1.0
        df_rf['composite_score'] = RISK_FREE_SCORE_SENTINEL

    # ===== NEAR_EXPIRY =====
    if not df_near.empty:
        raw_R = df_near['raw_return_percent'].astype(float)
        raw_M = df_near['raw_margin_percent'].astype(float)

        base_near = (
            NEAR_EXPIRY_SCORE_BASE
            + NEAR_EXPIRY_W_R * raw_R
            + NEAR_EXPIRY_W_M * raw_M
        ).round(4)

        df_near['prob_survival'] = NEAR_EXPIRY_PROB_SURVIVAL
        df_near['M_risk'] = np.inf
        df_near['score_cobb_douglas'] = base_near
        df_near['score_crra'] = base_near
        df_near['vol_quality_factor'] = 1.0
        df_near['imbalance_factor'] = 1.0
        df_near['composite_score'] = base_near

    # ===== NORMAL =====
    if not df_normal.empty:
        if 'M_risk' not in df_normal.columns:
            df_normal = add_margin_risk_column(df_normal)

        R30 = df_normal['monthly_return_%'].astype(float).clip(lower=0.0)
        M30 = df_normal['margin30'].astype(float).clip(lower=0.0)
        M_risk = df_normal['M_risk'].astype(float)

        prob_survival = norm.cdf(M_risk)
        df_normal['prob_survival'] = np.round(prob_survival, 4)

        # فرمول پایه: Cobb-Douglas
        score_cd = (R30 ** w_r) * (M30 ** w_m)
        df_normal['score_cobb_douglas'] = (score_cd * prob_survival).round(4)

        # فرمول CRRA (برای مقایسه)
        score_crra = np.sqrt(R30 * M30) * prob_survival
        df_normal['score_crra'] = score_crra.round(4)

        # ضریب کیفیت نوسان
        if 'VolatilityQualityScore' in df_normal.columns:
            vq = df_normal['VolatilityQualityScore'].fillna(10.0).clip(
                lower=0.0, upper=10.0
            )
            vol_factor = (vq / 10.0) ** vol_quality_power
        else:
            vol_factor = pd.Series(1.0, index=df_normal.index)
        df_normal['vol_quality_factor'] = np.round(vol_factor, 4)

        # ضریب عدم‌تعادل (Anti-Imbalance)
        ratio = (M30 / R30.replace(0, np.nan)).replace(
            [np.inf, -np.inf], np.nan
        ).fillna(1.0)
        imbalance_factor = np.minimum(1.0, ratio ** imbalance_power)
        df_normal['imbalance_factor'] = np.round(imbalance_factor, 4)

        # امتیاز نهایی
        df_normal['composite_score'] = (
            score_cd * prob_survival
            * vol_factor
            * imbalance_factor
        ).round(4)

    return pd.concat([df_rf, df_near, df_normal])


# ============================================================
# لایه ۴ و ۵: رتبه‌بندی و تصمیم
# ============================================================
def run_bull_call_spread_strategy(
    df_options,
    df_vol=None,
    min_monthly_return=DEFAULT_MIN_MONTHLY_RETURN,
    min_margin_floor=DEFAULT_MIN_MARGIN_FLOOR,
    margin_percentile=DEFAULT_MARGIN_PERCENTILE,
    min_rr_ratio=DEFAULT_MIN_RR_RATIO,
    w_r=DEFAULT_W_R,
    w_m=DEFAULT_W_M,
    vol_quality_power=DEFAULT_VOL_QUALITY_POWER,
    imbalance_power=DEFAULT_IMBALANCE_POWER,
    min_m_risk=DEFAULT_MIN_M_RISK,
    decision_threshold=DEFAULT_DECISION_THRESHOLD,
    near_expiry_min_return=NEAR_EXPIRY_MIN_RETURN,
    near_expiry_min_margin=NEAR_EXPIRY_MIN_MARGIN,
):
    """اجرای کامل استراتژی."""
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
                        exercise_tax_rate=EXERCISE_TAX_RATE,
                        days=days,
                    )

                    if res['status'] == 'DISCARD':
                        continue

                    if (
                        res['status'] != 'RISK_FREE'
                        and res['risk_reward_ratio'] < min_rr_ratio
                    ):
                        continue

                    results_fee.append({
                        'underlying': underlying_symbol,
                        'is_near_expiry': res['is_near_expiry'],
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
                        'raw_return_percent': res['raw_return_percent'],
                        'raw_margin_percent': res['raw_margin_percent'],
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

    # ===== Merge با نوسان =====
    if df_vol is not None and not df_vol.empty:
        result_df = pd.merge(result_df, df_vol, on='underlying', how='left')
    else:
        result_df['HV_60'] = np.nan
        result_df['VolatilityQualityScore'] = np.nan

    # ===== لایه ۲: فیلترینگ سخت =====
    result_df_filtered = apply_hard_constraints(
        result_df,
        min_monthly_return=min_monthly_return,
        min_margin_floor=min_margin_floor,
        margin_percentile=margin_percentile,
        min_m_risk=min_m_risk,
        near_expiry_min_return=near_expiry_min_return,
        near_expiry_min_margin=near_expiry_min_margin,
    )

    if result_df_filtered.empty:
        return result_df_filtered

    # ===== لایه ۳: امتیازدهی =====
    result_df_filtered = calculate_composite_score(
        result_df_filtered,
        w_r=w_r,
        w_m=w_m,
        vol_quality_power=vol_quality_power,
        imbalance_power=imbalance_power,
    )

    # ===== لایه ۴: رتبه‌بندی =====
    result_df_filtered = result_df_filtered.sort_values(
        by='composite_score', ascending=False
    ).reset_index(drop=True)

    # ===== لایه ۵: تصمیم =====
    always_enter_mask = (
        (result_df_filtered['composite_score'] == RISK_FREE_SCORE_SENTINEL)
        | (result_df_filtered['composite_score'] >= NEAR_EXPIRY_SCORE_BASE)
    )
    result_df_filtered['decision'] = np.where(
        always_enter_mask,
        'ENTER',
        np.where(
            result_df_filtered['composite_score'] > decision_threshold,
            'ENTER',
            'SKIP',
        ),
    )

    result_df_filtered['regime'] = np.select(
        [
            result_df_filtered['composite_score'] == RISK_FREE_SCORE_SENTINEL,
            result_df_filtered['composite_score'] >= NEAR_EXPIRY_SCORE_BASE,
        ],
        ['RISK_FREE', 'NEAR_EXPIRY'],
        default='NORMAL',
    )

    # چیدمان ستون‌ها
    column_order = [
        'underlying', 'regime', 'decision',
        'composite_score', 'score_cobb_douglas', 'score_crra',
        'prob_survival', 'M_risk', 'Z_score',
        'HV_60', 'VolatilityQualityScore',
        'vol_quality_factor', 'imbalance_factor',
        'stock_price', 'long_option_symbol', 'long_strike',
        'long_ask_premium', 'short_option_symbol', 'short_strike',
        'short_bid_premium', 'capital_at_risk', 'max_net_profit',
        'max_profit_percent', 'monthly_return_%', 'margin30',
        'raw_return_percent', 'raw_margin_percent',
        'break_even_price', 'break_even_percent',
        'break_even_percent_scale', 'risk_reward_ratio',
        'days_to_maturity', 'long_volume', 'short_volume',
    ]
    column_order = [c for c in column_order if c in result_df_filtered.columns]
    result_df_filtered = result_df_filtered[column_order]

    # جایگزینی Sentinelها
    result_df_filtered['break_even_percent'] = result_df_filtered[
        'break_even_percent'
    ].replace(RISK_FREE_BREAK_EVEN_SENTINEL, 'Risk Free')
    result_df_filtered['break_even_percent_scale'] = result_df_filtered[
        'break_even_percent_scale'
    ].replace(RISK_FREE_BREAK_EVEN_SENTINEL, 'Risk Free')
    result_df_filtered['monthly_return_%'] = result_df_filtered[
        'monthly_return_%'
    ].replace(RISK_FREE_RETURN_SENTINEL, 'Infinite')
    result_df_filtered['margin30'] = result_df_filtered['margin30'].apply(
        lambda v: 'Risk Free' if v == np.inf else round(v, 2)
    )
    result_df_filtered['M_risk'] = result_df_filtered['M_risk'].apply(
        lambda v: 'N/A' if (pd.isna(v) or v == np.inf) else round(v, 2)
    )
    result_df_filtered['composite_score'] = result_df_filtered[
        'composite_score'
    ].replace(RISK_FREE_SCORE_SENTINEL, 'Risk Free')

    return result_df_filtered


# ============================================================
# ذخیره خروجی در اکسل
# ============================================================
def save_results_to_excel(result_df, filename="result_bull_call_spread.xlsx"):
    """ذخیره نتایج خروجی در فایل اکسل."""
    header_font = Font(name='Segoe UI', size=11, bold=True, color='FFFFFF')
    header_fill = PatternFill(
        start_color='203764', end_color='203764', fill_type='solid'
    )
    alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    body_font = Font(name='Segoe UI', size=10)
    gray_font = Font(color='808080', italic=True, name='Segoe UI', size=10)

    rename_dict = {
        'underlying': 'نماد پایه',
        'regime': 'رژیم',
        'decision': 'تصمیم',
        'composite_score': 'امتیاز نهایی',
        'score_cobb_douglas': 'امتیاز Cobb-Douglas',
        'score_crra': 'امتیاز CRRA',
        'prob_survival': 'احتمال بقا',
        'M_risk': 'M_risk',
        'Z_score': 'Z-Score',
        'HV_60': 'نوسان ۶۰ روزه',
        'VolatilityQualityScore': 'کیفیت نوسان',
        'vol_quality_factor': 'ضریب کیفیت نوسان',
        'imbalance_factor': 'ضریب عدم‌تعادل',
        'stock_price': 'قیمت سهم',
        'long_option_symbol': 'نماد خرید',
        'long_strike': 'قیمت اعمال خرید',
        'long_ask_premium': 'پریمیوم خرید',
        'short_option_symbol': 'نماد فروش',
        'short_strike': 'قیمت اعمال فروش',
        'short_bid_premium': 'پریمیوم فروش',
        'capital_at_risk': 'سرمایه درگیر',
        'max_net_profit': 'حداکثر سود خالص',
        'max_profit_percent': 'درصد بازدهی',
        'monthly_return_%': 'سود ماهانه (R30)',
        'margin30': 'حاشیه ماهانه (M30)',
        'raw_return_percent': 'سود خام',
        'raw_margin_percent': 'حاشیه خام',
        'break_even_price': 'قیمت سربه‌سر',
        'break_even_percent': 'درصد رشد تا سربه‌سر',
        'break_even_percent_scale': 'مقیاس سربه‌سر',
        'risk_reward_ratio': 'R/R',
        'days_to_maturity': 'روز تا سررسید',
        'long_volume': 'حجم خرید',
        'short_volume': 'حجم فروش',
    }

    result_df_renamed = result_df.rename(columns=rename_dict)
    filepath = current_dir / filename

    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        result_df_renamed.to_excel(
            writer, sheet_name='bull_call_spread', index=False
        )
        worksheet = writer.sheets['bull_call_spread']

        # هدر
        for col_idx in range(1, len(result_df_renamed.columns) + 1):
            cell = worksheet.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = alignment

        # بدنه
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
            f"A1:{get_column_letter(len(result_df_renamed.columns))}"
            f"{len(result_df_renamed) + 1}"
        )
        worksheet.freeze_panes = 'A2'

        # تنظیم عرض ستون‌ها
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

    print(f"Results saved to: {filename}")


# ============================================================
# تابع اصلی
# ============================================================
def main():
    """تابع اصلی اجرای استراتژی Bull Call Spread."""
    try:
        print("=" * 65)
        print("Bull Call Spread Strategy")
        print("=" * 65)

        # ===== بارگذاری پروفایل نوسان =====
        df_vol = load_volatility_profile()
        if df_vol.empty:
            print("\nWARNING: Volatility profile not loaded.")
        else:
            print(f"\nVolatility profile: {len(df_vol)} symbols loaded")

        # ===== بارگذاری داده بازار =====
        filtered_data = load_and_filter_data()

        if filtered_data.empty:
            print("No market data found.")
            return

        print(f"Market data: {len(filtered_data)} CALL options loaded")

        # ===== اجرای استراتژی =====
        results = run_bull_call_spread_strategy(
            filtered_data,
            df_vol=df_vol,
            min_monthly_return=DEFAULT_MIN_MONTHLY_RETURN,
            min_margin_floor=DEFAULT_MIN_MARGIN_FLOOR,
            margin_percentile=DEFAULT_MARGIN_PERCENTILE,
            min_rr_ratio=DEFAULT_MIN_RR_RATIO,
            w_r=DEFAULT_W_R,
            w_m=DEFAULT_W_M,
            vol_quality_power=DEFAULT_VOL_QUALITY_POWER,
            imbalance_power=DEFAULT_IMBALANCE_POWER,
            min_m_risk=DEFAULT_MIN_M_RISK,
            decision_threshold=DEFAULT_DECISION_THRESHOLD,
            near_expiry_min_return=NEAR_EXPIRY_MIN_RETURN,
            near_expiry_min_margin=NEAR_EXPIRY_MIN_MARGIN,
        )

        if results.empty:
            print("No valid strategy setups found after filtering.")
            return

        print(f"\nResults: {len(results)} positions after filtering")

        # ===== ذخیره در اکسل =====
        save_results_to_excel(results)

        # ===== خلاصه تصمیم‌ها =====
        print("\n=== Decision Summary ===")
        for regime in ['RISK_FREE', 'NEAR_EXPIRY', 'NORMAL']:
            regime_df = results[results['regime'] == regime]
            if regime_df.empty:
                continue
            enter_count = (regime_df['decision'] == 'ENTER').sum()
            skip_count = (regime_df['decision'] == 'SKIP').sum()
            print(f"   [{regime}] ENTER: {enter_count}   SKIP: {skip_count}")

        entered = results[results['decision'] == 'ENTER']
        if not entered.empty:
            best = entered.iloc[0]
            print("\n=== Best Position ===")
            print(f"   Composite Score: {best['composite_score']}")

    except Exception as e:
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()