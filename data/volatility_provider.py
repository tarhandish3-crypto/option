# data/volatility_provider.py
# -*- coding: utf-8 -*-

"""
Provider برای خواندن Historical_Volatility.xlsx.

این فایل، در ابتدای اجرای برنامه بارگذاری می‌شود و در حافظه
نگه‌داری می‌گردد. در طول اسکن، فقط از حافظه خوانده می‌شود.

داده‌های استخراج‌شده:
    - HV_60: نوسان تاریخی ۶۰ روزه (اصلی برای M_risk)
    - VolatilityQualityScore (VQ): امتیاز کیفیت نوسان (۰-۱۰)
    - LongTrend, RelativeReturn_1Y, Alpha
    - RecoveryStrength, TechnicalDecline, BuyerStrength
    - RSI_14, SupportProximity, ResistanceProximity
    - LastPrice

نحوه استفاده:
    from data.volatility_provider import preload_volatility, get_vq
    
    # یک بار در ابتدای اجرا
    ok = preload_volatility()
    if not ok:
        # فایل نیست — پیغام به کاربر
    
    # هر جا لازم شد
    vq = get_vq("فزر")
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional

import pandas as pd

logger = logging.getLogger("OptionScanner.Data.VolatilityProvider")


# ═══════════════════════════════════════════════════════════════
# ثابت‌ها
# ═══════════════════════════════════════════════════════════════

# مسیر ریشه‌ی پروژه (generate_strategyV4/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# مسیر فایل VQ
_VOLATILITY_FILE = _PROJECT_ROOT / "0myStrategy" / "Historical_Volatility.xlsx"

# مقادیر پیش‌فرض (در صورت نبود نماد در فایل)
_DEFAULT_VQ = 5.0
_DEFAULT_HV_60 = 0.30
_DEFAULT_HV_20 = 0.30
_DEFAULT_HV_120 = 0.30
_DEFAULT_RSI = 50.0
_DEFAULT_LAST_PRICE = 0.0


# ═══════════════════════════════════════════════════════════════
# State درون‌حافظه‌ای
# ═══════════════════════════════════════════════════════════════

_VOLATILITY_CACHE: Dict[str, Dict[str, Any]] = {}
_IS_LOADED: bool = False
_LOAD_ERROR: Optional[str] = None
_LOAD_LOCK = threading.Lock()


# ═══════════════════════════════════════════════════════════════
# API عمومی
# ═══════════════════════════════════════════════════════════════

def preload_volatility(force: bool = False) -> bool:
    """
    بارگذاری Historical_Volatility.xlsx در حافظه.

    اگر قبلاً بارگذاری شده و force=False باشد، دوباره نمی‌خواند.

    Args:
        force: اگر True، حتی اگر قبلاً بارگذاری شده، دوباره بخوان.

    Returns:
        True اگر فایل موجود و بارگذاری موفق بود.
        False اگر فایل نبود یا خطا داشت.
    """
    global _IS_LOADED, _LOAD_ERROR

    with _LOAD_LOCK:
        if _IS_LOADED and not force:
            return True

        # پاک‌سازی کش قبلی
        _VOLATILITY_CACHE.clear()
        _IS_LOADED = False
        _LOAD_ERROR = None

        # بررسی وجود فایل
        if not _VOLATILITY_FILE.exists():
            msg = f"Volatility file not found: {_VOLATILITY_FILE}"
            logger.error(msg)
            _LOAD_ERROR = "FILE_NOT_FOUND"
            return False

        # تلاش برای خواندن
        try:
            n_loaded = _load_from_excel()
            _IS_LOADED = True
            logger.info(
                f"Volatility loaded: {n_loaded} symbols from "
                f"{_VOLATILITY_FILE.name}"
            )
            return True

        except Exception as e:
            msg = f"Failed to load volatility file: {e}"
            logger.error(msg, exc_info=True)
            _LOAD_ERROR = f"LOAD_ERROR: {e}"
            _VOLATILITY_CACHE.clear()
            return False


def is_loaded() -> bool:
    """آیا فایل با موفقیت بارگذاری شده؟"""
    return _IS_LOADED


def get_load_error() -> Optional[str]:
    """دریافت پیغام خطای آخرین بارگذاری (اگر خطا داشته)."""
    return _LOAD_ERROR


def get_volatility(ticker: str) -> Dict[str, Any]:
    """
    دریافت کل داده‌ی نوسان یک نماد.

    اگر نماد در فایل نباشد، مقادیر پیش‌فرض برمی‌گردد.
    """
    if not _IS_LOADED:
        # تلاش برای بارگذاری در لحظه (اگر قبلاً نشده)
        preload_volatility()

    normalized = _normalize_ticker(ticker)
    if normalized in _VOLATILITY_CACHE:
        return _VOLATILITY_CACHE[normalized]

    # نماد در فایل نیست
    logger.debug(f"Volatility not found for '{ticker}', using defaults")
    return _get_defaults()


def get_vq(ticker: str) -> float:
    """دریافت VQ با fallback به 5.0"""
    data = get_volatility(ticker)
    return float(data.get("VolatilityQualityScore", _DEFAULT_VQ))


def get_hv_60(ticker: str) -> float:
    """دریافت HV_60 با fallback به 0.30"""
    data = get_volatility(ticker)
    return float(data.get("HV_60", _DEFAULT_HV_60))


def get_all_loaded_tickers() -> list[str]:
    """دریافت لیست همه‌ی نمادهای بارگذاری‌شده."""
    return list(_VOLATILITY_CACHE.keys())


def get_file_path() -> str:
    """دریافت مسیر فایل VQ (برای نمایش به کاربر)."""
    return str(_VOLATILITY_FILE)


def clear_cache() -> None:
    """پاک کردن کش (برای تست یا بارگذاری مجدد)."""
    global _IS_LOADED, _LOAD_ERROR
    with _LOAD_LOCK:
        _VOLATILITY_CACHE.clear()
        _IS_LOADED = False
        _LOAD_ERROR = None


# ═══════════════════════════════════════════════════════════════
# توابع کمکی
# ═══════════════════════════════════════════════════════════════

def _load_from_excel() -> int:
    """
    خواندن فایل اکسل و پر کردن کش.

    Returns:
        تعداد نمادهای بارگذاری‌شده.
    """
    df = pd.read_excel(_VOLATILITY_FILE)

    if df.empty:
        raise ValueError("Volatility file is empty")

    # بررسی وجود ستون کلیدی
    if "UnderlyingTicker" not in df.columns:
        raise ValueError(
            f"Missing required column 'UnderlyingTicker'. "
            f"Available: {list(df.columns)}"
        )

    loaded = 0
    for _, row in df.iterrows():
        ticker_raw = row.get("UnderlyingTicker")
        if pd.isna(ticker_raw) or not str(ticker_raw).strip():
            continue

        ticker = _normalize_ticker(str(ticker_raw))
        _VOLATILITY_CACHE[ticker] = {
            # نوسان‌ها
            "HV_20": _safe_float(row.get("HV_20"), _DEFAULT_HV_20),
            "HV_60": _safe_float(row.get("HV_60"), _DEFAULT_HV_60),
            "HV_120": _safe_float(row.get("HV_120"), _DEFAULT_HV_120),
            "VolatilityRatio": _safe_float(row.get("VolatilityRatio"), 1.0),
            "TrendSlope": _safe_float(row.get("TrendSlope"), 0.0),
            "LongTrend": _safe_float(row.get("LongTrend"), 0.0),
            # افت‌ها
            "MaxDrawdown_20": _safe_float(row.get("MaxDrawdown_20"), 0.0),
            "MaxDrawdown_60": _safe_float(row.get("MaxDrawdown_60"), 0.0),
            "MaxDrawdown_120": _safe_float(row.get("MaxDrawdown_120"), 0.0),
            # بازگشت و افت تکنیکال
            "RecoveryStrength": _safe_float(row.get("RecoveryStrength"), 0.0),
            "TechnicalDecline": _safe_float(row.get("TechnicalDecline"), 0.0),
            # تحلیل‌های خریدار
            "RSI_14": _safe_float(row.get("RSI_14"), _DEFAULT_RSI),
            "BuyerStrength": _safe_float(row.get("BuyerStrength"), 0.0),
            "SupportProximity": _safe_float(row.get("SupportProximity"), 0.0),
            "ResistanceProximity": _safe_float(row.get("ResistanceProximity"), 0.0),
            # بازدهی نسبی و بتا/آلفا
            "RelativeReturn_6M": _safe_float(row.get("RelativeReturn_6M"), 0.0),
            "RelativeReturn_1Y": _safe_float(row.get("RelativeReturn_1Y"), 0.0),
            "Beta": _safe_float(row.get("Beta"), 1.0),
            "Alpha": _safe_float(row.get("Alpha"), 0.0),
            # قیمت
            "LastPrice": _safe_float(row.get("LastPrice"), _DEFAULT_LAST_PRICE),
            # VQ نهایی
            "VolatilityQualityScore": _safe_float(
                row.get("VolatilityQualityScore"), _DEFAULT_VQ
            ),
        }
        loaded += 1

    return loaded


def _safe_float(val: Any, default: float = 0.0) -> float:
    """تبدیل ایمن به float با مدیریت NaN."""
    if val is None:
        return default
    try:
        if pd.isna(val):
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


def _normalize_ticker(t: str) -> str:
    """نرمال‌سازی نماد (ی/ک عربی → فارسی)."""
    if not t:
        return ""
    return str(t).strip().replace("ي", "ی").replace("ك", "ک")


def _get_defaults() -> Dict[str, Any]:
    """مقادیر پیش‌فرض برای نمادی که در فایل نیست."""
    return {
        "HV_20": _DEFAULT_HV_20,
        "HV_60": _DEFAULT_HV_60,
        "HV_120": _DEFAULT_HV_120,
        "VolatilityRatio": 1.0,
        "TrendSlope": 0.0,
        "LongTrend": 0.0,
        "MaxDrawdown_20": 0.0,
        "MaxDrawdown_60": 0.0,
        "MaxDrawdown_120": 0.0,
        "RecoveryStrength": 0.0,
        "TechnicalDecline": 0.0,
        "RSI_14": _DEFAULT_RSI,
        "BuyerStrength": 0.0,
        "SupportProximity": 0.0,
        "ResistanceProximity": 0.0,
        "RelativeReturn_6M": 0.0,
        "RelativeReturn_1Y": 0.0,
        "Beta": 1.0,
        "Alpha": 0.0,
        "LastPrice": _DEFAULT_LAST_PRICE,
        "VolatilityQualityScore": _DEFAULT_VQ,
    }


__all__ = [
    "preload_volatility",
    "is_loaded",
    "get_load_error",
    "get_volatility",
    "get_vq",
    "get_hv_60",
    "get_all_loaded_tickers",
    "get_file_path",
    "clear_cache",
]