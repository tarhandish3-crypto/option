# 0myStrategy/api_server.py
# -*- coding: utf-8 -*-

"""
Backend تحلیلگر آپشن:
- Watcher: هر ۳ ثانیه TSETMC را می‌خواند و **فقط استراتژی فعال** را تحلیل می‌کند
- STATE: ذخیره نتایج در حافظه
- FastAPI: Endpointها برای UI و Snippet
- Bale: ارسال پیام به پیام‌رسان بله

قابل اجرا:
1. مستقل:     python api_server.py
2. از UI:     from api_server import run_api_server_threaded
"""

import sys
import threading
import time
import json
from pathlib import Path
from datetime import datetime

# ═══════════════════════════════════════════════════════════════
# 🔧 مسیرها
# ═══════════════════════════════════════════════════════════════

current_file_path = Path(__file__).resolve()
current_dir = current_file_path.parent          # 0myStrategy/
root_dir = current_dir.parent                   # generate_strategyV4/

sys.path.insert(0, str(root_dir))

# ═══════════════════════════════════════════════════════════════
# Imports
# ═══════════════════════════════════════════════════════════════

import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

# ماژول‌های پروژه
from config import (
    EXERCISE_TAX_RATE,
    get_commission_rate,
    get_exercise_fee_rate,
    get_symbol_kind,
    get_symbol_market,
)

from data.downloader import MarketDownloader
from data.cleaner import DataCleaner

from Bull_call_spread import run_bull_call_spread_strategy
from Covered_Call import analyze_covered_call
from Long_Call import run_long_call_strategy


# ═══════════════════════════════════════════════════════════════
# تنظیمات
# ═══════════════════════════════════════════════════════════════

# ⏱ فاصله Watcher (کوتاه‌تر = سریع‌تر ولی سنگین‌تر)
WATCHER_INTERVAL_SEC = 3

VALID_STRATEGIES = ["bull_call_spread", "covered_call", "long_call"]


# ═══════════════════════════════════════════════════════════════
# Pydantic Models
# ═══════════════════════════════════════════════════════════════

class SelectPositionRequest(BaseModel):
    strategy: str
    index: int


class BaleMessageRequest(BaseModel):
    message: str


class ActiveStrategyRequest(BaseModel):
    strategy: str


# ═══════════════════════════════════════════════════════════════
# بارگذاری پروفایل نوسان
# ═══════════════════════════════════════════════════════════════

VOLATILITY_FILE = current_dir / "Historical_Volatility.xlsx"


def load_volatility_from_root():
    """بارگذاری پروفایل نوسان از root_dir"""
    if not VOLATILITY_FILE.exists():
        print(f"⚠️ فایل نوسان یافت نشد: {VOLATILITY_FILE}")
        return pd.DataFrame()

    try:
        df_vol = pd.read_excel(VOLATILITY_FILE)
        required_cols = ['UnderlyingTicker', 'HV_60']
        missing = [c for c in required_cols if c not in df_vol.columns]
        if missing:
            print(f"⚠️ ستون‌های گمشده در فایل نوسان: {missing}")
            return pd.DataFrame()

        df_vol = df_vol.rename(columns={'UnderlyingTicker': 'underlying'})

        keep_cols = ['underlying', 'HV_60']
        if 'VolatilityQualityScore' in df_vol.columns:
            keep_cols.append('VolatilityQualityScore')

        return df_vol[keep_cols].copy()

    except Exception as e:
        print(f"❌ خطا در بارگذاری فایل نوسان: {e}")
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════════
# FastAPI Setup
# ═══════════════════════════════════════════════════════════════

app = FastAPI(title="Option Analyzer API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════
# State
# ═══════════════════════════════════════════════════════════════

STATE = {
    "positions": {
        "bull_call_spread": [],
        "covered_call": [],
        "long_call": [],
    },
    "active_strategy": "bull_call_spread",   # ← استراتژی فعال
    "last_update": 0,
    "fetch_count": 0,
    "error_count": 0,
    "is_running": False,
    "pending_order": None,
    "lock": threading.Lock(),
    "last_duration_ms": 0,   # زمان اجرای آخرین تحلیل
}

# ═══════════════════════════════════════════════════════════════
# Bale Notifier
# ═══════════════════════════════════════════════════════════════

BALE_ENABLED = False
BALE_TOKEN = ""
BALE_CHAT_ID = ""
BALE_TOP_N = 3


def load_bale_config():
    """خواندن تنظیمات بله از user_settings.json"""
    global BALE_ENABLED, BALE_TOKEN, BALE_CHAT_ID, BALE_TOP_N

    settings_file = root_dir / "user_settings.json"

    if not settings_file.exists():
        print(f"⚠️ user_settings.json یافت نشد: {settings_file}")
        return

    try:
        with open(settings_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        active_profile = data.get('active_profile', '')
        profiles = data.get('profiles', {})

        if active_profile and active_profile in profiles:
            bale = profiles[active_profile].get('bale', {})
            BALE_ENABLED = bale.get('enabled', False)
            BALE_TOKEN = bale.get('bot_token', '')
            BALE_CHAT_ID = bale.get('chat_id', '')
            BALE_TOP_N = int(bale.get('top_n', 3))
            print(f"✅ Bale config loaded (enabled={BALE_ENABLED})")
        else:
            print(f"⚠️ پروفایل فعال '{active_profile}' یافت نشد")
    except Exception as e:
        print(f"❌ Bale config error: {e}")


def send_to_bale(message):
    """ارسال پیام به بله"""
    if not BALE_ENABLED or not BALE_TOKEN or not BALE_CHAT_ID:
        return False

    import requests

    url = f"https://tapi.bale.ai/bot{BALE_TOKEN}/sendMessage"
    payload = {
        "chat_id": BALE_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
    }

    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            return True
        else:
            print(f"Bale failed: {r.status_code} - {r.text[:100]}")
            return False
    except Exception as e:
        print(f"Bale error: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
# Watcher — فقط استراتژی فعال
# ═══════════════════════════════════════════════════════════════

def analyze_market():
    """
    دریافت داده و تحلیل **فقط استراتژی فعال**.
    
    این تابع بر اساس STATE["active_strategy"] تصمیم می‌گیرد
    کدام استراتژی را محاسبه کند.
    """
    try:
        t_start = time.time()
        
        # ۱. خواندن استراتژی فعال
        with STATE["lock"]:
            active = STATE.get("active_strategy", "bull_call_spread")
        
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] شروع تحلیل ({active})...")

        # ===== بارگذاری پروفایل نوسان =====
        df_vol = load_volatility_profile()
        if df_vol.empty:
            print("\nWARNING: Volatility profile not loaded.")
        else:
            print(f"\nVolatility profile: {len(df_vol)} symbols loaded")
            
        # ۲. دریافت داده
        df_raw = MarketDownloader.from_tsetmc_direct()
        df_cleaned = DataCleaner.clean(df_raw)
        df_final = DataCleaner.add_derived_columns(df_cleaned)

        # ۳. فیلتر CALL
        is_call = df_final['Type'].apply(
            lambda x: x.name == 'CALL' if hasattr(x, 'name')
            else str(x).upper() == 'CALL')
        calls = df_final[(df_final['DaysToMaturity'] >= 0) & is_call].copy()
        if calls.empty:
            print("No market data found.")
            return
        print(f"  CALLs: {len(calls)}")

        # ═══════════════════════════════════════════════════════
        # 🎯 ۵. تحلیل فقط استراتژی فعال
        # ═══════════════════════════════════════════════════════

        if active == "bull_call_spread":
            try:
                bcs_results = run_bull_call_spread_strategy(df_options=calls, df_vol=df_vol)
                if bcs_results is not None and not bcs_results.empty:
                    enter_bcs = bcs_results[bcs_results['decision'] == 'ENTER']
                    with STATE["lock"]:
                        STATE["positions"]["bull_call_spread"] = enter_bcs.to_dict('records')
                    print(f"  ✅ Bull Call Spread: {len(enter_bcs)} ENTER")
                else:
                    with STATE["lock"]:
                        STATE["positions"]["bull_call_spread"] = []
                    print(f"  Bull Call Spread: 0")
            except Exception as e:
                print(f"  ⚠️ Bull Call error: {e}")

        elif active == "covered_call":
            try:
                cc_results = analyze_covered_call(
                    output_file=str(current_dir / "covered_call_temp.xlsx")
                )
                if cc_results is not None and not cc_results.empty:
                    enter_cc = cc_results[cc_results['decision'] == 'ENTER']
                    with STATE["lock"]:
                        STATE["positions"]["covered_call"] = enter_cc.to_dict('records')
                    print(f"  ✅ Covered Call: {len(enter_cc)} ENTER")
                else:
                    with STATE["lock"]:
                        STATE["positions"]["covered_call"] = []
                    print(f"  Covered Call: 0")
            except Exception as e:
                print(f"  ⚠️ Covered Call error: {e}")

        elif active == "long_call":
            try:
                lc_results = run_long_call_strategy(calls, max_break_even_percent=12)
                if lc_results is not None and not lc_results.empty:
                    with STATE["lock"]:
                        STATE["positions"]["long_call"] = lc_results.to_dict('records')
                    print(f"  ✅ Long Call: {len(lc_results)}")
                else:
                    with STATE["lock"]:
                        STATE["positions"]["long_call"] = []
                    print(f"  Long Call: 0")
            except Exception as e:
                print(f"  ⚠️ Long Call error: {e}")

        else:
            print(f"  ⚠️ استراتژی ناشناخته: {active}")

        # ۶. به‌روزرسانی State
        t_duration_ms = int((time.time() - t_start) * 1000)
        with STATE["lock"]:
            STATE["last_update"] = time.time()
            STATE["fetch_count"] += 1
            STATE["last_duration_ms"] = t_duration_ms

        # ۷. ارسال به بله (فقط استراتژی فعال)
        send_new_positions_to_bale(active)

        print(f"  ✅ تحلیل کامل شد در {t_duration_ms} میلی‌ثانیه")

    except Exception as e:
        with STATE["lock"]:
            STATE["error_count"] += 1
        print(f"  ❌ خطا: {e}")
        import traceback
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════════
# Bale — ارسال موقعیت‌های جدید
# ═══════════════════════════════════════════════════════════════

SENT_FINGERPRINTS = set()


def build_fingerprint(strategy, pos):
    """ساخت اثر انگشت یکتا"""
    if strategy == 'bull_call_spread':
        return f"{strategy}|{pos.get('underlying')}|{pos.get('long_option_symbol')}|{pos.get('short_option_symbol')}|{pos.get('days_to_maturity')}"
    else:
        return f"{strategy}|{pos.get('underlying')}|{pos.get('option_symbol')}|{pos.get('days_to_maturity')}"


def send_new_positions_to_bale(active_strategy):
    """ارسال موقعیت‌های جدید به بله (فقط استراتژی فعال)"""
    if not BALE_ENABLED:
        return

    with STATE["lock"]:
        positions = STATE["positions"].get(active_strategy, [])

    for pos in positions[:BALE_TOP_N]:
        fp = build_fingerprint(active_strategy, pos)
        if fp in SENT_FINGERPRINTS:
            continue

        if active_strategy == 'bull_call_spread':
            msg = (
                f"🤖 *Bull Call Spread*\n"
                f"📌 {pos.get('underlying')}\n"
                f"🟢 {pos.get('long_option_symbol')}\n"
                f"🔴 {pos.get('short_option_symbol')}\n"
                f"📈 سود ماهانه: {pos.get('monthly_return_%')}%\n"
                f"🏆 امتیاز: {pos.get('composite_score')}\n"
                f"⏱ {pos.get('days_to_maturity')} روز"
            )
        elif active_strategy == 'covered_call':
            msg = (
                f"🤖 *Covered Call*\n"
                f"📌 {pos.get('underlying')}\n"
                f"🔴 {pos.get('option_symbol')}\n"
                f"📈 سود ماهانه: {pos.get('monthly_return_%')}%\n"
                f"🏆 امتیاز: {pos.get('composite_score')}"
            )
        else:
            msg = (
                f"🤖 *Long Call*\n"
                f"📌 {pos.get('underlying')}\n"
                f"🟢 {pos.get('option_symbol')}\n"
                f"📈 سود ماهانه: {pos.get('monthly_return_%')}%"
            )

        if send_to_bale(msg):
            SENT_FINGERPRINTS.add(fp)
            print(f"  📱 Bale: {active_strategy} - {pos.get('underlying')}")
        time.sleep(0.5)


def watcher_loop():
    """حلقه اصلی Watcher"""
    STATE["is_running"] = True
    print(f"🚀 Watcher started (interval: {WATCHER_INTERVAL_SEC}s)")

    while True:
        try:
            analyze_market()
        except Exception as e:
            print(f"Watcher error: {e}")
            with STATE["lock"]:
                STATE["error_count"] += 1

        time.sleep(WATCHER_INTERVAL_SEC)


# ═══════════════════════════════════════════════════════════════
# 🎯 استخراج لگ‌ها از موقعیت
# ═══════════════════════════════════════════════════════════════

def _extract_legs_from_position(strategy: str, pos: dict) -> list:
    """استخراج لیست لگ‌ها از یک موقعیت بر اساس استراتژی"""
    legs = []

    def to_num(val, default=0):
        try:
            if val is None:
                return default
            return float(val)
        except (ValueError, TypeError):
            return default

    if strategy == 'bull_call_spread':
        legs.append({
            "direction": "buy",
            "symbol": str(pos.get('long_option_symbol', '')).strip(),
            "price": to_num(pos.get('long_ask_premium', 0)),
            "quantity": 1,
            "description": "خرید CALL",
        })
        legs.append({
            "direction": "sell",
            "symbol": str(pos.get('short_option_symbol', '')).strip(),
            "price": to_num(pos.get('short_bid_premium', 0)),
            "quantity": 1,
            "description": "فروش CALL",
        })

    elif strategy == 'covered_call':
        legs.append({
            "direction": "buy",
            "symbol": str(pos.get('underlying', '')).strip(),
            "price": to_num(pos.get('stock_price', 0)),
            "quantity": 1,
            "description": "خرید سهم پایه",
        })
        legs.append({
            "direction": "sell",
            "symbol": str(pos.get('option_symbol', '')).strip(),
            "price": to_num(pos.get('premium', 0)),
            "quantity": 1,
            "description": "فروش CALL",
        })

    elif strategy == 'long_call':
        legs.append({
            "direction": "buy",
            "symbol": str(pos.get('option_symbol', '')).strip(),
            "price": to_num(pos.get('premium', 0)),
            "quantity": 1,
            "description": "خرید CALL",
        })

    # فیلتر لگ‌های خالی
    legs = [leg for leg in legs if leg['symbol'] and leg['price'] > 0]

    return legs


# ═══════════════════════════════════════════════════════════════
# API Endpoints
# ═══════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {"status": "ok", "message": "Option Analyzer API"}


@app.get("/health")
def health():
    with STATE["lock"]:
        return {
            "status": "ok",
            "active_strategy": STATE.get("active_strategy"),
            "last_update_ago": time.time() - STATE["last_update"] if STATE["last_update"] else None,
            "last_duration_ms": STATE.get("last_duration_ms", 0),
            "fetch_count": STATE["fetch_count"],
            "error_count": STATE["error_count"],
            "bale_enabled": BALE_ENABLED,
        }


@app.get("/active-strategy")
def get_active_strategy():
    """دریافت استراتژی فعال فعلی"""
    with STATE["lock"]:
        return {
            "active_strategy": STATE.get("active_strategy", "bull_call_spread"),
            "valid_strategies": VALID_STRATEGIES,
        }


@app.post("/set-active-strategy")
def set_active_strategy_endpoint(req: ActiveStrategyRequest):
    """
    تنظیم استراتژی فعال.
    
    Watcher در دور بعدی، فقط این استراتژی را محاسبه می‌کند.
    """
    strategy = req.strategy

    if strategy not in VALID_STRATEGIES:
        return {
            "error": f"Invalid strategy: {strategy}",
            "valid_strategies": VALID_STRATEGIES,
        }

    with STATE["lock"]:
        old_strategy = STATE.get("active_strategy")
        STATE["active_strategy"] = strategy

        # پاک کردن نتایج استراتژی‌های غیرفعال (برای آزادسازی حافظه)
        for s in VALID_STRATEGIES:
            if s != strategy:
                STATE["positions"][s] = []

    print(f"\n🎯 Active strategy changed: {old_strategy} → {strategy}")
    return {
        "status": "ok",
        "active_strategy": strategy,
        "message": f"Watcher will analyze '{strategy}' in next cycle",
    }


@app.get("/all-positions")
def get_all_positions():
    """همه موقعیت‌ها (فقط استراتژی فعال دارای داده است)"""
    with STATE["lock"]:
        return {
            "positions": STATE["positions"],
            "active_strategy": STATE.get("active_strategy"),
            "last_update": STATE["last_update"],
            "last_duration_ms": STATE.get("last_duration_ms", 0),
            "fetch_count": STATE["fetch_count"],
        }


@app.get("/active-positions")
def get_active_positions():
    """فقط موقعیت‌های استراتژی فعال"""
    with STATE["lock"]:
        active = STATE.get("active_strategy", "bull_call_spread")
        return {
            "active_strategy": active,
            "positions": STATE["positions"].get(active, []),
            "last_update": STATE["last_update"],
            "last_duration_ms": STATE.get("last_duration_ms", 0),
        }


@app.get("/top-positions/{strategy}")
def get_top_positions(strategy: str, limit: int = 10):
    with STATE["lock"]:
        if strategy not in STATE["positions"]:
            return {"error": "Unknown strategy"}

        positions = STATE["positions"][strategy][:limit]
        return {
            "strategy": strategy,
            "count": len(positions),
            "positions": positions,
            "updated_at": STATE["last_update"],
        }


@app.get("/best-position")
def get_best_position():
    """بهترین موقعیت Bull Call Spread (سازگاری)"""
    with STATE["lock"]:
        positions = STATE["positions"]["bull_call_spread"]
        last_update = STATE["last_update"]

    if not positions:
        return {"data": None, "updated_at": last_update}

    sorted_positions = sorted(
        positions,
        key=lambda p: p.get('composite_score', 0)
        if isinstance(p.get('composite_score'), (int, float)) else 999999,
        reverse=True
    )

    best = sorted_positions[0]

    return {
        "data": {
            "id": f"{best.get('underlying')}_{best.get('long_option_symbol')}_{best.get('short_option_symbol')}_{best.get('days_to_maturity')}",
            "strategy": "bull_call_spread",
            "underlying": best.get('underlying'),
            "long_option_symbol": best.get('long_option_symbol'),
            "long_strike": best.get('long_strike'),
            "long_ask_premium": best.get('long_ask_premium'),
            "short_option_symbol": best.get('short_option_symbol'),
            "short_strike": best.get('short_strike'),
            "short_bid_premium": best.get('short_bid_premium'),
            "composite_score": best.get('composite_score'),
            "monthly_return": best.get('monthly_return_%'),
            "margin30": best.get('margin30'),
            "days_to_maturity": best.get('days_to_maturity'),
            "maturity_date": best.get('maturity_date'),
        },
        "updated_at": last_update,
    }


@app.post("/select-position")
def select_position(req: SelectPositionRequest):
    """
    انتخاب موقعیت برای ارسال به کارگزاری.
    """
    strategy = req.strategy
    index = req.index

    with STATE["lock"]:
        if strategy not in STATE["positions"]:
            return {"error": "Unknown strategy"}

        positions = STATE["positions"][strategy]
        if index < 0 or index >= len(positions):
            return {"error": "Index out of range"}

        position = positions[index]
        legs = _extract_legs_from_position(strategy, position)

        STATE["pending_order"] = {
            "id": f"{position.get('underlying')}_{time.time()}",
            "strategy": strategy,
            "position": position,
            "legs": legs,
            "timestamp": time.time(),
        }
        pending = STATE["pending_order"]

    print(f"\n📤 Selected: {strategy} - {position.get('underlying')}")
    print(f"   Legs: {len(legs)}")
    for i, leg in enumerate(legs, 1):
        direction_fa = "خرید" if leg['direction'] == 'buy' else "فروش"
        print(f"     {i}. {direction_fa} {leg['symbol']} @ {leg['price']}")

    return {"status": "ok", "pending_order": pending}


@app.get("/pending-order")
def get_pending_order():
    with STATE["lock"]:
        return {"pending_order": STATE["pending_order"]}


@app.post("/clear-pending")
def clear_pending():
    with STATE["lock"]:
        STATE["pending_order"] = None
    return {"status": "ok"}


@app.post("/send-to-bale")
def send_to_bale_endpoint(req: BaleMessageRequest):
    message = req.message
    if not message:
        return {"error": "Empty message"}

    if not BALE_ENABLED:
        return {"error": "Bale not enabled in user_settings.json"}

    ok = send_to_bale(message)
    if ok:
        return {"status": "ok"}
    else:
        return {"error": "Failed to send"}


# ═══════════════════════════════════════════════════════════════
# توابع اجرا
# ═══════════════════════════════════════════════════════════════

def run_api_server_threaded():
    """اجرای Watcher و FastAPI در Threadهای جداگانه"""
    print("=" * 60)
    print("🚀 Starting Option Analyzer Backend...")
    print("=" * 60)

    load_bale_config()

    # Watcher در Thread جداگانه
    watcher_thread = threading.Thread(target=watcher_loop, daemon=True)
    watcher_thread.start()
    print("✅ Watcher thread started")

    # FastAPI در Thread جداگانه
    API_PORT = 8001
    def _run_uvicorn():
        print(f"FastAPI starting on port {API_PORT}...")
        try:
            uvicorn.run(app, host="127.0.0.1", port=API_PORT, log_level="warning")
        except Exception as e:
            print(f"FastAPI error: {e}")

    api_thread = threading.Thread(target=_run_uvicorn, daemon=True)
    api_thread.start()
    print("✅ FastAPI thread started (port 8000)")

    return watcher_thread, api_thread


def run_api_server_standalone():
    """اجرای مستقل API Server (blocking)"""
    print("=" * 60)
    print("🚀 Option Analyzer API Server (Standalone)")
    print("=" * 60)

    load_bale_config()

    threading.Thread(target=watcher_loop, daemon=True).start()
    print("✅ Watcher thread started")

    print("\n📡 API Server: http://127.0.0.1:8000")
    print("   • GET  /health")
    print("   • GET  /active-strategy")
    print("   • POST /set-active-strategy")
    print("   • GET  /active-positions")
    print("   • GET  /all-positions")
    print("   • POST /select-position")
    print("   • GET  /pending-order")
    print("   • POST /clear-pending")
    print("   • POST /send-to-bale")
    print("=" * 60)

    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    run_api_server_standalone()