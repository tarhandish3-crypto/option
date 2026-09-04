# ui/settings_manager.py
# -*- coding: utf-8 -*-

"""
ماژول مدیریت تنظیمات، پروفایل‌ها و ذخیره‌سازی پایدار در فایل user_settings.json
بدون باگ انتساب به رشته و مجهز به مکانیزم اعتبارسنجی خودکار.
"""

from __future__ import annotations

import os
import json
import logging
from threading import RLock
from typing import Dict, Any, List, Optional, Union

import config

logger = logging.getLogger("OptionScanner.UI.SettingsManager")

_DEFAULT_PROFILE_NAME = "پیش‌فرض"
SETTINGS_FILE_PATH = "user_settings.json"


# =========================================================================
# تنظیمات پیش‌فرض پایه سیستم
# =========================================================================

DEFAULT_SETTINGS: Dict[str, Any] = {
    "theme": "تاریک (Dark)",
    "layout_direction": "راست‌چین (RTL)",
    "auto_scan_enabled": True,
    "auto_scan_interval": 60,
    "bale_enabled": False,
    "bale_bot_token": "",
    "bale_chat_id": "",
    "bale_top_n": 2,
    "broker_username": "",
    "broker_password": "",
    "excluded_symbols": [],
    "custom_prices": {},
    "custom_prices_enabled": True,
    "active_strategies": [
        "covered_call",
        "bull_call_spread",
        "bear_put_spread",
        "iron_condor",
        "long_straddle",
        "long_strangle",
        "collar",
        "conversion",
        "married_put",
        "strip",
        "strap",
        "long_call",
        "long_put",
    ],
    "column_visibility": {},
    "price_range": {
        "min_percent": -45,
        "max_percent": 45,
        "num_points": 21,
        "step_size": None,
        "labels_format": "{:.0f}%",
    }
}


class SettingsManager:
    """
    مدیریت جامع خواندن، ویرایش، پشتیبان‌گیری و ذخیره‌سازی تنظیمات سیستم
    """
    _instance: Optional[SettingsManager] = None
    _lock = RLock()

    def __new__(cls, *args, **kwargs) -> SettingsManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self, filepath: str = SETTINGS_FILE_PATH):
        # جلوگیری از مقداردهی مجدد در الگوی Singleton
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.filepath = filepath
        self._active_profile_name: str = "default"
        self._profiles_data: Dict[str, Dict[str, Any]] = {}
        self._root_data: Dict[str, Any] = {}

        self.load_from_disk()
        self._initialized = True

    # =========================================================================
    # خواندن و نوشتن روی دیسک (Disk I/O)
    # =========================================================================

    def load_from_disk(self) -> None:
        """بارگذاری فایل JSON یا ایجاد مقادیر پیش‌فرض در صورت عدم وجود"""
        with self._lock:
            if not os.path.exists(self.filepath):
                logger.info(f"Settings file '{self.filepath}' not found. Creating default settings.")
                self._create_default_store()
                self.save_to_disk()
                return

            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    loaded_data = json.load(f)

                if not isinstance(loaded_data, dict):
                    raise ValueError("Root JSON is not a dictionary.")

                self._root_data = loaded_data
                self._active_profile_name = str(loaded_data.get("active_profile", "default"))
                
                raw_profiles = loaded_data.get("profiles", {})
                if isinstance(raw_profiles, dict) and raw_profiles:
                    self._profiles_data = {
                        str(k): self._merge_with_defaults(v)
                        for k, v in raw_profiles.items()
                        if isinstance(v, dict)
                    }
                else:
                    self._profiles_data = {"default": self._merge_with_defaults(loaded_data)}

                # تضمین وجود پروفایل فعال معتبر
                if self._active_profile_name not in self._profiles_data:
                    if "default" in self._profiles_data:
                        self._active_profile_name = "default"
                    else:
                        self._active_profile_name = list(self._profiles_data.keys())[0]

                logger.info(f"Settings loaded successfully. Active profile: '{self._active_profile_name}'")

            except Exception as e:
                logger.error(f"Error reading '{self.filepath}': {e}. Reverting to defaults.")
                self._create_default_store()
                self.save_to_disk()

    def save_to_disk(self) -> bool:
        """ذخیره قطعی و اتمیک داده‌ها در فایل user_settings.json"""
        with self._lock:
            try:
                # اطمینان از ساختار سالم دیکشنری ذخیره‌سازی
                output_payload: Dict[str, Any] = {
                    "active_profile": self._active_profile_name,
                    "profiles": self._profiles_data,
                    # کپی فیلدهای مهم در سطح ریشه برای دسترسی سریع‌تر سایر ماژول‌ها
                    "custom_prices": self.get_custom_prices(),
                    "custom_prices_enabled": self.get_custom_prices_enabled(),
                    "active_strategies": self.get_active_strategies(),
                    "excluded_symbols": self.get_excluded_symbols(),
                }

                # نوشتن ایمن
                temp_path = f"{self.filepath}.tmp"
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(output_payload, f, ensure_ascii=False, indent=4)

                if os.path.exists(self.filepath):
                    os.replace(temp_path, self.filepath)
                else:
                    os.rename(temp_path, self.filepath)

                logger.info(f"Settings successfully written to '{self.filepath}'")
                return True

            except Exception as e:
                logger.error(f"Failed to save settings to '{self.filepath}': {e}", exc_info=True)
                return False

    def _create_default_store(self) -> None:
        """ایجاد مخزن پیش‌فرض"""
        self._active_profile_name = "default"
        self._profiles_data = {"default": DEFAULT_SETTINGS.copy()}
        self._root_data = {
            "active_profile": "default",
            "profiles": self._profiles_data
        }

    def _merge_with_defaults(self, custom: Dict[str, Any]) -> Dict[str, Any]:
        """ادغام تنظیمات کاربر با مقادیر پیش‌فرض جهت تضمین وجود تمام کلیدها"""
        merged = DEFAULT_SETTINGS.copy()
        if isinstance(custom, dict):
            for k, v in custom.items():
                if k in ("custom_prices", "active_strategies", "excluded_symbols"):
                    merged[k] = v
                else:
                    merged[k] = v
        return merged

    # =========================================================================
    # مدیریت پروفایل‌ها (Profiles API)
    # =========================================================================

    def get_active_profile(self) -> str:
        """بازگرداندن نام متنی پروفایل فعال (String)"""
        with self._lock:
            return self._active_profile_name

    def set_active_profile(self, profile_name: str) -> bool:
        """تغییر پروفایل فعال"""
        with self._lock:
            if profile_name in self._profiles_data:
                self._active_profile_name = profile_name
                self.save_to_disk()
                return True
            return False

    def get_profiles(self) -> List[str]:
        """لیست اسامی تمام پروفایل‌ها"""
        with self._lock:
            return list(self._profiles_data.keys())

    def create_profile(self, profile_name: str, base_settings: Optional[Dict[str, Any]] = None) -> bool:
        """ایجاد پروفایل جدید"""
        with self._lock:
            if profile_name in self._profiles_data:
                return False
            self._profiles_data[profile_name] = self._merge_with_defaults(base_settings or {})
            self._active_profile_name = profile_name
            self.save_to_disk()
            return True

    def delete_profile(self, profile_name: str) -> bool:
        """حذف پروفایل"""
        with self._lock:
            if profile_name == "default" or len(self._profiles_data) <= 1:
                return False
            if profile_name in self._profiles_data:
                del self._profiles_data[profile_name]
                if self._active_profile_name == profile_name:
                    self._active_profile_name = list(self._profiles_data.keys())[0]
                self.save_to_disk()
                return True
            return False

    # =========================================================================
    # دریافت و ویرایش تنظیمات (Settings CRUD)
    # =========================================================================

    def get_active_settings(self) -> Dict[str, Any]:
        """بازگرداندن یک کپی ایمن از دیکشنری تنظیمات پروفایل فعال"""
        with self._lock:
            active_dict = self._profiles_data.get(self._active_profile_name, DEFAULT_SETTINGS)
            return active_dict.copy()

    def get_settings(self) -> Dict[str, Any]:
        """سازگاری با کدهای قبلی"""
        return self.get_active_settings()

    def save_settings(self, new_settings: Dict[str, Any], profile_name: Optional[str] = None) -> bool:
        """
        ذخیره و به‌روزرسانی دیکشنری تنظیمات در پروفایل مشخص یا پروفایل جاری
        """
        with self._lock:
            target_profile = profile_name or self._active_profile_name
            if not isinstance(new_settings, dict):
                logger.error("save_settings failed: new_settings must be a dictionary.")
                return False

            current = self._profiles_data.get(target_profile, DEFAULT_SETTINGS.copy())
            current.update(new_settings)
            self._profiles_data[target_profile] = current

            return self.save_to_disk()

    def get_setting(self, key: str, default: Any = None) -> Any:
        """دریافت مقدار یک کلید خاص از تنظیمات فعال"""
        with self._lock:
            settings = self.get_active_settings()
            return settings.get(key, default)

    def set_setting(self, key: str, value: Any) -> bool:
        """تنظیم و ذخیره مقدار یک کلید خاص"""
        with self._lock:
            settings = self.get_active_settings()
            settings[key] = value
            return self.save_settings(settings)

    # =========================================================================
    # متدهای اختصاصی قیمت دستی (Custom Prices) - رفع باگ انتساب به رشته
    # =========================================================================

    def get_custom_prices(self) -> Dict[str, float]:
        """دریافت دیکشنری قیمت‌های دستی"""
        with self._lock:
            prices = self.get_setting("custom_prices", {})
            if isinstance(prices, dict):
                return {str(k): float(v) for k, v in prices.items() if v is not None}
            elif isinstance(prices, str):
                try:
                    parsed = json.loads(prices)
                    if isinstance(parsed, dict):
                        return {str(k): float(v) for k, v in parsed.items()}
                except Exception:
                    pass
            return {}

    def set_custom_prices(self, prices: Dict[str, float]) -> bool:
        """
        ذخیره قطعی و ایمن قیمت‌های دستی بدون خطا
        """
        with self._lock:
            if not isinstance(prices, dict):
                logger.warning("set_custom_prices received a non-dict value. Converting to empty dict.")
                clean_prices = {}
            else:
                clean_prices = {
                    str(k): float(v) for k, v in prices.items()
                    if v is not None and float(v) > 0
                }

            # ۱. ذخیره در پروفایل فعال
            active_dict = self._profiles_data.setdefault(self._active_profile_name, DEFAULT_SETTINGS.copy())
            active_dict["custom_prices"] = clean_prices

            # ۲. همگام‌سازی با کانفیگ برنامه
            if hasattr(config, "CUSTOM_PRICES"):
                config.CUSTOM_PRICES = clean_prices

            return self.save_to_disk()

    def get_custom_prices_enabled(self) -> bool:
        """بررسی فعال بودن قیمت‌های دستی"""
        with self._lock:
            return bool(self.get_setting("custom_prices_enabled", True))

    def set_custom_prices_enabled(self, enabled: bool) -> bool:
        """فعال یا غیرفعال‌سازی قیمت‌های دستی"""
        with self._lock:
            active_dict = self._profiles_data.setdefault(self._active_profile_name, DEFAULT_SETTINGS.copy())
            active_dict["custom_prices_enabled"] = bool(enabled)
            return self.save_to_disk()

    # =========================================================================
    # سایر متدهای دسترسی سریع (Convenience Methods)
    # =========================================================================

    def get_excluded_symbols(self) -> List[str]:
        """دریافت نمادهای استثناشده (بلاک‌شده)"""
        with self._lock:
            excluded = self.get_setting("excluded_symbols", [])
            return list(excluded) if isinstance(excluded, (list, tuple, set)) else []

    def set_excluded_symbols(self, symbols: List[str]) -> bool:
        """تنظیم نمادهای استثناشده"""
        with self._lock:
            clean_list = [str(s).strip() for s in symbols if str(s).strip()]
            return self.set_setting("excluded_symbols", clean_list)

    def get_active_strategies(self) -> List[str]:
        """دریافت استراتژی‌های فعال برای اسکن"""
        with self._lock:
            strats = self.get_setting("active_strategies", None)
            if isinstance(strats, (list, tuple)):
                return list(strats)
            return getattr(config, "ACTIVE_STRATEGIES", DEFAULT_SETTINGS["active_strategies"])

    def set_active_strategies(self, strategies: List[str]) -> bool:
        """تنظیم استراتژی‌های فعال"""
        with self._lock:
            clean_list = [str(s).strip() for s in strategies if str(s).strip()]
            if hasattr(config, "ACTIVE_STRATEGIES"):
                config.ACTIVE_STRATEGIES = clean_list
            return self.set_setting("active_strategies", clean_list)

    def get_bale_config(self) -> Dict[str, Any]:
        """دریافت پیکربندی پیام‌رسان بله"""
        with self._lock:
            settings = self.get_active_settings()
            return {
                "enabled": settings.get("bale_enabled", False),
                "bot_token": settings.get("bale_bot_token", ""),
                "chat_id": settings.get("bale_chat_id", ""),
                "top_n": settings.get("bale_top_n", 2),
            }

    def get_broker_config(self) -> Dict[str, Any]:
        """دریافت تنظیمات احراز هویت کارگزاری"""
        with self._lock:
            settings = self.get_active_settings()
            return {
                "username": settings.get("broker_username", ""),
                "password": settings.get("broker_password", ""),
            }

    def reset_to_defaults(self) -> bool:
        """بازنشانی کامل تنظیمات به حالت کارخانه"""
        with self._lock:
            self._create_default_store()
            return self.save_to_disk()


# =========================================================================
# نمونه یکتای سراسری (Singleton Instance Export)
# =========================================================================

settings_manager = SettingsManager()