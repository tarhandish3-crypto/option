# ui/settings_manager.py
# -*- coding: utf-8 -*-

"""
مدیریت متمرکز تنظیمات برنامه با پشتیبانی از پروفایل‌های چندگانه.
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
        "layout_direction":           "راست‌چین (RTL)",
        "log_level":                  "INFO",
        "export_dir":                 str(config.OUTPUT_DIR),

        # پیشرفته
        "enable_parallel_processing": config.SYSTEM_CONFIG.get("parallel_enabled", False),
        "max_parallel_workers":       config.SYSTEM_CONFIG.get("max_workers", 3),
        "cache_enabled":              config.CACHE_ENABLED,
        "cache_ttl_seconds":          config.CACHE_TTL_SECONDS,

        # پیام‌رسان بله
        "bale_enabled":   False,
        "bale_bot_token": "",
        "bale_chat_id":   "",
        "bale_top_n":     2,

        # کارگزاری اومکس
        "broker_username": "",
        "broker_password": "",

        # استراتژی‌های فعال و نمادهای بلاک‌شده
        "active_strategies": getattr(config, "ACTIVE_STRATEGIES", []),
        "excluded_symbols": [],
    }


class SettingsManager:
    """
    مدیر تنظیمات برنامه — Singleton برای استفاده یکپارچه در کل پروژه.
    """

    def __init__(self):
        self._profiles: Dict[str, Dict[str, Any]] = {}
        self._active_profile: str = _DEFAULT_PROFILE_NAME
        self._excluded_symbols: List[str] = []
        self._load()

    def _load(self) -> None:
        """بارگذاری تنظیمات از فایل"""
        if _SETTINGS_FILE.exists():
            try:
                with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._profiles = data.get("profiles", {})
                self._active_profile = data.get(
                    "active_profile", _DEFAULT_PROFILE_NAME)
                self._excluded_symbols = sorted(
                    data.get("excluded_symbols", []))
                logger.info(
                    f"Settings loaded -- active profile: '{self._active_profile}'"
                    f" | profiles: {len(self._profiles)}"
                    f" | blocked symbols: {len(self._excluded_symbols)}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to load settings: {e} -- using defaults")
                self._profiles = {}
                self._active_profile = _DEFAULT_PROFILE_NAME
                self._excluded_symbols = []
        else:
            logger.info(
                "Settings file not found -- using defaults from config.py")

    def _save(self) -> None:
        """ذخیره‌سازی کل وضعیت در فایل JSON"""
        try:
            data = {
                "active_profile": self._active_profile,
                "profiles": self._profiles,
                "excluded_symbols": self._excluded_symbols,
            }
            with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            logger.info(f"Settings saved -- profile: '{self._active_profile}'")
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

    def get_defaults(self) -> Dict[str, Any]:
        """تنظیمات پیش‌فرض خالص از config.py"""
        return _build_defaults_from_config()

    def get_active_settings(self) -> Dict[str, Any]:
        """دریافت تنظیمات جاری برنامه با احتساب مقادیر دیفالت"""
        if self._active_profile == _DEFAULT_PROFILE_NAME:
            return self.get_defaults()

        profile_data = self._profiles.get(self._active_profile)
        if profile_data is None:
            logger.warning(
                f"Profile '{self._active_profile}' not found -- falling back to defaults"
            )
            self._active_profile = _DEFAULT_PROFILE_NAME
            return self.get_defaults()

        merged = self.get_defaults()
        merged.update(profile_data)
        return merged

    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """
        متد کمکی برای ذخیره مستقیم دیکشنری تنظیمات در پروفایل فعال یا پروفایل اختصاصی
        """
        active = self._active_profile
        if active == _DEFAULT_PROFILE_NAME:
            active = "تنظیمات سفارشی"
            self._active_profile = active

        return self.save_profile(active, settings)

    def get_profile_names(self) -> List[str]:
        return sorted(self._profiles.keys())

    def get_active_profile_name(self) -> str:
        return self._active_profile

    def get_profile(self, name: str) -> Optional[Dict[str, Any]]:
        if name == _DEFAULT_PROFILE_NAME:
            return self.get_defaults()
        profile = self._profiles.get(name)
        if profile is None:
            return None
        merged = self.get_defaults()
        merged.update(profile)
        return merged

    def save_profile(self, name: str, settings: Dict[str, Any]) -> bool:
        if name == _DEFAULT_PROFILE_NAME:
            logger.warning("Name 'default' is reserved and cannot be saved.")
            return False

        name = name.strip()
        if not name:
            return False

        self._profiles[name] = deepcopy(settings)
        self._active_profile = name
        self._save()
        logger.info(f"Profile '{name}' saved and activated.")
        return True

    def set_active_profile(self, name: str) -> bool:
        if name == _DEFAULT_PROFILE_NAME:
            self._active_profile = _DEFAULT_PROFILE_NAME
            self._save()
            return True

        if name not in self._profiles:
            logger.warning(f"Profile '{name}' not found.")
            return False

        self._active_profile = name
        self._save()
        logger.info(f"Active profile changed to: '{name}'")
        return True

    def delete_profile(self, name: str) -> bool:
        if name == _DEFAULT_PROFILE_NAME:
            logger.warning("Default profile cannot be deleted.")
            return False

        if name not in self._profiles:
            return False

        del self._profiles[name]
        if self._active_profile == name:
            self._active_profile = _DEFAULT_PROFILE_NAME

        self._save()
        logger.info(f"Profile '{name}' deleted.")
        return True

    def restore_defaults(self) -> None:
        self._active_profile = _DEFAULT_PROFILE_NAME
        self._save()
        logger.info("Active profile reset to 'default'.")

    def get_excluded_symbols(self) -> List[str]:
        return list(self._excluded_symbols)

    def set_excluded_symbols(self, symbols: List[str]) -> None:
        self._excluded_symbols = sorted(set(symbols))
        self._save()
        logger.info(
            f"Blocked symbols updated: {len(self._excluded_symbols)} symbol(s)")
    
    def get_active_strategies(self) -> List[str]:
        """دریافت لیست استراتژی‌های فعال"""
        s = self.get_active_settings()
        return s.get("active_strategies", [])
    
    def get_custom_prices(self) -> Dict[str, float]:
        """دریافت دیکشنری قیمت‌های دستی نمادها"""
        s = self.get_active_settings()
        return s.get("custom_prices", {})
    
    def set_custom_prices(self, prices: Dict[str, float]) -> None:
        """ذخیره قیمت‌های دستی نمادها"""
        self._active_profile["custom_prices"] = prices
        self._save()
        logger.info(f"Custom prices updated: {len(prices)} symbols")
    
    def get_custom_price(self, symbol: str) -> Optional[float]:
        """دریافت قیمت دستی برای یک نماد خاص"""
        prices = self.get_custom_prices()
        return prices.get(symbol)
    
    def set_custom_price(self, symbol: str, price: float) -> None:
        """تنظیم قیمت دستی برای یک نماد"""
        prices = self.get_custom_prices()
        prices[symbol] = price
        self.set_custom_prices(prices)
    
    def remove_custom_price(self, symbol: str) -> None:
        """حذف قیمت دستی یک نماد"""
        prices = self.get_custom_prices()
        if symbol in prices:
            del prices[symbol]
            self.set_custom_prices(prices)
    
    def clear_all_custom_prices(self) -> None:
        """حذف تمام قیمت‌های دستی"""
        self.set_custom_prices({})

    def get_bale_config(self) -> Dict[str, Any]:
        s = self.get_active_settings()
        return {
            "bot_token": s.get("bale_bot_token", ""),
            "chat_id":   s.get("bale_chat_id", ""),
            "top_n":     s.get("bale_top_n", 2),
            "enabled":   s.get("bale_enabled", False),
        }

    def get_broker_config(self) -> Dict[str, Any]:
        s = self.get_active_settings()
        return {
            "username": s.get("broker_username", ""),
            "password": s.get("broker_password", ""),
        }


settings_manager = SettingsManager()
