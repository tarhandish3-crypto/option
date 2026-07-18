# config.py
# -*- coding: utf-8 -*-

from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np

# =====================================================
# مسیرهای اصلی پروژه (Directory Structure)
# =====================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = BASE_DIR / "output"
CHARTS_DIR = OUTPUT_DIR / "charts"
LOGS_DIR = BASE_DIR / "logs"

# تضمین ایجاد پوشه‌های حیاتی در بدو اجرای برنامه
for directory in [DATA_DIR, CACHE_DIR, OUTPUT_DIR, CHARTS_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# =====================================================
# کارمزدها و مالیات (Fees & Taxes)
# =====================================================

# ===== کارمزد اعمال بر اساس نوع دارایی (طبق تعرفه سمات) =====
EXERCISE_FEE_RATE: Dict[tuple, float] = {
    ('tse', 'stock'): 0.0005,       # ۰.۱٪ برای سهام عادی
    ('ifb', 'stock'): 0.0005,       # ۰.۱٪ برای سهام فرابورس
    ('tse', 'etf-stock'): 0.0005,  # ۰.۰۵٪ برای ETF سهامی
    ('ifb', 'etf-stock'): 0.0005,  # ۰.۰۵٪ برای ETF سهامی فرابورس
    ('tse', 'etf-leverage'): 0.0005,  # صندوق های اهرمی
    ('ifb', 'etf-leverage'): 0.0005,
    ('tse', 'etf-fix'): 0.0005,    # ۰.۰۲٪ برای ETF درآمد ثابت
    ('ifb', 'etf-fix'): 0.0005,    # ۰.۰۲٪ برای ETF درآمد ثابت فرابورس
    ('tse', 'etf-gold'): 0.0005,   # ۰.۰۵٪ برای ETF طلا
    ('ifb', 'etf-gold'): 0.0005,   # ۰.۰۵٪ برای ETF طلا فرابورس
    ('tse', 'etf-mix'): 0.0005,    # ۰.۰۲٪ برای ETF مختلط
    ('ifb', 'etf-mix'): 0.0005,    # ۰.۰۲٪ برای ETF مختلط فرابورس
}

# ===== مالیات واگذاری =====
EXERCISE_TAX_RATE = 0.005         # ۰.۵٪ مالیات واگذاری سهم (فقط فروشنده)

# ===== کارمزد اختیار معامله =====
OPTION_BUY_COMMISSION = 0.00103   # ۰.۱۰۳٪ کارمزد خرید اختیار
OPTION_SELL_COMMISSION = 0.00103  # ۰.۱۰۳٪ کارمزد فروش اختیار

# =====================================================
# دیکشنری کارمزدها (Commission Dictionary)
# =====================================================

COMMISSION_DICT = {
    # ===== سهام (Stock) =====
    # خرید سهام بورس (STOCK, market:1, side:true)
    ('tse', 'stock', True): 0.003712,
    # فروش سهام بورس (STOCK, market:1, side:false)
    ('tse', 'stock', False): 0.0088,
    # خرید سهام فرابورس (STOCK, market:2, side:true)
    ('ifb', 'stock', True): 0.003632,
    # فروش سهام فرابورس (STOCK, market:2, side:false)
    ('ifb', 'stock', False): 0.0088,

    # ===== ETF سهام (ETF Stock) =====
    ('tse', 'etf-stock', True): 0.00232,   # خرید ETF سهام بورس
    ('tse', 'etf-stock', False): 0.002375,  # فروش ETF سهام بورس
    ('ifb', 'etf-stock', True): 0.00232,   # خرید ETF سهام فرابورس
    ('ifb', 'etf-stock', False): 0.002375,  # فروش ETF سهام فرابورس

    # ===== ETF اهرمی (ETF Leverage) =====
    # اضافه شده جهت انطباق با نگاشت تفکیک‌شده نمادهای اهرم، توان و موج
    ('tse', 'etf-leverage', True): 0.00232,
    ('tse', 'etf-leverage', False): 0.002375,
    ('ifb', 'etf-leverage', True): 0.00232,
    ('ifb', 'etf-leverage', False): 0.002375,

    # ===== ETF طلا / کالا (ETF Gold) =====
    # بر اساس داده‌های market:3 و kind:OPTION (یا دارایی‌های کالا) در صورت نیاز به توسعه
    ('tse', 'etf-gold', True): 0.0012,
    ('tse', 'etf-gold', False): 0.0012,

    # ===== ETF درآمد ثابت (ETF Fix) =====
    ('tse', 'etf-fix', True): 0.000375,    # خرید ETF درآمد ثابت بورس
    ('tse', 'etf-fix', False): 0.000375,   # فروش ETF درآمد ثابت بورس
    ('ifb', 'etf-fix', True): 0.000375,    # خرید ETF درآمد ثابت فرابورس
    ('ifb', 'etf-fix', False): 0.000375,   # فروش ETF درآمد ثابت فرابورس

    # ===== ETF مختلط (ETF Mix) =====
    ('tse', 'etf-mix', True): 0.001215,    # خرید ETF مختلط بورس
    # اصلاح شده: فروش ETF مختلط بورس (طبق جیسون: 0.001323)
    ('tse', 'etf-mix', False): 0.001323,
    ('ifb', 'etf-mix', True): 0.001215,    # خرید ETF مختلط فرابورس
    ('ifb', 'etf-mix', False): 0.001323,   # اصلاح شده: فروش ETF مختلط فرابورس

    # ===== اختیار معامله (Option) =====
    ('tse', 'option', True): 0.00103,      # خرید اختیار بورس
    ('tse', 'option', False): 0.00103,     # فروش اختیار بورس
    # اصلاح شده: خرید اختیار فرابورس (طبق جیسون: 0.00102)
    ('ifb', 'option', True): 0.00102,
    ('ifb', 'option', False): 0.00103,     # فروش اختیار فرابورس
}

# =====================================================
# اطلاعات نمادها (Symbol Info)
# =====================================================

SYMBOL_INFO = {
    # ===== سهام بورس (TSE Stock) =====
    'اخابر':    {'IsETF': False, 'Market': 'tse', 'Kind': 'stock'},
    'تاصیکو':   {'IsETF': False, 'Market': 'tse', 'Kind': 'stock'},
    'خبهمن':   {'IsETF': False, 'Market': 'tse', 'Kind': 'stock'},
    'خساپا':   {'IsETF': False, 'Market': 'tse', 'Kind': 'stock'},
    'خودرو':   {'IsETF': False, 'Market': 'tse', 'Kind': 'stock'},
    'ذوب':     {'IsETF': False, 'Market': 'tse', 'Kind': 'stock'},
    'شپنا':    {'IsETF': False, 'Market': 'tse', 'Kind': 'stock'},
    'شستا':    {'IsETF': False, 'Market': 'tse', 'Kind': 'stock'},
    'فملی':    {'IsETF': False, 'Market': 'tse', 'Kind': 'stock'},
    'وبصادر':  {'IsETF': False, 'Market': 'tse', 'Kind': 'stock'},
    'وبملت':   {'IsETF': False, 'Market': 'tse', 'Kind': 'stock'},
    'وتجارت':  {'IsETF': False, 'Market': 'tse', 'Kind': 'stock'},

    # ===== سهام فرابورس (IFB Stock) =====
    'فزر':     {'IsETF': False, 'Market': 'ifb', 'Kind': 'stock'},

    # ===== ETF سهام بورس (TSE ETF Stock) =====
    # صندوق اهرمی بورس
    'اهرم':    {'IsETF': True, 'Market': 'tse', 'Kind': 'etf-leverage'},
    # صندوق شاخصی هم‌وزن بورس
    'هم تراز': {'IsETF': True, 'Market': 'tse', 'Kind': 'etf-stock'},

    # ===== ETF سهام فرابورس (IFB ETF Stock) =====
    # صندوق توسعه اطلس فرابورس
    'اطلس':    {'IsETF': True, 'Market': 'ifb', 'Kind': 'etf-stock'},
    # صندوق اهرمی توان فرابورس
    'توان':    {'IsETF': True, 'Market': 'ifb', 'Kind': 'etf-leverage'},
    # صندوق بخشی فرابورس
    'طعام':    {'IsETF': True, 'Market': 'ifb', 'Kind': 'etf-stock'},
    # صندوق اهرمی موج فرابورس
    'موج':     {'IsETF': True, 'Market': 'ifb', 'Kind': 'etf-leverage'},
}

# =====================================================
# تنظیمات بازه قیمتی برای محاسبه P&L
# =====================================================

PRICE_RANGE_CONFIG = {
    "min_percent": -50,          # حداقل درصد تغییر قیمت
    "max_percent": 50,           # حداکثر درصد تغییر قیمت
    "num_points": 21,            # تعداد نقاط (گام‌ها)
    "step_size": None,           # اگر None باشد، بر اساس num_points محاسبه می‌شود
    "labels_format": "{:.0f}%",  # فرمت برچسب‌ها
}

# =====================================================
# آستانه‌های نقدشوندگی (Liquidity Thresholds)
# =====================================================

DaysToMaturity = 2               # حداقل روز تا سررسید
MIN_VOLUME = 3                   # حداقل حجم معاملات روزانه
MIN_OPEN_INTEREST = 50           # حداقل موقعیت‌های باز
MAX_SPREAD_PCT = 0.05            # حداکثر اسپرد قابل قبول (5%)
LIQUIDITY_SCORE_THRESHOLD = 1.0  # آستانه امتیاز نقدشوندگی
DEFAULT_DEPTH_THRESHOLD = 30     # آستانه عمق سفارشات

# =====================================================
# نرخ بهره و نوسان‌پذیری (Rates & Volatility)
# =====================================================

RISK_FREE_RATE = 0.24            # نرخ بدون ریسک سالانه (23%)
RISK_FREE_RATE_MONTHLY = 0.019   # نرخ بدون ریسک ماهانه (1.9%)
DEFAULT_VOLATILITY = 0.30        # نوسان‌پذیری پیش‌فرض (30%)
HISTORICAL_VOLATILITY_WINDOW = 30  # پنجره محاسبه نوسان تاریخی (روز)

# =====================================================
# تنظیمات کش (Cache Settings)
# =====================================================

CACHE_TTL_SECONDS = 6           # زمان انقضای کش (ثانیه)
MAX_CACHE_SIZE = 10000           # حداکثر تعداد آیتم‌های کش
CACHE_ENABLED = True             # فعال/غیرفعال کردن کش

# =====================================================
# تنظیمات دانلود داده (Download Settings)
# =====================================================

DOWNLOAD_CONFIG = {
    "use_dns_bypass": True,
    "max_attempts": 3,
    "retry_delay": 5,
    "timeout": 30,
}

# =====================================================
# تنظیمات موتور اسکنر (Scanner Settings)
# =====================================================

SCANNER_CONFIG = {
    "min_volume": MIN_VOLUME,
    "min_open_interest": MIN_OPEN_INTEREST,
    "max_spread_pct": MAX_SPREAD_PCT,
    "min_liquidity_score": LIQUIDITY_SCORE_THRESHOLD,
    "ignore_frozen_underlying": True
}

# =====================================================
# استراتژی‌های هدف برای اسکن (Target Strategies)
# =====================================================

ACTIVE_STRATEGIES: List[str] = [
    "bull_call_spread",
    "bear_put_spread",
    "collar",
    "conversion",
    "covered_call",
    "iron_condor",
    "long_box",
    "long_guts",
    "long_straddle",
    "long_strangle",
    "married_put",
    "strip",
    "strap",
]

# =====================================================
# پروفایل‌های رتبه‌بندی (Ranking Profiles)
# =====================================================

RANKING_WEIGHTS: Dict[str, Dict[str, float]] = {
    "conservative": {
        "win_rate": 0.35,
        "risk_reward": 0.10,
        "rom": 0.10,
        "margin_efficiency": 0.15,
        "max_profit": 0.05,
        "max_loss": 0.25,
    },
    "balanced": {
        "win_rate": 0.25,
        "risk_reward": 0.15,
        "rom": 0.20,
        "margin_efficiency": 0.15,
        "max_profit": 0.10,
        "max_loss": 0.15,
    },
    "aggressive": {
        "win_rate": 0.10,
        "risk_reward": 0.15,
        "rom": 0.35,
        "margin_efficiency": 0.15,
        "max_profit": 0.15,
        "max_loss": 0.10,
    },
    "income": {
        "win_rate": 0.30,
        "risk_reward": 0.10,
        "rom": 0.25,
        "margin_efficiency": 0.20,
        "max_profit": 0.05,
        "max_loss": 0.10,
    },
    "volatility": {
        "win_rate": 0.10,
        "risk_reward": 0.30,
        "rom": 0.15,
        "margin_efficiency": 0.05,
        "max_profit": 0.25,
        "max_loss": 0.15,
    },
}

DEFAULT_PROFILE = "balanced"

# =====================================================
# تنظیمات رتبه‌بندی (Ranking Settings)
# =====================================================

RANKING_CONFIG = {
    "default_profile": DEFAULT_PROFILE,
    "min_score_threshold": 20.0,
    "min_profit_threshold": 0.0,
    "top_n_results": 20,
}

# =====================================================
# تنظیمات خروجی Excel (Excel Output Settings)
# =====================================================

EXCEL_CONFIG = {
    "top_n": 40,
    "min_score_threshold": 30.0,
    "include_chart_data": True,
    "include_help_sheet": True,
    "show_liquidity_score": True,
    "currency_format": "#,##0;[Red](#,##0);\"-\"",
    "percent_format": "0.0%",
    "decimal_format": "0.00",
    "integer_format": "#,##0",
}

# =====================================================
# تنظیمات خروجی (Output Settings)
# =====================================================

OUTPUT_CONFIG = {
    "top_n": 250,
    "min_score_threshold": 5.0,
    "include_chart_data": False,
    "excel_filename": "opportunities",
}

# =====================================================
# تنظیمات گزارش و نمودار (Report & Chart Settings)
# =====================================================

CHART_CONFIG = {
    "dpi": 150,
    "style": "seaborn-v0_8-whitegrid",
    "figsize": (11, 7),
}

# =====================================================
# تنظیمات عمومی سیستم (Logging & Environment)
# =====================================================

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        },
        "detailed": {
            "format": "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "level": "INFO",
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": str(LOGS_DIR / "scanner_execution.log"),
            "encoding": "utf-8",
            "formatter": "detailed",
            "level": "DEBUG",
        }
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
}

# =====================================================
# تنظیمات عمومی سیستم (General Settings)
# =====================================================

SYSTEM_CONFIG = {
    "scan_interval_minutes": 2,     # فاصله زمانی بین هر چرخه (دقیقه)
    "max_cycles": 1,                # تعداد دفعات اجرا (0 = بی‌نهایت)
    "parallel_enabled": False,
    "max_workers": 3,
    "debug_mode": False,
}

# =====================================================
# تنظیمات ویژگی‌های محاسباتی (Feature Flags)
# =====================================================

FEATURE_FLAGS = {
    # اگر True باشد، وجه تضمین (مارجین) محاسبه و در required_margin ذخیره می‌شود
    # اگر False باشد، required_margin = 0 خواهد بود
    "calculate_margin": True,

    # اگر True باشد، کارمزد معاملاتی (کارگزاری + بورس + پایاپای) از سود/زیان کسر می‌شود
    # اگر False باشد، P&L ناخالص بدون کسر کارمزد گزارش می‌شود
    "apply_commissions": True,

    # کارمزد اعمال/تسویه فیزیکی در سررسید برای موقعیت‌های ITM خریدار
    "apply_exercise_fee": True,


    # اگر True باشد، یونانی‌ها (Delta, Gamma, Theta, Vega) محاسبه شده
    # و در ستون‌های اکسل نمایش داده می‌شوند
    "calculate_greeks": False,

    # اگر True باشد، Risk Metrics (POP, Sharpe, VaR, ...) محاسبه شود
    "calculate_risk_metrics": True,

    # نوع تسویه در سررسید: 'CASH' (نقدی) یا 'PHYSICAL' (فیزیکی)
    # در حالت PHYSICAL، مالیات واگذاری (۰.۵٪) به صورت خودکار اعمال می‌شود.
    # در حالت CASH، مالیات واگذاری به صورت خودکار صفر در نظر گرفته می‌شود.
    "exercise_settlement_type": "PHYSICAL",

    # فعال‌سازی فالبک به قیمت نظری در صورت عدم وجود معامله در روز (ماده ۲۴)
    "use_theoretical_price_fallback": False,
}


def get_feature_flags() -> Dict[str, bool]:
    """دریافت تنظیمات ویژگی‌های محاسباتی"""
    return FEATURE_FLAGS.copy()

# =====================================================
# توابع کمکی (Helper Functions)
# =====================================================


def get_ranking_weights(profile: str = DEFAULT_PROFILE) -> Dict[str, float]:
    """دریافت وزن‌های رتبه‌بندی برای یک پروفایل خاص"""
    return RANKING_WEIGHTS.get(profile, RANKING_WEIGHTS[DEFAULT_PROFILE])


def get_active_strategies() -> List[str]:
    """دریافت لیست استراتژی‌های فعال"""
    return ACTIVE_STRATEGIES.copy()


def get_scanner_config() -> Dict[str, Any]:
    """دریافت تنظیمات اسکنر"""
    return SCANNER_CONFIG.copy()


def get_output_config() -> Dict[str, Any]:
    """دریافت تنظیمات خروجی"""
    return OUTPUT_CONFIG.copy()


def get_excel_config() -> Dict[str, Any]:
    """دریافت تنظیمات خروجی Excel"""
    return EXCEL_CONFIG.copy()


def get_ranking_config() -> Dict[str, Any]:
    """دریافت تنظیمات رتبه‌بندی"""
    return RANKING_CONFIG.copy()


def get_chart_config() -> Dict[str, Any]:
    """دریافت تنظیمات نمودار"""
    return CHART_CONFIG.copy()


def get_system_config() -> Dict[str, Any]:
    """دریافت تنظیمات عمومی سیستم"""
    return SYSTEM_CONFIG.copy()


def get_cache_config() -> Dict[str, Any]:
    """دریافت تنظیمات کش"""
    return {
        "ttl_seconds": CACHE_TTL_SECONDS,
        "max_size": MAX_CACHE_SIZE,
        "enabled": CACHE_ENABLED,
        "directory": str(CACHE_DIR),
    }


def get_liquidity_config() -> Dict[str, Any]:
    """دریافت تنظیمات نقدشوندگی"""
    return {
        "min_volume": MIN_VOLUME,
        "min_open_interest": MIN_OPEN_INTEREST,
        "max_spread_pct": MAX_SPREAD_PCT,
        "threshold": LIQUIDITY_SCORE_THRESHOLD,
        "depth_threshold": DEFAULT_DEPTH_THRESHOLD,
    }


def get_fee_config() -> Dict[str, Any]:
    """دریافت تنظیمات کارمزدها"""
    return {
        "exercise_fee_rate": EXERCISE_FEE_RATE,
        "exercise_tax_rate": EXERCISE_TAX_RATE,
        "option_buy_commission": OPTION_BUY_COMMISSION,
        "option_sell_commission": OPTION_SELL_COMMISSION,
    }


def get_commission_rate(
        market: str,
        asset_type: str,
        is_buy: bool) -> float:
    """
    دریافت نرخ کارمزد بر اساس نوع بازار و دارایی
    """
    key = (market, asset_type, is_buy)
    return COMMISSION_DICT.get(key)  # مقدار پیش‌فرض


def get_exercise_fee_rate(market: str, kind: str) -> float:
    """
    دریافت نرخ کارمزد اعمال بر اساس بازار و نوع دارایی
    """
    key = (market, kind)
    return EXERCISE_FEE_RATE.get(key)  # ۰.۱٪ پیش‌فرض


def get_symbol_info(symbol: str) -> Optional[Dict[str, Any]]:
    """دریافت اطلاعات یک نماد"""
    return SYMBOL_INFO.get(symbol)


def is_symbol_etf(symbol: str) -> bool:
    """بررسی اینکه آیا نماد ETF است"""
    info = get_symbol_info(symbol)
    return info.get('IsETF', False) if info else False


def get_symbol_market(symbol: str) -> str:
    """دریافت بازار نماد ('tse' یا 'ifb')"""
    info = get_symbol_info(symbol)
    return info.get('Market', 'tse') if info else 'tse'


def get_symbol_kind(symbol: str) -> str:
    """دریافت نوع نماد ('stock', 'etf-stock', 'etf-gold', etc.)"""
    info = get_symbol_info(symbol)
    return info.get('Kind', 'stock') if info else 'stock'


def get_price_steps() -> np.ndarray:
    """تولید آرایه درصدهای تغییر قیمت بر اساس تنظیمات کاربر"""
    config = PRICE_RANGE_CONFIG
    min_pct = config["min_percent"]
    max_pct = config["max_percent"]
    num_points = config["num_points"]

    if num_points <= 1:
        return np.array([0.0], dtype=np.float64)

    step_size = config.get("step_size")
    if step_size is not None:
        steps = np.arange(min_pct, max_pct + step_size, step_size)
        return np.round(steps, 2)

    steps = np.linspace(min_pct, max_pct, num_points)
    return np.round(steps, 2)


def get_price_labels(steps: np.ndarray = None) -> List[str]:
    """تولید برچسب‌های قیمتی برای نمایش در Excel"""
    if steps is None:
        steps = get_price_steps()

    format_str = PRICE_RANGE_CONFIG.get("labels_format", "{:.0f}%")
    return [format_str.format(s) for s in steps]


def get_price_levels(S0_stock: float) -> np.ndarray:
    """تولید سطوح قیمت مطلق بر اساس S0"""
    pct_steps = get_price_steps()
    return np.round(S0_stock * (1 + pct_steps / 100.0), 0)
