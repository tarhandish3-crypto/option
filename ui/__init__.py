# ui/__init__.py
# -*- coding: utf-8 -*-

"""
ماژول رابط کاربری (UI) پروژه Option Strategy Scanner
"""

import logging

logger = logging.getLogger(__name__)

# خروجی‌های اصلی ماژول جهت دسترسی ساده‌تر
__all__ = [
    "MainWindow",
    "ScannerWorker",
    "AutoScannerWorker",
    "SymbolFilterDialog",
    "SettingsDialog",
]

# ۱. وارد کردن پنجره اصلی
try:
    from ui.main_window import MainWindow
except ImportError as e:
    logger.warning(f"دسترسی به MainWindow امکان‌پذیر نیست: {e}")
    MainWindow = None

# ۲. وارد کردن ورکرهای پس‌زمینه (Multithreading)
try:
    from ui.workers import ScannerWorker, AutoScannerWorker
except ImportError as e:
    logger.warning(f"دسترسی به ورکرهای پس‌زمینه امکان‌پذیر نیست: {e}")
    ScannerWorker = None
    AutoScannerWorker = None

# ۳. وارد کردن پنجره‌های دیالوگ (در صورت وجود)
try:
    from ui.symbol_filter_dialog import SymbolFilterDialog
except ImportError:
    SymbolFilterDialog = None

try:
    from ui.settings_dialog import SettingsDialog
except ImportError:
    SettingsDialog = None
