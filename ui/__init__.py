# ui/__init__.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger("OptionScanner.UI")


# ═════════════════════════════════════════════════════════════
# Importهای مستقیم (بدون وابستگی به MainWindow)
# ═════════════════════════════════════════════════════════════

from ui.strategy_inspector import StrategyInspectorWidget
from ui.payoff_chart_dialog import PayoffChartDialog
from ui.settings_dialog import SettingsDialog
from ui.strategy_settings_dialog import StrategySettingsDialog
from ui.strategy_filter_dialog import StrategyFilterDialog
from ui.symbol_filter_dialog import SymbolFilterDialog
from ui.settings_manager import settings_manager, SettingsManager
from ui.table_components import StrategyCellDelegate, get_flash_manager


# ═════════════════════════════════════════════════════════════
# MainWindow
# ═════════════════════════════════════════════════════════════

from ui.main_window import MainWindow


# ═════════════════════════════════════════════════════════════
# 🆕 SpreadAnalyzerWindow — Lazy Import
# ═════════════════════════════════════════════════════════════

def get_spread_analyzer_window():
    """
    دریافت کلاس SpreadAnalyzerWindow به صورت Lazy.

    این تابع، از Circular Import جلوگیری می‌کند چون:
    - spread_analyzer_window.py ممکن است به ui.theme و ... وابسته باشد
    - اگر در ابتدای فایل import شود، چرخه ایجاد می‌شود

    Returns:
        class: کلاس SpreadAnalyzerWindow

    Example:
        from ui import get_spread_analyzer_window
        SpreadAnalyzerWindow = get_spread_analyzer_window()
        window = SpreadAnalyzerWindow(scanner_engine=engine)
    """
    from ui.spread_analyzer_window import SpreadAnalyzerWindow
    return SpreadAnalyzerWindow


# ═════════════════════════════════════════════════════════════
# TYPE_CHECKING (فقط برای IDE — در زمان اجرا import نمی‌شود)
# ═════════════════════════════════════════════════════════════

if TYPE_CHECKING:
    from ui.spread_analyzer_window import SpreadAnalyzerWindow


# ═════════════════════════════════════════════════════════════
# __all__
# ═════════════════════════════════════════════════════════════

__all__ = [
    # پنجره‌ها
    "MainWindow",
    "get_spread_analyzer_window",

    # کامپوننت‌ها
    "StrategyInspectorWidget",
    "StrategyCellDelegate",
    "get_flash_manager",

    # دیالوگ‌ها
    "PayoffChartDialog",
    "SettingsDialog",
    "StrategySettingsDialog",
    "StrategyFilterDialog",
    "SymbolFilterDialog",

    # مدیریت تنظیمات
    "settings_manager",
    "SettingsManager",
]