# data/manager.py

"""
مدیر یکپارچه داده - ارکستراتور دانلود، پاکسازی، محاسبات و ساخت تصویر بازار

این ماژول مسئول:
    1. هماهنگی بین دانلودر، پاکساز، محاسبه‌گر و تبدیل به دیتامدل نهایی
    2. مدیریت کش هوشمند با مکانیسم TTL بر روی کپسول دیتامدل
    3. Fallback خودکار بین منابع داده چندگانه
    4. ارائه درگاه واحد واحد برای تغذیه ScannerEngine
"""

import logging
import pickle
from pathlib import Path
from datetime import datetime
from typing import Optional
import pandas as pd

from data.downloader import MarketDownloader
from data.cleaner import DataCleaner
from analytics.graaks_calculator import calculate_greeks_vectorized, get_risk_free_rate
from core.models import MarketSnapshot
from config import CACHE_DIR, CACHE_TTL_SECONDS, get_feature_flags

logger = logging.getLogger("OptionScanner.Data.Manager")


class DataManager:
    """
    مدیر اصلی داده - ارکستراتور کل خط لوله داده سیستم

    ویژگی‌ها:
        - کپسوله‌سازی کامل خط لوله حول دیتامدل MarketSnapshot
        - کش با TTL قابل تنظیم بر روی شیء بومی مدل
        - Fallback هوشمند در صورت خرابی منابع زنده به کش قدیمی یا فایل محلی
    """

    def __init__(self, cache_dir: str = "data/cache", use_cache: bool = True, ttl_seconds: int = 60):
        """
        Args:
            cache_dir: پوشه ذخیره کش
            use_cache: فعال/غیرفعال کردن کش
            ttl_seconds: زمان انقضای کش (ثانیه)
        """
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "market_snapshot.pkl"
        self.use_cache = use_cache
        self.ttl_seconds = ttl_seconds if ttl_seconds is not None else CACHE_TTL_SECONDS

    # =====================================================
    # درگاه یکپارچه دریافت تصویر بازار (متد تجمیع شده)
    # =====================================================

    def get_market_snapshot(self, force_refresh: bool = False, calc_advanced: bool = True) -> MarketSnapshot:
        """
        متد تجمیع شده و ارشد لایه دیتا.
        کل خط لوله شامل لود کش، دانلود چندکاناله، پاکسازی، محاسبات یونانی و مپ به مدل را انجام می‌دهد.

        """
        # 0. بررسی کش (در صورت عدم نیاز به Force Refresh)
        if self.use_cache and not force_refresh:
            snapshot_cached = self._load_cache()
            if snapshot_cached is not None and snapshot_cached.option_contracts:
                logger.info(
                    f"Serving MarketSnapshot from memory/disk cache: {len(snapshot_cached.option_contracts)} contracts")
                return snapshot_cached

        # لیست دانلودرها برای اجرای مکانیزم Fallback به ترتیب اولویت
        download_sources = [
            ("TSETMC (direct)", MarketDownloader.from_tsetmc_direct),
            ("TSETMC (with DNS bypass)", MarketDownloader.from_tsetmc_with_bypass),
            ("Optionschool24", MarketDownloader.from_optionschool24)]

        df_raw = pd.DataFrame()

        # 1. تلاش برای دریافت از منابع زنده
        for source_name, download_func in download_sources:
            try:
                logger.info(f"Attempting to fetch from {source_name}...")
                df_raw = download_func()
                if df_raw is not None and not df_raw.empty:
                    logger.info(
                        f"Successfully fetched from {source_name}: {len(df_raw)} records")
                    break
            except Exception as e:
                logger.warning(f"Failed to fetch from {source_name}: {e}")
                continue

        # 2. بررسی مکانیزم Fallback در صورت شکست منابع زنده
        if df_raw.empty:
            if self.use_cache:
                logger.warning(
                    "All live sources failed. Trying expired cache as fallback...")
                snapshot_expired = self._load_cache(ignore_ttl=True)
                if snapshot_expired is not None and snapshot_expired.option_contracts:
                    logger.warning(
                        f"Using expired cache fallback: {len(snapshot_expired.option_contracts)} contracts")
                    return snapshot_expired

            logger.warning("Trying local backup file as last resort...")
            df_raw = MarketDownloader.from_local_file()

        if df_raw.empty:
            raise RuntimeError(
                "Critical Error: All data sources and fallbacks failed to provide market data.")

        # 3. پردازش متمرکز و مپ به شیء MarketSnapshot
        snapshot = self._process_and_convert(df_raw, calc_advanced)

        # 4. ذخیره در کش دیسک
        self._save_cache(snapshot)

        return snapshot

    # =====================================================
    # پردازش داخلی و تبدیل ساختار داده
    # =====================================================

    def _process_and_convert(self, df: pd.DataFrame, calc_advanced: bool) -> MarketSnapshot:
        """پاکسازی، اعمال فرآیندهای مالی و تبدیل نهایی دیتافریم به شیء بازار"""
        if df.empty:
            return MarketSnapshot()

        # ۱. پاکسازی و استخراج ستون‌ها
        df = DataCleaner.clean(df)
        df = DataCleaner.add_derived_columns(df)

        # ۲. محاسبات پیشرفته (BSM, Greeks, IV)
        if calc_advanced:
            logger.info(
                "Calculating advanced metrics (BSM, Greeks, IV)...")
            rf_rate = get_risk_free_rate()
            df = calculate_greeks_vectorized(df, rf_rate)
            logger.info(
                f"Advanced metrics calculated for {len(df)} records")
        else:
            logger.info(
                "Greeks calculation skipped (calculate_greeks=False)")

        # ۳. ساخت شیء هوشمند MarketSnapshot و ایندکس‌گذاری ساختار یافته درخت نمادها
        snapshot = MarketSnapshot.from_dataframe(df)
        snapshot.build_indices()
        return snapshot

    # =====================================================
    # مدیریت کش (بروزرسانی شده برای کار با اشیاء بومی سیستم)
    # =====================================================

    def _save_cache(self, snapshot: MarketSnapshot) -> None:
        """ذخیره شیء کامل دیتامدل در کش پیکل"""
        if not self.use_cache or not snapshot:
            return
        try:
            with open(self.cache_file, 'wb') as f:
                pickle.dump({
                    'snapshot': snapshot,
                    'timestamp': datetime.now()}, f)
            logger.debug("MarketSnapshot saved to disk cache.")
        except Exception as e:
            logger.warning(f"Cache save failed: {e}")

    def _load_cache(self, ignore_ttl: bool = False) -> Optional[MarketSnapshot]:
        """بارگذاری شیء دیتامدل از کش پیکل با بررسی امضای زمانی"""
        if not self.use_cache or not self.cache_file.exists():
            return None
        try:
            with open(self.cache_file, 'rb') as f:
                cache = pickle.load(f)

            if not ignore_ttl:
                age = (datetime.now() - cache['timestamp']).total_seconds()
                if age > self.ttl_seconds:
                    logger.debug(
                        f"Disk cache expired (age: {age:.0f}s > {self.ttl_seconds}s)")
                    return None

            return cache['snapshot']
        except Exception as e:
            logger.warning(f"Cache load failed: {e}")
            return None

    def clear_cache(self) -> None:
        if self.cache_file.exists():
            self.cache_file.unlink()
            logger.info("Cache cleared")


# =====================================================
# توابع تجمیع‌شده و درگاه‌های سطح بالای سیستم (High-Level API)
# =====================================================

def get_market_snapshot(use_cache: bool = True, calc_advanced: bool = True, force_refresh: bool = False) -> MarketSnapshot:
    """
    تنها درگاه ارشد و رسمی پروژه برای دریافت دیتای کل بازار بورس.

    Example:
        >>> snapshot = get_market_snapshot()
        >>> engine = ScannerEngine(snapshot=snapshot)
    """
    manager = DataManager(use_cache=use_cache)
    return manager.get_market_snapshot(force_refresh=force_refresh, calc_advanced=calc_advanced)


def Options(bsm_greeks: bool = False, use_cache: bool = True, force_refresh: bool = False) -> pd.DataFrame:
    """
    تابع معادل سازگار با نسخه‌های فایما و کدهای قدیمی پروژه (Retro-compatibility).
    از آنجا که سیستم‌های قدیمی به دیتافریم نیاز دارند، این تابع دیتای داخلی Snapshot را باز می‌کند.
    """
    snapshot = get_market_snapshot(
        use_cache=use_cache, calc_advanced=bsm_greeks, force_refresh=force_refresh)

    # بازگرداندن دیتافریم از روی لیست قراردادهای داخل Snapshot جهت متوقف نشدن کدهای قدیمی سیستم
    if not snapshot.option_contracts:
        return pd.DataFrame()

    # استخراج دیتای ساختاریافته در قالب دیکشنری پنداس
    records = [contract.__dict__ for contract in snapshot.option_contracts]
    return pd.DataFrame(records)
