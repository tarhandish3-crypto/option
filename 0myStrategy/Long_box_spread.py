# 0myStrategy/Long_box_spread.py
# -*- coding: utf-8 -*-

import sys
from pathlib import Path

current_file_path = Path(__file__).resolve()
current_dir = current_file_path.parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

import json
import warnings
import logging

import pandas as pd
import requests

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


warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)


# ============================================================
# 🎯 بارگذاری پیکربندی Bale از user_settings.json
# ============================================================

def load_bale_config():
    settings_file = root_dir / "user_settings.json"

    try:
        with open(settings_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        active_profile = data.get('active_profile', '')
        profiles = data.get('profiles')

        if active_profile and active_profile in profiles:
            profile_data = profiles[active_profile]
            bale_config = profile_data.get('bale')

            return {
                "enabled": bool(bale_config.get('enabled', False)),
                "bot_token": str(bale_config.get('bot_token')),
                "chat_id": str(bale_config.get('chat_id')),
                "top_n": int(bale_config.get('top_n', 1)),
            }

    except json.JSONDecodeError as e:
        print(f"[BALE-CONFIG] ERROR: Invalid JSON: {e}")
        return {}
    except Exception as e:
        print(f"[BALE-CONFIG] ERROR: {e}")
        return {}


_BALE_CONFIG = load_bale_config()

BALE_ENABLED = _BALE_CONFIG.get('enabled', False)
BALE_BOT_TOKEN = _BALE_CONFIG.get('bot_token', '')
BALE_CHAT_ID = _BALE_CONFIG.get('chat_id', '')
BALE_TOP_N = _BALE_CONFIG.get('top_n', 1)

BALE_PARSE_MODE = "Markdown"
BALE_TIMEOUT = 10

BALE_DEDUP_ENABLED = True
BALE_SENT_HISTORY_FILE = current_dir / "sent_positions_long_box.json"


# ============================================================
# پارامترهای پیش‌فرض
# ============================================================
DEFAULT_MIN_MONTHLY_RETURN = -1.0
TRANSFER_TAX_RATE = 0.005   # 0.5% مالیات نقل و انتقال

T_DISPLAY_EPSILON = 0.02


# ==========================================================================================
# بخش ۰: Bale Notifier
# ==========================================================================================

def send_message_to_bale(message_text, bot_token=None, chat_id=None,
                          parse_mode=None, timeout=None):
    if not BALE_ENABLED:
        return None

    token = bot_token or BALE_BOT_TOKEN
    c_id = chat_id or BALE_CHAT_ID
    mode = parse_mode if parse_mode is not None else BALE_PARSE_MODE
    t_out = timeout or BALE_TIMEOUT

    if not token:
        print("[BALE] Bot token is not configured.")
        return None

    if not c_id:
        print("[BALE] Chat ID is not configured.")
        return None

    url = f'https://tapi.bale.ai/bot{token}/sendMessage'
    payload = {"chat_id": c_id, "text": message_text}
    if mode:
        payload["parse_mode"] = mode

    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers=headers,
            timeout=t_out
        )
        if response.status_code == 200:
            print(f"[BALE] Message sent successfully.")
            return response.json()
        else:
            print(f"[BALE] Failed: HTTP {response.status_code} - {response.text[:200]}")
            return None
    except requests.exceptions.Timeout:
        print("[BALE] Timeout occurred.")
        return None
    except Exception as e:
        print(f"[BALE] Error: {e}")
        return None


def _format_number(value, decimals=0):
    if value is None or pd.isna(value):
        return "N/A"
    try:
        if decimals > 0:
            return f"{float(value):,.{decimals}f}"
        return f"{int(round(float(value))):,}"
    except (ValueError, TypeError):
        return str(value)


def build_long_box_spread_message(row):
    """ساخت پیام Long Box Spread برای ارسال به بله."""
    underlying = row.get('underlying', 'N/A')
    stock_price = row.get('stock_price', 0)

    long_call_sym = row.get('long_call_symbol', 'N/A')
    long_call_premium = row.get('long_call_ask_premium', 0)

    short_call_sym = row.get('short_call_symbol', 'N/A')
    short_call_premium = row.get('short_call_bid_premium', 0)

    long_put_sym = row.get('long_put_symbol', 'N/A')
    long_put_premium = row.get('long_put_ask_premium', 0)

    short_put_sym = row.get('short_put_symbol', 'N/A')
    short_put_premium = row.get('short_put_bid_premium', 0)

    monthly_return = row.get('monthly_return_%', 0)

    message = (
        "🤖 *فرصت جدید استراتژی Long Box Spread*" + "\n"
        + "------------------------------------" + "\n"
        + f"📌 *نماد پایه:* `{underlying}`" + "\n"
        + f"📊 *قیمت سهم پایه:* `{_format_number(stock_price)}` ریال" + "\n"
        + "------------------------------------" + "\n"
        + f"🟢 *خرید CALL:* `{long_call_sym}` "
          f"(پریمیوم: {_format_number(long_call_premium)})" + "\n"
        + f"🔴 *فروش CALL:* `{short_call_sym}` "
          f"(پریمیوم: {_format_number(short_call_premium)})" + "\n"
        + f"🟢 *خرید PUT:* `{long_put_sym}` "
          f"(پریمیوم: {_format_number(long_put_premium)})" + "\n"
        + f"🔴 *فروش PUT:* `{short_put_sym}` "
          f"(پریمیوم: {_format_number(short_put_premium)})" + "\n"
        + "------------------------------------" + "\n"
        + f"📈 *بازدهی ماهانه:* `%{_format_number(monthly_return, 2)}`"
    )

    return message


# ==========================================================================================
# بخش ۰.۵: تاریخچه ارسال
# ==========================================================================================

def _load_sent_history():
    if not BALE_DEDUP_ENABLED:
        return {}
    if not BALE_SENT_HISTORY_FILE.exists():
        return {}
    try:
        with open(BALE_SENT_HISTORY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {}
        return data
    except Exception as e:
        print(f"[BALE-DEDUP] Error loading history: {e}")
        return {}


def _save_sent_history(history):
    if not BALE_DEDUP_ENABLED:
        return
    try:
        with open(BALE_SENT_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[BALE-DEDUP] Error saving history: {e}")


def _build_fingerprint(underlying, k_low, k_high, days, strategy):
    s = str(strategy).strip()
    u = str(underlying).strip()
    kl = str(k_low).strip()
    kh = str(k_high).strip()
    d = str(int(days))
    return f"{s}|{u}|{kl}|{kh}|{d}"


def _is_already_sent(fingerprint, history):
    return fingerprint in history


def _mark_as_sent(fingerprint, history, row, strategy_type="long_box_spread"):
    history[fingerprint] = {
        'sent_at': pd.Timestamp.now().isoformat(),
        'strategy': strategy_type,
        'underlying': str(row.get('underlying', '')),
        'strike_low': float(row.get('strike_low', 0)),
        'strike_high': float(row.get('strike_high', 0)),
        'days_to_maturity': int(row.get('days_to_maturity', 0)),
        'maturity_date': str(row.get('maturity_date', '')),
        'monthly_return': float(row.get('monthly_return_%', 0)),
    }


def send_best_position_to_bale(result_df):
    if not BALE_ENABLED:
        print("\n[SKIP] Bale notification is disabled.")
        return

    if not BALE_BOT_TOKEN or not BALE_CHAT_ID:
        print("\n[SKIP] Bale bot_token or chat_id is not configured.")
        return

    if result_df is None or result_df.empty:
        print("\n[BALE] No results to send.")
        return

    enter_df = result_df[result_df['decision'] == 'ENTER']
    if enter_df.empty:
        print("\n[BALE] No ENTER positions.")
        return

    history = _load_sent_history()
    print(f"\n[BALE-DEDUP] History: {len(history)} records.")

    pool_size = max(BALE_TOP_N * 10, 20)
    candidate_pool = enter_df.head(min(len(enter_df), pool_size))
    print(f"[BALE-DEDUP] Candidate pool: {len(candidate_pool)} positions "
          f"(looking for up to {BALE_TOP_N} new).")

    sent_count = 0
    skipped_count = 0

    for _, row in candidate_pool.iterrows():
        if sent_count >= BALE_TOP_N:
            break

        fingerprint = _build_fingerprint(
            underlying=row.get('underlying', ''),
            k_low=row.get('strike_low', 0),
            k_high=row.get('strike_high', 0),
            days=row.get('days_to_maturity', 0),
            strategy="long_box_spread",
        )

        if _is_already_sent(fingerprint, history):
            print(f"[BALE-DEDUP] SKIP duplicate: {fingerprint}")
            skipped_count += 1
            continue

        msg = build_long_box_spread_message(row)
        result = send_message_to_bale(msg)

        if result is not None:
            _mark_as_sent(fingerprint, history, row,
                          strategy_type="long_box_spread")
            sent_count += 1
            print(f"[BALE-DEDUP] SENT new: {fingerprint}")

    _save_sent_history(history)
    print(f"[BALE-DEDUP] Sent: {sent_count}, Skipped: {skipped_count}")

    if sent_count == 0:
        print(f"[BALE-DEDUP] WARNING: No new positions to send "
              f"(all {len(candidate_pool)} candidates were duplicates).")


# ============================================================
# لایه ۱: تحلیل یک Long Box Spread
# ============================================================
def long_box_spread_analysis(
    stock_price,
    strike_low,
    long_call_ask,
    short_call_bid,
    strike_high,
    long_put_ask,
    short_put_bid,
    contract_size,
    opt_buy_commission,
    opt_sell_commission,
    exercise_fee_rate,
    transfer_tax_rate,
    days,
    min_monthly_return,
):
    """
    محاسبه پارامترهای Long Box Spread.

    ساختار:
        Long CALL (K_low)  + Short CALL (K_high)
        Long PUT  (K_high) + Short PUT  (K_low)

    هزینه‌ها:
        - کارمزد ورود برای ۴ ساق
        - کارمزد اعمال فقط برای ۲ ساق خرید (Long Call, Long Put)
        - مالیات انتقال روی:
              * Short CALL(K_high) → واگذاری سهم پایه به طرف مقابل
              * Long PUT(K_high)   → دریافت سهم پایه از اعمال
          که هر دو روی مبلغ K_high × ContractSize محاسبه می‌شوند.
    """
    # ===== پریمیوم‌های ناخالص ورود =====
    long_call_premium = round(long_call_ask * contract_size, 0)
    long_put_premium = round(long_put_ask * contract_size, 0)

    short_call_premium = round(short_call_bid * contract_size, 0)
    short_put_premium = round(short_put_bid * contract_size, 0)

    # ===== کارمزدهای ورود =====
    long_call_entry_fee = round(long_call_premium * opt_buy_commission, 0)
    long_put_entry_fee = round(long_put_premium * opt_buy_commission, 0)

    short_call_entry_fee = round(short_call_premium * opt_sell_commission, 0)
    short_put_entry_fee = round(short_put_premium * opt_sell_commission, 0)

    total_entry_fees = (
        long_call_entry_fee
        + long_put_entry_fee
        + short_call_entry_fee
        + short_put_entry_fee
    )

    # ===== بدهی خالص (سرمایه درگیر) =====
    net_debit = (
        long_call_premium + long_put_premium
        - short_call_premium - short_put_premium
        + total_entry_fees
    )

    # اگر بدهی خالص مثبت نباشد یعنی داده معیوب یا آربیتراژ لحظه‌ای غیرواقعی
    if net_debit <= 0:
        return {'status': 'DISCARD'}

    # ===== حداکثر بازدهی در سررسید (تضمینی) =====
    max_payoff = (strike_high - strike_low) * contract_size

    # ===== کارمزدهای اعمال (فقط دو ساق خرید) =====
    long_call_exercise_fee = round(
        (strike_low * contract_size) * exercise_fee_rate, 0)
    long_put_exercise_fee = round(
        (strike_high * contract_size) * exercise_fee_rate, 0)
    total_exercise_fees = long_call_exercise_fee + long_put_exercise_fee

    # ===== مالیات نقل و انتقال =====
    # Short CALL(K_high) → ما سهم را واگذار می‌کنیم
    short_call_transfer_tax = round(
        (strike_high * contract_size) * transfer_tax_rate, 0)
    # Long PUT(K_high) → سهم به ما واگذار می‌شود
    long_put_transfer_tax = round(
        (strike_high * contract_size) * transfer_tax_rate, 0)
    total_transfer_tax = short_call_transfer_tax + long_put_transfer_tax

    # ===== سود خالص تضمینی =====
    max_net_profit = (
        max_payoff
        - net_debit
        - total_exercise_fees
        - total_transfer_tax
    )

    # ===== بازدهی =====
    capital_at_risk = max(1.0, net_debit)
    days_safe = max(T_DISPLAY_EPSILON, float(days))

    raw_return_percent = round((max_net_profit / capital_at_risk) * 100, 4)
    monthly_return = round(
        (max_net_profit / capital_at_risk) * (30 / days_safe) * 100, 4)

    # ===== فیلتر بازدهی =====
    if monthly_return < min_monthly_return:
        return {'status': 'DISCARD'}

    return {
        'status': 'VALID',
        'net_debit': net_debit,
        'max_payoff': max_payoff,
        'max_net_profit': max_net_profit,
        'capital_at_risk': capital_at_risk,
        'raw_return_percent': raw_return_percent,
        'monthly_return': monthly_return,
        'total_entry_fees': total_entry_fees,
        'total_exercise_fees': total_exercise_fees,
        'total_transfer_tax': total_transfer_tax,
    }


# ============================================================
# لایه ۲: اجرای استراتژی روی داده بازار (نسخه بهینه‌شده)
# ============================================================
def run_long_box_spread_strategy(
    df_options,
    min_monthly_return=DEFAULT_MIN_MONTHLY_RETURN,
):
    """
    اجرای کامل استراتژی Long Box Spread با اسکن سریع.

    بهینه‌سازی‌ها:
        1. ابتدا CALLها و PUTهای معتبر (هم Bid و هم Ask > 0) را
           با استفاده از dict-indexing سریع استخراج می‌کنیم.
        2. سپس «نردبان مشترک» را با intersection دو دیکشنری
           می‌سازیم تا فقط Strikeهایی بمانند که هر چهار
           قرارداد با قیمت معتبر در آن‌ها موجود است.
        3. زوج‌گیری فقط روی این نردبان کوچک‌شده انجام می‌شود.
    """
    results = []

    for underlying_symbol, group in df_options.groupby('UnderlyingTicker'):
        market = get_symbol_market(underlying_symbol)
        kind = get_symbol_kind(underlying_symbol)

        opt_buy_commission = get_commission_rate(market, 'option', True)
        opt_sell_commission = get_commission_rate(market, 'option', False)
        exercise_fee_rate = get_exercise_fee_rate(market, kind)

        for days, sub_group in group.groupby('DaysToMaturity'):

            # =========================================================
            # مرحله ۱: تشخیص سریع نوع قرارداد (CALL / PUT)
            # =========================================================
            type_series = sub_group['Type']
            first_type = type_series.iloc[0]

            if hasattr(first_type, 'name'):
                # enum است
                type_upper = type_series.apply(
                    lambda x: x.name if hasattr(x, 'name') else str(x).upper()
                )
            else:
                type_upper = type_series.astype(str).str.upper()

            call_df = sub_group[type_upper == 'CALL']
            put_df = sub_group[type_upper == 'PUT']

            if call_df.empty or put_df.empty:
                continue

            # =========================================================
            # مرحله ۲: ساخت دیکشنری‌های «معتبر» (هم Bid و هم Ask > 0)
            # =========================================================
            def _build_valid_map(df):
                strike_arr = df['StrikePrice'].to_numpy(dtype=float)
                ask_arr = df['AskPrice'].to_numpy(dtype=float)
                bid_arr = df['BidPrice'].to_numpy(dtype=float)
                records = df.to_dict('records')

                valid = {}
                for k, ask, bid, rec in zip(strike_arr, ask_arr, bid_arr, records):
                    if (
                        pd.notna(ask) and ask > 0
                        and pd.notna(bid) and bid > 0
                        and k not in valid
                    ):
                        valid[k] = rec
                return valid

            call_map = _build_valid_map(call_df)
            put_map = _build_valid_map(put_df)

            # =========================================================
            # مرحله ۳: نردبان مشترک (Intersection)
            # =========================================================
            common_strikes = sorted(call_map.keys() & put_map.keys())
            n = len(common_strikes)

            if n < 2:
                continue

            # =========================================================
            # مرحله ۴: زوج‌گیری سریع
            # =========================================================
            for i in range(n):
                k_low = common_strikes[i]
                call_low = call_map[k_low]
                put_low = put_map[k_low]

                long_call_ask = float(call_low['AskPrice'])
                short_put_bid = float(put_low['BidPrice'])

                # مقادیر ثابت مشترک (چون همه یک نماد پایه و یک سررسید دارند)
                stock_price = call_low['UnderlyingPrice']
                contract_size = call_low['ContractSize']
                maturity_date = str(call_low.get('MaturityDate', ''))

                for j in range(i + 1, n):
                    k_high = common_strikes[j]
                    call_high = call_map[k_high]
                    put_high = put_map[k_high]

                    short_call_bid = float(call_high['BidPrice'])
                    long_put_ask = float(put_high['AskPrice'])

                    res = long_box_spread_analysis(
                        stock_price=stock_price,
                        strike_low=k_low,
                        long_call_ask=long_call_ask,
                        short_call_bid=short_call_bid,
                        strike_high=k_high,
                        long_put_ask=long_put_ask,
                        short_put_bid=short_put_bid,
                        contract_size=contract_size,
                        opt_buy_commission=opt_buy_commission,
                        opt_sell_commission=opt_sell_commission,
                        exercise_fee_rate=exercise_fee_rate,
                        transfer_tax_rate=TRANSFER_TAX_RATE,
                        days=days,
                        min_monthly_return=min_monthly_return,
                    )

                    if res['status'] == 'DISCARD':
                        continue

                    results.append({
                        'underlying': underlying_symbol,
                        'stock_price': round(stock_price, 0),
                        'strike_low': k_low,
                        'strike_high': k_high,
                        'long_call_symbol': call_low['Ticker'],
                        'long_call_ask_premium': round(long_call_ask, 0),
                        'short_call_symbol': call_high['Ticker'],
                        'short_call_bid_premium': round(short_call_bid, 0),
                        'long_put_symbol': put_high['Ticker'],
                        'long_put_ask_premium': round(long_put_ask, 0),
                        'short_put_symbol': put_low['Ticker'],
                        'short_put_bid_premium': round(short_put_bid, 0),
                        'net_debit': res['net_debit'],
                        'max_payoff': res['max_payoff'],
                        'max_net_profit': res['max_net_profit'],
                        'capital_at_risk': res['capital_at_risk'],
                        'raw_return_percent': res['raw_return_percent'],
                        'monthly_return_%': res['monthly_return'],
                        'total_entry_fees': res['total_entry_fees'],
                        'total_exercise_fees': res['total_exercise_fees'],
                        'total_transfer_tax': res['total_transfer_tax'],
                        'days_to_maturity': days,
                        'long_call_volume': int(call_low.get('Volume', 0)),
                        'short_call_volume': int(call_high.get('Volume', 0)),
                        'long_put_volume': int(put_high.get('Volume', 0)),
                        'short_put_volume': int(put_low.get('Volume', 0)),
                        'maturity_date': maturity_date,
                    })

    if not results:
        return pd.DataFrame()

    result_df = pd.DataFrame(results)

    # ===== رتبه‌بندی بر اساس بازدهی ماهانه (نزولی) =====
    result_df = result_df.sort_values(
        by='monthly_return_%', ascending=False).reset_index(drop=True)

    # ===== تصمیم =====
    result_df['decision'] = 'ENTER'

    # ===== چیدمان ستون‌ها =====
    column_order = [
        'underlying', 'decision',
        'monthly_return_%', 'raw_return_percent',
        'net_debit', 'max_payoff', 'max_net_profit',
        'capital_at_risk',
        'stock_price', 'strike_low', 'strike_high',
        'long_call_symbol', 'long_call_ask_premium',
        'short_call_symbol', 'short_call_bid_premium',
        'long_put_symbol', 'long_put_ask_premium',
        'short_put_symbol', 'short_put_bid_premium',
        'total_entry_fees', 'total_exercise_fees', 'total_transfer_tax',
        'days_to_maturity',
        'long_call_volume', 'short_call_volume',
        'long_put_volume', 'short_put_volume',
        'maturity_date',
    ]
    column_order = [c for c in column_order if c in result_df.columns]
    result_df = result_df[column_order]

    return result_df


# ============================================================
# ذخیره خروجی در اکسل
# ============================================================
def save_results_to_excel(result_df, filename="result_long_box_spread.xlsx"):
    header_font = Font(name='Segoe UI', size=11, bold=True, color='FFFFFF')
    header_fill = PatternFill(
        start_color='1F4E3D', end_color='1F4E3D', fill_type='solid')
    alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    body_font = Font(name='Segoe UI', size=10)
    gray_font = Font(color='808080', italic=True, name='Segoe UI', size=10)

    rename_dict = {
        'underlying': 'نماد پایه',
        'decision': 'تصمیم',
        'monthly_return_%': 'بازدهی ماهانه',
        'raw_return_percent': 'بازدهی کل',
        'net_debit': 'بدهی خالص',
        'max_payoff': 'حداکثر بازدهی',
        'max_net_profit': 'سود خالص تضمینی',
        'capital_at_risk': 'سرمایه درگیر',
        'stock_price': 'قیمت سهم',
        'strike_low': 'اعمال پایین',
        'strike_high': 'اعمال بالا',
        'long_call_symbol': 'نماد خرید CALL',
        'long_call_ask_premium': 'پریمیوم خرید CALL',
        'short_call_symbol': 'نماد فروش CALL',
        'short_call_bid_premium': 'پریمیوم فروش CALL',
        'long_put_symbol': 'نماد خرید PUT',
        'long_put_ask_premium': 'پریمیوم خرید PUT',
        'short_put_symbol': 'نماد فروش PUT',
        'short_put_bid_premium': 'پریمیوم فروش PUT',
        'total_entry_fees': 'کارمزد ورود',
        'total_exercise_fees': 'کارمزد اعمال',
        'total_transfer_tax': 'مالیات انتقال',
        'days_to_maturity': 'روز تا سررسید',
        'long_call_volume': 'حجم خرید CALL',
        'short_call_volume': 'حجم فروش CALL',
        'long_put_volume': 'حجم خرید PUT',
        'short_put_volume': 'حجم فروش PUT',
        'maturity_date': 'تاریخ اعمال',
    }

    result_df_renamed = result_df.rename(columns=rename_dict)
    filepath = current_dir / filename

    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        result_df_renamed.to_excel(
            writer, sheet_name='long_box_spread', index=False)
        worksheet = writer.sheets['long_box_spread']

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
            f"A1:{get_column_letter(len(result_df_renamed.columns))}"
            f"{len(result_df_renamed) + 1}")
        worksheet.freeze_panes = 'A2'

        for col in worksheet.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                if cell.value:
                    text = str(cell.value)
                    if '\n' in text:
                        line_length = max(len(line) for line in text.split('\n'))
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
    """تابع اصلی اجرای استراتژی Long Box Spread."""
    try:
        # ===== بارگذاری داده بازار =====
        df_raw = MarketDownloader.from_tsetmc_direct()
        df_cleaned = DataCleaner.clean(df_raw)
        df_final = DataCleaner.add_derived_columns(df_cleaned)

        filtered_data = df_final[df_final['DaysToMaturity'] >= 0.0].copy()

        if filtered_data.empty:
            print("No market data found.")
            return

        print(f"Market data: {len(filtered_data)} option contracts loaded")

        # ===== اجرای استراتژی =====
        results = run_long_box_spread_strategy(
            filtered_data,
            min_monthly_return=DEFAULT_MIN_MONTHLY_RETURN,
        )

        if results.empty:
            print("No valid Long Box setups found.")
            return

        print(f"\nResults: {len(results)} Long Box positions found")

        # ===== ذخیره در اکسل =====
        save_results_to_excel(results)

        # ===== ارسال به بله =====
        send_best_position_to_bale(results)

    except Exception as e:
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()