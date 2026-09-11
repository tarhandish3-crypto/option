# ui/__init__.py
# -*- coding: utf-8 -*-

# فقط مواردی که به MainWindow وابسته نیستند را import کنید
from ui.strategy_inspector import StrategyInspectorWidget
from ui.payoff_chart_dialog import PayoffChartDialog
from ui.settings_dialog import SettingsDialog
from ui.strategy_settings_dialog import StrategySettingsDialog
from ui.strategy_filter_dialog import StrategyFilterDialog
from ui.symbol_filter_dialog import SymbolFilterDialog
from ui.settings_manager import settings_manager, SettingsManager
from ui.table_components import StrategyCellDelegate, get_flash_manager

from ui.main_window import MainWindow

__all__ = [
    "MainWindow",
    "StrategyInspectorWidget",
    "PayoffChartDialog",
    "SettingsDialog",
    "StrategySettingsDialog",
    "StrategyFilterDialog",
    "SymbolFilterDialog",
    "settings_manager",
    "SettingsManager",
    "StrategyCellDelegate",
    "get_flash_manager",
]