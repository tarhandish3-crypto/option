# ui/__init__.py
# -*- coding: utf-8 -*-

"""
ماژول رابط کاربری (UI) پروژه Option Strategy Scanner
شامل پنجره‌های اصلی، دیالوگ‌های تنظیمات، ورکرهای پس‌زمینه و کامپوننت‌های گرافیکی.
"""

import logging

logger = logging.getLogger("OptionScanner.UI")

# لیست اجزای عمومی ماژول جهت دسترسی سریع‌تر
__all__ = [
    # پنجره اصلی و پنل‌های جانبی
    "MainWindow",
    "StrategyInspectorWidget",
    
    # دیالوگ‌ها
    "SettingsDialog",
    "SymbolFilterDialog",
    "StrategySettingsDialog",
    "PayoffChartDialog",
    
    # ورکرهای پس‌زمینه و مدیریت داده
    "ScannerWorker",
    "AutoScannerWorker",
    "BrokerLoginWorker",
    "StrategyExecutorWorker",
    "TelemetryWorker",
    "BatchUpdateManager",
    
    # مدل‌ها و کامپوننت‌های جدول
    "FastStrategyTableModel",
    "StrategyFilterProxyModel",
    "StrategyCellDelegate",
    
    # مدیریت تنظیمات و تم
    "settings_manager",
    "SettingsManager",
]

# ۱. وارد کردن پنجره اصلی و پنل‌های بازرسی
try:
    from ui.main_window import MainWindow, StrategyInspectorWidget
except ImportError as e:
    logger.warning(f"MainWindow components are not accessible: {e}")
    MainWindow = None
    StrategyInspectorWidget = None

# ۲. وارد کردن پنجره‌های دیالوگ
try:
    from ui.settings_dialog import SettingsDialog
except ImportError:
    SettingsDialog = None

try:
    from ui.symbol_filter_dialog import SymbolFilterDialog
except ImportError:
    SymbolFilterDialog = None

try:
    from ui.strategy_settings_dialog import StrategySettingsDialog
except ImportError:
    StrategySettingsDialog = None

try:
    from ui.payoff_chart_dialog import PayoffChartDialog
except ImportError:
    PayoffChartDialog = None

# ۳. وارد کردن ورکرهای پس‌زمینه و تلمتری (Multithreading)
try:
    from ui.workers import (
        ScannerWorker,
        AutoScannerWorker,
        BrokerLoginWorker,
        StrategyExecutorWorker,
        TelemetryWorker,
        BatchUpdateManager,
    )
except ImportError as e:
    logger.warning(f"Background workers are not accessible: {e}")
    ScannerWorker = None
    AutoScannerWorker = None
    BrokerLoginWorker = None
    StrategyExecutorWorker = None
    TelemetryWorker = None
    BatchUpdateManager = None


# ۵. مدیریت تنظیمات
try:
    from ui.settings_manager import settings_manager, SettingsManager
except ImportError:
    settings_manager = None
    SettingsManager = None