# -*- coding: utf-8 -*-

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np

# تنظیم لاگر اختصاصی ماژول کانفیگ
logger = logging.getLogger("OptionScanner.Config")

# =====================================================
# مسیرهای اصلی پروژه (Directory Structure)
# =====================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = BASE_DIR / "output"
CHARTS_DIR = OUTPUT_DIR / "charts"
LOGS_DIR = BASE_DIR / "logs"
CONFIG_DIR = BASE_DIR / "config"
USER_SETTINGS_PATH = BASE_DIR / "user_settings.json"

# تضمین ایجاد پوشه‌های حیاتی در بدو اجرای برنامه
for directory in [DATA_DIR, CACHE_DIR, OUTPUT_DIR, CHARTS_DIR, LOGS_DIR, CONFIG_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# =====================================================
# کارمزدها و مالیات (Fees & Taxes)
# =====================================================

# ===== کارمزد اعمال بر اساس نوع دارایی (طبق تعرفه سمات) =====
EXERCISE_FEE_RATE: Dict[tuple, float] = {
    ('tse', 'stock'): 0.0005,        # ۰.۱٪ برای سهام عادی
    ('ifb', 'stock'): 0.0005,        # ۰.۱٪ برای سهام فرابورس
    ('tse', 'etf-stock'): 0.0005,   # ۰.۰۵٪ برای ETF سهامی
    ('ifb', 'etf-stock'): 0.0005,   # ۰.۰۵٪ برای ETF سهامی فرابورس
    ('tse', 'etf-leverage'): 0.0005,  # صندوق های اهرمی
    ('ifb', 'etf-leverage'): 0.0005,
    ('tse', 'etf-fix'): 0.0005,     # ۰.۰۲٪ برای ETF درآمد ثابت
    ('ifb', 'etf-fix'): 0.0005,     # ۰.۰۲٪ برای ETF درآمد ثابت فرابورس
    ('tse', 'etf-gold'): 0.0005,    # ۰.۰۵٪ برای ETF طلا
    ('ifb', 'etf-gold'): 0.0005,    # ۰.۰۵٪ برای ETF طلا فرابورس
    ('tse', 'etf-mix'): 0.0005,     # ۰.۰۲٪ برای ETF مختلط
    ('ifb', 'etf-mix'): 0.0005,     # ۰.۰۲٪ برای ETF مختلط فرابورس
}

# ===== مالیات واگذاری =====
EXERCISE_TAX_RATE = 0.005         # ۰.۵٪ مالیات واگذاری سهم (فقط فروشنده)


# =====================================================
# دیکشنری کارمزدها (Commission Dictionary)
# =====================================================

COMMISSION_DICT = {
    # ===== سهام (Stock) =====
    ('tse', 'stock', True): 0.003712,
    ('tse', 'stock', False): 0.0088,
    ('ifb', 'stock', True): 0.003632,
    ('ifb', 'stock', False): 0.0088,

    # ===== ETF سهام (ETF Stock) =====
    ('tse', 'etf-stock', True): 0.00232,
    ('tse', 'etf-stock', False): 0.002375,
    ('ifb', 'etf-stock', True): 0.00232,
    ('ifb', 'etf-stock', False): 0.002375,

    # ===== ETF اهرمی (ETF Leverage) =====
    ('tse', 'etf-leverage', True): 0.00232,
    ('tse', 'etf-leverage', False): 0.002375,
    ('ifb', 'etf-leverage', True): 0.00232,
    ('ifb', 'etf-leverage', False): 0.002375,

    # ===== ETF طلا / کالا (ETF Gold) =====
    ('tse', 'etf-gold', True): 0.0012,
    ('tse', 'etf-gold', False): 0.0012,

    # ===== ETF درآمد ثابت (ETF Fix) =====
    ('tse', 'etf-fix', True): 0.000375,
    ('tse', 'etf-fix', False): 0.000375,
    ('ifb', 'etf-fix', True): 0.000375,
    ('ifb', 'etf-fix', False): 0.000375,

    # ===== ETF مختلط (ETF Mix) =====
    ('tse', 'etf-mix', True): 0.001215,
    ('tse', 'etf-mix', False): 0.001323,
    ('ifb', 'etf-mix', True): 0.001215,
    ('ifb', 'etf-mix', False): 0.001323,

    # ===== اختیار معامله (Option) =====
    ('tse', 'option', True): 0.001,
    ('tse', 'option', False): 0.001,
    ('ifb', 'option', True): 0.001,
    ('ifb', 'option', False): 0.001,
}

# =====================================================
# اطلاعات نمادها (Symbol Info)
# =====================================================

SYMBOL_INFO = {
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
    'فزر':     {'IsETF': False, 'Market': 'ifb', 'Kind': 'stock'},
    'اهرم':    {'IsETF': True, 'Market': 'tse', 'Kind': 'etf-leverage'},
    'هم تراز': {'IsETF': True, 'Market': 'tse', 'Kind': 'etf-stock'},
    'اطلس':    {'IsETF': True, 'Market': 'ifb', 'Kind': 'etf-stock'},
    'توان':    {'IsETF': True, 'Market': 'ifb', 'Kind': 'etf-leverage'},
    'طعام':    {'IsETF': True, 'Market': 'ifb', 'Kind': 'etf-stock'},
    'موج':     {'IsETF': True, 'Market': 'ifb', 'Kind': 'etf-leverage'},
}

# =====================================================
# تنظیمات پیش‌فرض بازه قیمتی (Fallback Price Range)
# =====================================================

PRICE_RANGE_CONFIG = {
    "min_percent": -45,
    "max_percent": 45,
    "num_points": 21,
    "step_size": None,
    "labels_format": "{:.0f}%",
}

# =====================================================
# آستانه‌های پیش‌فرض نقدشوندگی (Fallback Values)
# =====================================================

DaysToMaturity = 1
MIN_VOLUME = 3
MIN_OPEN_INTEREST = 50
MAX_SPREAD_PCT = 0.05
LIQUIDITY_SCORE_THRESHOLD = 1.0
DEFAULT_DEPTH_THRESHOLD = 30

# =====================================================
# نرخ بهره و نوسان‌پذیری (Rates & Volatility)
# =====================================================

RISK_FREE_RATE = 0.24
RISK_FREE_RATE_MONTHLY = 0.019
DEFAULT_VOLATILITY = 0.30
HISTORICAL_VOLATILITY_WINDOW = 30

# =====================================================
# تنظیمات کش (Cache Settings)
# =====================================================

CACHE_TTL_SECONDS = 6
MAX_CACHE_SIZE = 10000
CACHE_ENABLED = True

# =====================================================
# تنظیمات عمومی سیستم (General Settings)
# =====================================================

SYSTEM_CONFIG = {
    "scan_interval_minutes": 2,
    "max_cycles": 1,
    "parallel_enabled": False,
    "max_workers": 3,
    "debug_mode": False,
}

# =====================================================
# تنظیمات ویژگی‌های محاسباتی (Feature Flags)
# =====================================================

FEATURE_FLAGS = {
    "calculate_margin": True,
    "apply_commissions": True,
    "apply_exercise_fee": True,
    "calculate_greeks": False,
    "calculate_risk_metrics": True,
    "exercise_settlement_type": "PHYSICAL",
    "use_theoretical_price_fallback": False,
}

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
# استراتژی‌های پیش‌فرض هدف برای اسکن (Fallback Strategies)
# =====================================================

ACTIVE_STRATEGIES: List[str] = [
    "bull_call_spread",
    "bear_put_spread",
    "collar",
    "conversion",
    "covered_call",
    "iron_condor",
    "long_guts",
    "long_straddle",
    "married_put",
    "strip",
    "strap",
    "long_call",
    "long_put",
]

# =====================================================
# پروفایل‌های رتبه‌بندی (Ranking Profiles)
# =====================================================

RANKING_WEIGHTS: Dict[str, Dict[str, float]] = {
    "conservative": {
        "risk_reward": 0.10,
        "rom": 0.10,
        "margin_efficiency": 0.15,
        "max_profit": 0.05,
        "max_loss": 0.25,
    },
    "balanced": {
        "risk_reward": 0.15,
        "rom": 0.20,
        "margin_efficiency": 0.15,
        "max_profit": 0.10,
        "max_loss": 0.15,
    },
    "aggressive": {
        "risk_reward": 0.15,
        "rom": 0.35,
        "margin_efficiency": 0.15,
        "max_profit": 0.15,
        "max_loss": 0.10,
    },
    "income": {
        "risk_reward": 0.10,
        "rom": 0.25,
        "margin_efficiency": 0.20,
        "max_profit": 0.05,
        "max_loss": 0.10,
    },
    "volatility": {
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
# تنظیمات خروجی Excel و Output
# =====================================================

EXCEL_CONFIG = {
    "top_n": 40,
    "min_score_threshold": 30.0,
    "include_chart_data": True,
    "include_help_sheet": True,
    "show_liquidity_score": True,
    "currency_format": '#,##0;[Red](#,##0);"-"',
    "percent_format": "0.0%",
    "decimal_format": "0.00",
    "integer_format": "#,##0",
}

OUTPUT_CONFIG = {
    "top_n": 250,
    "min_score_threshold": 5.0,
    "include_chart_data": False,
    "excel_filename": "opportunities",
}

CHART_CONFIG = {
    "dpi": 150,
    "style": "seaborn-v0_8-whitegrid",
    "figsize": (11, 7),
}

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
        "detailed": {
            "format": "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s"
        },
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
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": "INFO",
    },
}


# =====================================================
# توابع خواندن تنظیمات کاربر (User Settings Helpers)
# =====================================================

def get_active_user_settings() -> dict:
    """خواندن ایمن تنظیمات پروفایل فعال از user_settings.json"""
    if not USER_SETTINGS_PATH.exists():
        return {}
    try:
        with open(USER_SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                return {}
            active_profile = data.get("active_profile", "default")
            profiles = data.get("profiles", {})
            return profiles.get(active_profile, {})
    except Exception as e:
        logger.warning(f"Failed to read user_settings.json: {e}")
        return {}


def get_active_strategies() -> List[str]:
    """دریافت لیست استراتژی‌های فعال با اولویت تنظیمات کاربر"""
    user_settings = get_active_user_settings()
    strategies = user_settings.get("active_strategies", ACTIVE_STRATEGIES)
    return list(strategies).copy()


def get_price_steps() -> np.ndarray:
    """تولید آرایه درصدهای تغییر قیمت بر اساس تنظیمات پویا کاربر"""
    user_settings = get_active_user_settings()
    config = user_settings.get("price_range", PRICE_RANGE_CONFIG)

    min_pct = config.get("min_percent", -45)
    max_pct = config.get("max_percent", 45)
    num_points = config.get("num_points", 21)

    if num_points <= 1:
        return np.array([0.0], dtype=np.float64)

    step_size = config.get("step_size")
    if step_size is not None:
        steps = np.arange(min_pct, max_pct + step_size, step_size)
        return np.round(steps, 2)

    steps = np.linspace(min_pct, max_pct, num_points)
    return np.round(steps, 2)


def get_liquidity_config() -> Dict[str, Any]:
    """
    دریافت آستانه‌های نقدشوندگی با اولویت تنظیمات کاربر
    و مقداردهی Fallback از ثابت‌های سیستمی
    """
    user_settings = get_active_user_settings()

    min_vol = float(user_settings.get("min_volume", MIN_VOLUME))
    min_oi = int(user_settings.get("min_open_interest", MIN_OPEN_INTEREST))
    max_spread = float(user_settings.get("max_spread_pct", MAX_SPREAD_PCT))
    score_thresh = float(user_settings.get(
        "liquidity_score_threshold", LIQUIDITY_SCORE_THRESHOLD))
    depth_thresh = int(user_settings.get(
        "default_depth_threshold", DEFAULT_DEPTH_THRESHOLD))

    return {
        "days_to_maturity": int(user_settings.get("min_days_to_maturity", DaysToMaturity)),
        "max_days_to_maturity": int(user_settings.get("max_days_to_maturity", 365)),
        "min_volume": min_vol,
        "min_open_interest": min_oi,
        "max_spread_pct": max_spread,
        "liquidity_score_threshold": score_thresh,
        "threshold": score_thresh,              # پشتیبانی از کدهای قدیمی
        "default_depth_threshold": depth_thresh,
        "depth_threshold": depth_thresh,        # پشتیبانی از کدهای قدیمی
    }


def get_scanner_config() -> Dict[str, Any]:
    """دریافت تنظیمات اسکنر با اولویت تنظیمات کاربر"""
    liq_cfg = get_liquidity_config()
    return {
        "min_volume": liq_cfg["min_volume"],
        "min_open_interest": liq_cfg["min_open_interest"],
        "max_spread_pct": liq_cfg["max_spread_pct"],
        "min_liquidity_score": liq_cfg["threshold"],
        "ignore_frozen_underlying": True,
    }


# =====================================================
# توابع کمکی عمومی (General Helper Functions)
# =====================================================

def get_feature_flags() -> Dict[str, bool]:
    """دریافت تنظیمات ویژگی‌های محاسباتی"""
    return FEATURE_FLAGS.copy()


def get_ranking_weights(profile: str = DEFAULT_PROFILE) -> Dict[str, float]:
    """دریافت وزن‌های رتبه‌بندی برای یک پروفایل خاص"""
    return RANKING_WEIGHTS.get(profile, RANKING_WEIGHTS[DEFAULT_PROFILE])


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


def get_fee_config() -> Dict[str, Any]:
    """دریافت تنظیمات کارمزدها"""
    return {
        "exercise_fee_rate": EXERCISE_FEE_RATE,
        "exercise_tax_rate": EXERCISE_TAX_RATE,
    }


def get_commission_rate(
        market: str,
        asset_type: str,
        is_buy: bool) -> float:
    """دریافت نرخ کارمزد بر اساس نوع بازار و دارایی"""
    key = (market, asset_type, is_buy)
    return COMMISSION_DICT.get(key)


def get_exercise_fee_rate(market: str, kind: str) -> float:
    """دریافت نرخ کارمزد اعمال بر اساس بازار و نوع دارایی"""
    key = (market, kind)
    return EXERCISE_FEE_RATE.get(key)


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


def get_price_labels(steps: np.ndarray = None) -> List[str]:
    """تولید برچسب‌های قیمتی برای نمایش در Excel"""
    if steps is None:
        steps = get_price_steps()

    user_settings = get_active_user_settings()
    config = user_settings.get("price_range", PRICE_RANGE_CONFIG)
    format_str = config.get("labels_format", "{:.0f}%")
    return [format_str.format(s) for s in steps]


def get_price_levels(S0_stock: float) -> np.ndarray:
    """تولید سطوح قیمت مطلق بر اساس S0"""
    pct_steps = get_price_steps()
    return np.round(S0_stock * (1 + pct_steps / 100.0), 0)
