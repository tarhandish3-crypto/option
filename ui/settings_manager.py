# ui/settings_manager.py
# -*- coding: utf-8 -*-

"""
مدیریت متمرکز تنظیمات برنامه با پشتیبانی از پروفایل‌های چندگانه.

ساختار فایل ذخیره‌سازی (data/user_settings.json):
{
    "active_profile": "نام پروفایل فعال",
    "profiles": {
        "پروفایل من": { ...settings dict... },
        "تنظیمات محافظه‌کار": { ...settings dict... }
    }
}

قوانین:
- تنظیمات پیش‌فرض همیشه از config.py خوانده می‌شود (هرگز تغییر نمی‌کند).
- هر تغییر کاربر در یک پروفایل ذخیره می‌شود.
- پروفایل فعال در بین اجراهای برنامه حفظ می‌شود.
- "پیش‌فرض" یک نام رزرو است که نمی‌توان آن را ذخیره یا حذف کرد.
"""

import json
import logging
from copy import deepcopy
from pathlib import Path
from typing import Dict, Any, List, Optional

import config

logger = logging.getLogger("OptionScanner.UI.SettingsManager")

# نام رزرو برای تنظیمات پیش‌فرض config.py
_DEFAULT_PROFILE_NAME = "پیش‌فرض"

# مسیر فایل ذخیره‌سازی تنظیمات کاربر (روت پروژه)
_SETTINGS_FILE = config.BASE_DIR / "user_settings.json"


def _build_defaults_from_config() -> Dict[str, Any]:
    """
    استخراج تنظیمات پیش‌فرض مستقیم از config.py.
    این تابع تنها منبع حقیقت برای مقادیر پیش‌فرض است.
    """
    return {
        # شبکه و API
        "api_timeout":      config.DOWNLOAD_CONFIG.get("timeout", 30),
        "api_max_retries":  config.DOWNLOAD_CONFIG.get("max_attempts", 3),
        "request_delay_ms": config.DOWNLOAD_CONFIG.get("retry_delay", 5) * 1000,

        # پارامترهای اسکنر
        "risk_free_rate":           config.RISK_FREE_RATE,
        "min_open_interest":        config.MIN_OPEN_INTEREST,
        "min_days_to_maturity":     config.DaysToMaturity,
        "max_days_to_maturity":     365,
        "volatility_step_percent":  5.0,
        "volatility_range_min":     float(config.PRICE_RANGE_CONFIG.get("min_percent", -45)),
        "volatility_range_max":     float(config.PRICE_RANGE_CONFIG.get("max_percent", 45)),

        # عمومی و UI
        "auto_refresh_enabled":       False,
        "auto_refresh_interval_sec":  int(config.SYSTEM_CONFIG.get("scan_interval_minutes", 2) * 60),
        "theme":                      "روشن (Light)",
        "log_level":                  "INFO",
        "export_dir":                 str(config.OUTPUT_DIR),

        # پیشرفته
        "enable_parallel_processing": config.SYSTEM_CONFIG.get("parallel_enabled", False),
        "max_parallel_workers":       config.SYSTEM_CONFIG.get("max_workers", 3),
        "cache_enabled":              config.CACHE_ENABLED,
        "cache_ttl_seconds":          config.CACHE_TTL_SECONDS,

        # نمادهای بلاک‌شده (پیش‌فرض: هیچ‌کدام)
        "excluded_symbols": [],
    }


class SettingsManager:
    """
    مدیر تنظیمات برنامه — Singleton برای استفاده یکپارچه در کل پروژه.

    استفاده:
        from ui.settings_manager import settings_manager

        current = settings_manager.get_active_settings()
        settings_manager.save_profile("پروفایل جدید", current)
        settings_manager.set_active_profile("پروفایل جدید")
    """

    def __init__(self):
        self._profiles: Dict[str, Dict[str, Any]] = {}
        self._active_profile: str = _DEFAULT_PROFILE_NAME
        self._excluded_symbols: List[str] = []
        self._load()

    # =====================================================
    # بارگذاری و ذخیره‌سازی فایل
    # =====================================================

    def _load(self) -> None:
        """بارگذاری تنظیمات از فایل؛ اگر فایل نبود از پیش‌فرض شروع می‌کند."""
        if _SETTINGS_FILE.exists():
            try:
                with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._profiles = data.get("profiles", {})
                self._active_profile = data.get("active_profile", _DEFAULT_PROFILE_NAME)
                self._excluded_symbols = sorted(data.get("excluded_symbols", []))
                logger.info(
                    f"✅ تنظیمات بارگذاری شد — پروفایل فعال: '{self._active_profile}'"
                    f" | پروفایل‌ها: {len(self._profiles)}"
                    f" | نمادهای بلاک: {len(self._excluded_symbols)}"
                )
            except Exception as e:
                logger.warning(f"⚠️ خطا در بارگذاری تنظیمات: {e} — استفاده از پیش‌فرض")
                self._profiles = {}
                self._active_profile = _DEFAULT_PROFILE_NAME
                self._excluded_symbols = []
        else:
            logger.info("📄 فایل تنظیمات وجود ندارد — استفاده از پیش‌فرض config.py")

    def _save(self) -> None:
        """ذخیره‌سازی کل وضعیت در فایل JSON."""
        try:
            data = {
                "active_profile": self._active_profile,
                "profiles": self._profiles,
                "excluded_symbols": self._excluded_symbols,
            }
            with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            logger.info(f"💾 تنظیمات ذخیره شد — پروفایل: '{self._active_profile}'")
        except Exception as e:
            logger.error(f"❌ خطا در ذخیره تنظیمات: {e}")

    # =====================================================
    # دریافت تنظیمات
    # =====================================================

    def get_defaults(self) -> Dict[str, Any]:
        """تنظیمات پیش‌فرض خالص از config.py — هرگز تغییر نمی‌کند."""
        return _build_defaults_from_config()

    def get_active_settings(self) -> Dict[str, Any]:
        """
        تنظیمات جاری برنامه:
        - اگر پروفایل فعال 'پیش‌فرض' باشد → مستقیم از config.py
        - در غیر این صورت → از پروفایل ذخیره‌شده (با fallback به پیش‌فرض)
        """
        if self._active_profile == _DEFAULT_PROFILE_NAME:
            return self.get_defaults()

        profile_data = self._profiles.get(self._active_profile)
        if profile_data is None:
            logger.warning(
                f"⚠️ پروفایل '{self._active_profile}' یافت نشد — بازگشت به پیش‌فرض"
            )
            self._active_profile = _DEFAULT_PROFILE_NAME
            return self.get_defaults()

        # merge: پیش‌فرض + override با مقادیر پروفایل
        merged = self.get_defaults()
        merged.update(profile_data)
        return merged

    def get_profile_names(self) -> List[str]:
        """لیست نام پروفایل‌های کاربر (بدون 'پیش‌فرض')."""
        return sorted(self._profiles.keys())

    def get_active_profile_name(self) -> str:
        return self._active_profile

    def get_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """دریافت یک پروفایل خاص؛ برای 'پیش‌فرض' → config.py."""
        if name == _DEFAULT_PROFILE_NAME:
            return self.get_defaults()
        profile = self._profiles.get(name)
        if profile is None:
            return None
        merged = self.get_defaults()
        merged.update(profile)
        return merged

    # =====================================================
    # مدیریت پروفایل‌ها
    # =====================================================

    def save_profile(self, name: str, settings: Dict[str, Any]) -> bool:
        """
        ذخیره یا به‌روزرسانی یک پروفایل.
        نام 'پیش‌فرض' رزرو است و قابل ذخیره نیست.
        """
        if name == _DEFAULT_PROFILE_NAME:
            logger.warning("⛔ نام 'پیش‌فرض' رزرو است و قابل ذخیره نیست.")
            return False

        name = name.strip()
        if not name:
            return False

        self._profiles[name] = deepcopy(settings)
        self._active_profile = name
        self._save()
        logger.info(f"✅ پروفایل '{name}' ذخیره شد و فعال گردید.")
        return True

    def set_active_profile(self, name: str) -> bool:
        """تغییر پروفایل فعال."""
        if name == _DEFAULT_PROFILE_NAME:
            self._active_profile = _DEFAULT_PROFILE_NAME
            self._save()
            return True

        if name not in self._profiles:
            logger.warning(f"⚠️ پروفایل '{name}' یافت نشد.")
            return False

        self._active_profile = name
        self._save()
        logger.info(f"🔄 پروفایل فعال تغییر یافت: '{name}'")
        return True

    def delete_profile(self, name: str) -> bool:
        """حذف یک پروفایل. 'پیش‌فرض' حذف نمی‌شود."""
        if name == _DEFAULT_PROFILE_NAME:
            logger.warning("⛔ پروفایل 'پیش‌فرض' قابل حذف نیست.")
            return False

        if name not in self._profiles:
            return False

        del self._profiles[name]

        # اگر پروفایل حذف‌شده فعال بود، برگرد به پیش‌فرض
        if self._active_profile == name:
            self._active_profile = _DEFAULT_PROFILE_NAME

        self._save()
        logger.info(f"🗑️ پروفایل '{name}' حذف شد.")
        return True

    def restore_defaults(self) -> None:
        """
        بازگشت به تنظیمات پیش‌فرض config.py.
        پروفایل‌های ذخیره‌شده دست نخورده باقی می‌مانند.
        """
        self._active_profile = _DEFAULT_PROFILE_NAME
        self._save()
        logger.info("🔄 پروفایل فعال به 'پیش‌فرض' بازگردانده شد.")

    def rename_profile(self, old_name: str, new_name: str) -> bool:
        """تغییر نام یک پروفایل."""
        if old_name == _DEFAULT_PROFILE_NAME or new_name == _DEFAULT_PROFILE_NAME:
            return False
        if old_name not in self._profiles:
            return False
        new_name = new_name.strip()
        if not new_name or new_name in self._profiles:
            return False

        self._profiles[new_name] = self._profiles.pop(old_name)
        if self._active_profile == old_name:
            self._active_profile = new_name
        self._save()
        logger.info(f"✏️ پروفایل '{old_name}' به '{new_name}' تغییر نام یافت.")
        return True

    # =====================================================
    # مدیریت نمادهای بلاک‌شده (جدا از پروفایل — سراسری)
    # =====================================================

    def get_excluded_symbols(self) -> List[str]:
        """
        لیست نمادهای بلاک‌شده.
        این تنظیم سراسری است و وابسته به پروفایل نیست.
        """
        return list(self._excluded_symbols)

    def set_excluded_symbols(self, symbols: List[str]) -> None:
        """ذخیره لیست نمادهای بلاک‌شده و ثبت دائمی در فایل."""
        self._excluded_symbols = sorted(set(symbols))
        self._save()
        logger.info(f"🚫 نمادهای بلاک‌شده به‌روز شد: {len(self._excluded_symbols)} نماد")


# =====================================================
# نمونه Singleton — import کن و استفاده کن
# =====================================================

settings_manager = SettingsManager()
