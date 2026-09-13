# ui/settings_manager.py
# -*- coding: utf-8 -*-

"""
مدیریت متمرکز، ایمن و تک‌نمونه (Singleton) تنظیمات کاربر و پروفایل‌ها.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

import config

logger = logging.getLogger("OptionScanner.UI.SettingsManager")

SETTINGS_FILE_PATH = str(config.USER_SETTINGS_PATH)
_DEFAULT_PROFILE_NAME = "default"


# =========================================================================
# تنظیمات پیش‌فرض
# =========================================================================

DEFAULT_SETTINGS: Dict[str, Any] = {
    "theme": "dark",
    "layout_direction": "راست‌چین (RTL)",
    "auto_scan_enabled": True,
    "auto_scan_interval": 60,
    "min_volume": 3,
    "min_open_interest": 50,
    "min_days_to_maturity": 2,
    "max_days_to_maturity": 365,
    "max_spread_pct": 0.05,
    "liquidity_score_threshold": 1.0,
    "default_depth_threshold": 30,
    "risk_free_rate": 0.24,
    "price_range": {
        "min_percent": -45.0,
        "max_percent": 45.0,
        "num_points": 21,
        "step_size": None,
        "labels_format": "{:.0f}%",
    },
    "custom_prices": {},
    "custom_prices_enabled": True,
    "excluded_symbols": [],
    "active_strategies": [
        "bull_call_spread", "bear_put_spread", "collar", "conversion",
        "covered_call", "iron_condor", "long_guts", "long_straddle",
        "married_put", "strip", "strap", "long_call", "long_put",
    ],
    "strategy_filters": {},
    "bale": {
        "enabled": False,
        "bot_token": "",
        "chat_id": "",
        "top_n": 2,
    },
    "broker": {
        "username": "",
        "password": "",
        "headless": False,
    },
}


# =========================================================================
# SettingsManager (Singleton)
# =========================================================================

class SettingsManager:
    """مدیریت متمرکز تنظیمات کاربر با پشتیبانی از پروفایل‌ها"""

    _instance: Optional["SettingsManager"] = None
    _instance_lock = threading.RLock()
    _init_lock = threading.Lock()

    def __new__(cls, *args, **kwargs) -> "SettingsManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, filepath: str = SETTINGS_FILE_PATH) -> None:
        # جلوگیری از مقداردهی مجدد در Singleton
        with self._init_lock:
            if getattr(self, "_initialized", False):
                return

            self.filepath = filepath
            self._active_profile_name: str = _DEFAULT_PROFILE_NAME
            self._profiles_data: Dict[str, Dict[str, Any]] = {}
            self._lock = threading.RLock()

            try:
                self._load_from_disk()
            finally:
                self._initialized = True

    # =====================================================================
    # Profile API
    # =====================================================================

    def get_active_profile_name(self) -> str:
        with self._lock:
            return self._active_profile_name

    def get_active_profile(self) -> str:
        """Alias برای سازگاری با کدهای قدیمی"""
        return self.get_active_profile_name()

    def get_all_profile_names(self) -> List[str]:
        with self._lock:
            return list(self._profiles_data.keys())

    def get_profile_names(self) -> List[str]:
        """Alias برای سازگاری با settings_dialog"""
        return self.get_all_profile_names()

    def set_active_profile(self, profile_name: str) -> bool:
        """تغییر پروفایل فعال با rollback در صورت شکست ذخیره‌سازی"""
        with self._lock:
            if not profile_name:
                return False

            if profile_name not in self._profiles_data:
                self._profiles_data[profile_name] = copy.deepcopy(
                    DEFAULT_SETTINGS)

            previous = self._active_profile_name
            self._active_profile_name = profile_name

            if not self._save_to_disk():
                self._active_profile_name = previous
                logger.error(f"Failed to switch to profile '{profile_name}'")
                return False
            return True

    def save_profile(self, profile_name: str, settings: Dict[str, Any]) -> bool:
        """ذخیره تنظیمات در یک پروفایل مشخص (ایجاد یا به‌روزرسانی)"""
        with self._lock:
            if not profile_name or not isinstance(settings, dict):
                return False

            existing = self._profiles_data.get(
                profile_name, copy.deepcopy(DEFAULT_SETTINGS)
            )
            merged = self._deep_merge(existing, settings)
            self._profiles_data[profile_name] = merged
            self._active_profile_name = profile_name
            return self._save_to_disk()

    def create_profile(
        self,
        profile_name: str,
        base_settings: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """ایجاد پروفایل جدید با ادغام با تنظیمات پیش‌فرض"""
        with self._lock:
            if not profile_name or profile_name in self._profiles_data:
                return False
            self._profiles_data[profile_name] = self._deep_merge(
                DEFAULT_SETTINGS, base_settings or {}
            )
            return self._save_to_disk()

    def delete_profile(self, profile_name: str) -> bool:
        """حذف پروفایل (به‌جز پروفایل پیش‌فرض)"""
        with self._lock:
            if profile_name == _DEFAULT_PROFILE_NAME:
                return False
            if len(self._profiles_data) <= 1:
                return False
            if profile_name not in self._profiles_data:
                return False

            del self._profiles_data[profile_name]
            if self._active_profile_name == profile_name:
                self._active_profile_name = _DEFAULT_PROFILE_NAME
            return self._save_to_disk()

    # =====================================================================
    # Settings API
    # =====================================================================

    def get_active_settings(self) -> Dict[str, Any]:
        """دریافت کپی ایمن از تنظیمات پروفایل فعال"""
        with self._lock:
            return copy.deepcopy(self._get_active_settings_unlocked())

    def get_settings(self) -> Dict[str, Any]:
        """Alias برای سازگاری با کدهای قدیمی"""
        return self.get_active_settings()

    def save_settings(
        self,
        new_settings: Dict[str, Any],
        profile_name: Optional[str] = None,
        set_active: bool = False,
    ) -> bool:
        """ذخیره تنظیمات با ادغام عمیق"""
        with self._lock:
            if not isinstance(new_settings, dict):
                return False

            target = profile_name or self._active_profile_name
            if not target:
                return False

            current = self._profiles_data.get(
                target, copy.deepcopy(DEFAULT_SETTINGS)
            )
            merged = self._deep_merge(current, new_settings)
            self._profiles_data[target] = merged

            if set_active:
                self._active_profile_name = target

            return self._save_to_disk()

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._get_active_settings_unlocked().get(key, default)

    def set_setting(self, key: str, value: Any) -> bool:
        with self._lock:
            settings = self.get_active_settings()
            settings[key] = value
            return self.save_settings(settings)

    # =====================================================================
    # Convenience Setters/Getters
    # =====================================================================

    def get_custom_prices(self) -> Dict[str, float]:
        """دریافت قیمت‌های دستی با تبدیل ایمن به float"""
        with self._lock:
            raw = self._get_active_settings_unlocked().get("custom_prices", {})
            if not isinstance(raw, dict):
                return {}
            result: Dict[str, float] = {}
            for k, v in raw.items():
                if v is None:
                    continue
                try:
                    fval = float(v)
                    if fval > 0:
                        result[str(k)] = fval
                except (ValueError, TypeError):
                    logger.warning(f"Invalid custom price for '{k}': {v!r}")
            return result

    def set_custom_prices(self, prices: Dict[str, float]) -> bool:
        """ذخیره قیمت‌های دستی با پاک‌سازی خودکار"""
        with self._lock:
            if not isinstance(prices, dict):
                prices = {}
            clean: Dict[str, float] = {}
            for k, v in prices.items():
                if v is None:
                    continue
                try:
                    fval = float(v)
                    if fval > 0:
                        clean[str(k)] = fval
                except (ValueError, TypeError):
                    continue

            settings = self.get_active_settings()
            settings["custom_prices"] = clean
            return self.save_settings(settings)

    def get_custom_prices_enabled(self) -> bool:
        with self._lock:
            return bool(self.get_setting("custom_prices_enabled", True))

    def set_custom_prices_enabled(self, enabled: bool) -> bool:
        return self.set_setting("custom_prices_enabled", bool(enabled))

    def get_excluded_symbols(self) -> List[str]:
        with self._lock:
            excluded = self.get_setting("excluded_symbols", [])
            if isinstance(excluded, (list, tuple, set)):
                return [str(s).strip() for s in excluded if str(s).strip()]
            return []

    def set_excluded_symbols(self, symbols: List[str]) -> bool:
        with self._lock:
            clean = [str(s).strip() for s in symbols if str(s).strip()]
            return self.set_setting("excluded_symbols", clean)

    def get_active_strategies(self) -> List[str]:
        with self._lock:
            strats = self.get_setting("active_strategies", None)
            if isinstance(strats, (list, tuple)):
                return [str(s).strip() for s in strats if str(s).strip()]
            return list(DEFAULT_SETTINGS["active_strategies"])

    def set_active_strategies(self, strategies: List[str]) -> bool:
        with self._lock:
            clean = [str(s).strip() for s in strategies if str(s).strip()]
            if hasattr(config, "ACTIVE_STRATEGIES"):
                config.ACTIVE_STRATEGIES = clean
            return self.set_setting("active_strategies", clean)

    def get_bale_config(self) -> Dict[str, Any]:
        """دریافت پیکربندی بله با پشتیبانی از ساختار flat و nested"""
        with self._lock:
            settings = self._get_active_settings_unlocked()
            bale = settings.get("bale")

            # اگر ساختار nested معتبر است
            if isinstance(bale, dict) and bale:
                return {
                    "enabled": bool(bale.get("enabled", False)),
                    "bot_token": str(bale.get("bot_token", "")),
                    "chat_id": str(bale.get("chat_id", "")),
                    "top_n": int(bale.get("top_n", 2)),
                }

            # سازگاری با ساختار flat قدیمی
            return {
                "enabled": bool(settings.get("bale_enabled", False)),
                "bot_token": str(settings.get("bale_bot_token", "")),
                "chat_id": str(settings.get("bale_chat_id", "")),
                "top_n": int(settings.get("bale_top_n", 2)),
            }

    def get_broker_config(self) -> Dict[str, Any]:
        """دریافت پیکربندی کارگزاری با پشتیبانی از ساختار flat و nested"""
        with self._lock:
            settings = self._get_active_settings_unlocked()
            broker = settings.get("broker")

            if isinstance(broker, dict) and broker:
                return {
                    "username": str(broker.get("username", "")),
                    "password": str(broker.get("password", "")),
                    "headless": bool(broker.get("headless", False)),
                }

            return {
                "username": str(settings.get("broker_username", "")),
                "password": str(settings.get("broker_password", "")),
                "headless": bool(settings.get("broker_headless", False)),
            }

    # =====================================================================
    # Factory Defaults
    # =====================================================================

    def restore_defaults(self) -> bool:
        """بازنشانی کامل تنظیمات به پیش‌فرض کارخانه"""
        with self._lock:
            self._profiles_data = {
                _DEFAULT_PROFILE_NAME: copy.deepcopy(DEFAULT_SETTINGS)
            }
            self._active_profile_name = _DEFAULT_PROFILE_NAME
            return self._save_to_disk()

    def get_defaults(self) -> Dict[str, Any]:
        """دریافت کپی از تنظیمات پیش‌فرض کارخانه"""
        return copy.deepcopy(DEFAULT_SETTINGS)

    # =====================================================================
    # Internal Helpers
    # =====================================================================

    def _get_active_settings_unlocked(self) -> Dict[str, Any]:
        """دسترسی بدون قفل به تنظیمات پروفایل فعال (فقط در متدهای قفل‌دار)"""
        if self._active_profile_name not in self._profiles_data:
            self._profiles_data[self._active_profile_name] = copy.deepcopy(
                DEFAULT_SETTINGS
            )
        return self._profiles_data[self._active_profile_name]

    def _deep_merge(
        self, base: Dict[str, Any], custom: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        ادغام عمیق دو دیکشنری.

        نکته: لیست‌ها به طور کامل جایگزین می‌شوند (نه ادغام عناصر).
        """
        result = copy.deepcopy(base)
        for k, v in custom.items():
            if (
                isinstance(v, dict)
                and k in result
                and isinstance(result[k], dict)
            ):
                result[k] = self._deep_merge(result[k], v)
            else:
                result[k] = copy.deepcopy(v)
        return result

    def _normalize_settings(
        self, settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        سازگاری با ساختار flat قدیمی → nested جدید.

        این متد تضمین می‌کند که کلیدهای bale و broker همیشه به شکل
        nested وجود داشته باشند.
        """
        normalized = copy.deepcopy(settings)

        # مهاجرت bale
        if not isinstance(normalized.get("bale"), dict):
            normalized["bale"] = {
                "enabled": bool(settings.get("bale_enabled", False)),
                "bot_token": str(settings.get("bale_bot_token", "")),
                "chat_id": str(settings.get("bale_chat_id", "")),
                "top_n": int(settings.get("bale_top_n", 2)),
            }

        # مهاجرت broker
        if not isinstance(normalized.get("broker"), dict):
            normalized["broker"] = {
                "username": str(settings.get("broker_username", "")),
                "password": str(settings.get("broker_password", "")),
                "headless": bool(settings.get("broker_headless", False)),
            }

        return normalized

    # =====================================================================
    # Disk I/O
    # =====================================================================

    def _load_from_disk(self) -> None:
        """بارگذاری از فایل JSON یا ایجاد مقادیر پیش‌فرض"""
        if not os.path.exists(self.filepath):
            logger.info(
                f"Settings file '{self.filepath}' not found. Creating default."
            )
            self._profiles_data = {
                _DEFAULT_PROFILE_NAME: copy.deepcopy(DEFAULT_SETTINGS)
            }
            self._active_profile_name = _DEFAULT_PROFILE_NAME
            self._save_to_disk()
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise ValueError("JSON root must be a dictionary")

            self._active_profile_name = str(
                data.get("active_profile", _DEFAULT_PROFILE_NAME)
            )
            profiles = data.get("profiles", {})

            if not isinstance(profiles, dict) or not profiles:
                # سازگاری با ساختار flat قدیمی (بدون profiles)
                flat = self._normalize_settings(data)
                self._profiles_data = {
                    _DEFAULT_PROFILE_NAME: self._deep_merge(
                        DEFAULT_SETTINGS, flat
                    )
                }
            else:
                self._profiles_data = {}
                for name, p_data in profiles.items():
                    if not isinstance(p_data, dict):
                        continue
                    normalized = self._normalize_settings(p_data)
                    self._profiles_data[str(name)] = self._deep_merge(
                        DEFAULT_SETTINGS, normalized
                    )

            if self._active_profile_name not in self._profiles_data:
                self._active_profile_name = list(self._profiles_data.keys())[0]

            logger.info(
                f"Settings loaded. Active profile: '{self._active_profile_name}'"
            )

        except Exception as e:
            logger.error(f"Error loading '{self.filepath}': {e}")

            # بکاپ فایل خراب برای بازیابی دستی
            try:
                backup_path = f"{self.filepath}.corrupted.{int(time.time())}"
                if os.path.exists(self.filepath):
                    os.rename(self.filepath, backup_path)
                    logger.warning(
                        f"Corrupted file backed up to {backup_path}")
            except OSError as backup_err:
                logger.error(f"Failed to backup corrupted file: {backup_err}")

            self._profiles_data = {
                _DEFAULT_PROFILE_NAME: copy.deepcopy(DEFAULT_SETTINGS)
            }
            self._active_profile_name = _DEFAULT_PROFILE_NAME
            self._save_to_disk()

    def _save_to_disk(self) -> bool:
        """ذخیره اتمیک با پاک‌سازی مطمئن فایل موقت در همه شاخه‌ها"""
        with self._lock:
            temp_path = f"{self.filepath}.tmp"
            output_payload = {
                "active_profile": self._active_profile_name,
                "profiles": self._profiles_data,
            }

            try:
                # اطمینان از وجود پوشه والد
                parent_dir = os.path.dirname(os.path.abspath(self.filepath))
                if parent_dir and not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, exist_ok=True)

                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(output_payload, f, ensure_ascii=False, indent=4)
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        pass

                os.replace(temp_path, self.filepath)
                return True

            except PermissionError as e:
                logger.error(
                    f"Cannot replace settings file (Permission Denied): {e}"
                )
                self._cleanup_temp_file(temp_path)
                return False

            except Exception as e:
                logger.error(
                    f"Failed to save settings: {e}", exc_info=True
                )
                self._cleanup_temp_file(temp_path)
                return False

    def _cleanup_temp_file(self, temp_path: str) -> None:
        """پاک‌سازی ایمن فایل موقت"""
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError as e:
            logger.debug(f"Could not remove temp file '{temp_path}': {e}")


# =========================================================================
# Singleton Instance
# =========================================================================

settings_manager = SettingsManager()