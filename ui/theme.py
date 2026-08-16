# ui/theme.py
# -*- coding: utf-8 -*-

"""مدیریت پوسته (روشن/تاریک/سیستم) و استایل‌های مشترک UI."""

from __future__ import annotations

import logging
from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPalette, QColor
from PySide6.QtWidgets import QApplication

logger = logging.getLogger("OptionScanner.UI.Theme")

ThemeMode = Literal["light", "dark"]

THEME_LIGHT = "روشن (Light)"
THEME_DARK = "تاریک (Dark)"
THEME_SYSTEM = "سیستم (System)"


def resolve_theme(theme_setting: str) -> ThemeMode:
    """تبدیل مقدار ذخیره‌شده تنظیمات به light یا dark."""
    if theme_setting == THEME_DARK:
        return "dark"
    if theme_setting == THEME_SYSTEM:
        return "dark" if _detect_system_dark() else "light"
    return "light"


def is_dark(theme_setting: str) -> bool:
    return resolve_theme(theme_setting) == "dark"


def apply_app_layout(app: QApplication) -> None:
    """اعمال RTL سراسری برای کل برنامه."""
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)


def apply_app_theme(app: QApplication, theme_setting: str) -> ThemeMode:
    """اعمال پوسته روی QApplication و palette."""
    mode = resolve_theme(theme_setting)
    app.setProperty("theme_mode", mode)
    app.setStyleSheet(get_global_stylesheet(mode))
    _apply_palette(app, mode)
    logger.info(f"Theme applied: {theme_setting} -> {mode}")
    return mode


def get_global_stylesheet(mode: ThemeMode) -> str:
    if mode == "dark":
        return _DARK_GLOBAL_STYLE
    return _LIGHT_GLOBAL_STYLE


def get_toolbar_frame_style(mode: ThemeMode) -> str:
    bg = "#2d333b" if mode == "dark" else "white"
    return f"""
        QFrame {{
            background-color: {bg};
            border-radius: 8px;
            padding: 10px;
        }}
    """


def get_separator_style(mode: ThemeMode) -> str:
    color = "#444c56" if mode == "dark" else "#d0d7de"
    return f"background-color: {color};"


def get_interval_label_style(mode: ThemeMode) -> str:
    color = "#adbac7" if mode == "dark" else "#666"
    return f"color: {color}; font-size: 11px;"


def get_broker_connect_style(mode: ThemeMode, connected: bool = False) -> str:
    if connected:
        return (
            "QPushButton { background-color: #1b5e20; color: white; "
            "font-weight: bold; padding: 8px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #145214; }"
        )
    base = "#6d4c41" if mode == "dark" else "#5d4037"
    hover = "#5d4037" if mode == "dark" else "#4e342e"
    return (
        f"QPushButton {{ background-color: {base}; color: white; "
        f"font-weight: bold; padding: 8px 16px; border-radius: 4px; }}"
        f"QPushButton:hover {{ background-color: {hover}; }}"
    )


def get_send_bale_style(mode: ThemeMode) -> str:
    base = "#9b59b6" if mode == "dark" else "#7b2d8b"
    hover = "#7d3c98" if mode == "dark" else "#5e2070"
    disabled_bg = "#484f58" if mode == "dark" else "#b8c4d0"
    disabled_fg = "#768390" if mode == "dark" else "#7a8a9a"
    return (
        f"QPushButton#btn_send_bale {{ background-color: {base}; }}"
        f"QPushButton#btn_send_bale:hover {{ background-color: {hover}; }}"
        f"QPushButton#btn_send_bale:disabled {{ background-color: {disabled_bg}; color: {disabled_fg}; }}"
    )


def get_export_excel_style(mode: ThemeMode) -> str:
    base = "#238636" if mode == "dark" else "#1a6b3a"
    hover = "#2ea043" if mode == "dark" else "#145230"
    disabled_bg = "#484f58" if mode == "dark" else "#b8c4d0"
    disabled_fg = "#768390" if mode == "dark" else "#7a8a9a"
    return (
        f"QPushButton {{ background-color: {base}; }}"
        f"QPushButton:hover {{ background-color: {hover}; }}"
        f"QPushButton:disabled {{ background-color: {disabled_bg}; color: {disabled_fg}; }}"
    )


def get_empty_state_color(mode: ThemeMode) -> QColor:
    return QColor(138, 146, 156) if mode == "dark" else QColor(150, 150, 150)


def get_pnl_colors(mode: ThemeMode) -> tuple[QColor, QColor]:
    if mode == "dark":
        return QColor(63, 185, 80), QColor(248, 81, 73)
    return QColor(0, 128, 0), QColor(200, 0, 0)


def get_dialog_profile_frame_style(mode: ThemeMode) -> str:
    if mode == "dark":
        return "QFrame { background:#2d333b; border-radius:8px; padding:6px; }"
    return "QFrame { background:#f0f2f5; border-radius:8px; padding:6px; }"


def get_dialog_tab_style(mode: ThemeMode) -> str:
    if mode == "dark":
        return """
            QTabWidget::pane { border:1px solid #444c56; border-radius:6px; padding:10px; background:#22272e; }
            QTabBar::tab { padding:8px 16px; margin-right:4px; border-radius:4px; color:#adbac7; }
            QTabBar::tab:selected { background:#388bfd; color:white; }
        """
    return """
        QTabWidget::pane { border:1px solid #d0d7de; border-radius:6px; padding:10px; }
        QTabBar::tab { padding:8px 16px; margin-right:4px; border-radius:4px; }
        QTabBar::tab:selected { background:#4a6fa5; color:white; }
    """


def get_dialog_warning_banner_style(mode: ThemeMode) -> str:
    if mode == "dark":
        return (
            "background:#3d2e00; border:1px solid #d29922; border-radius:6px;"
            " padding:10px; color:#e3b341;"
        )
    return (
        "background:#fff3cd; border:1px solid #ffc107; border-radius:6px;"
        " padding:10px; color:#856404;"
    )


def get_symbol_filter_info_style(mode: ThemeMode) -> str:
    color = "#adbac7" if mode == "dark" else "#2c3e50"
    return f"font-weight: bold; color: {color};"


def get_symbol_filter_stats_style(mode: ThemeMode) -> str:
    if mode == "dark":
        return (
            "color: #adbac7; font-size: 9pt; padding: 6px; "
            "background-color: #2d333b; border-radius: 4px;"
        )
    return (
        "color: #34495e; font-size: 9pt; padding: 6px; "
        "background-color: #ecf0f1; border-radius: 4px;"
    )


def current_mode(app: QApplication | None = None) -> ThemeMode:
    target = app or QApplication.instance()
    if target is None:
        return "light"
    mode = target.property("theme_mode")
    return mode if mode in ("light", "dark") else "light"


def _detect_system_dark() -> bool:
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        return scheme == Qt.ColorScheme.Dark
    except Exception:
        pass

    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return value == 0
    except Exception:
        return False


def _apply_palette(app: QApplication, mode: ThemeMode) -> None:
    palette = QPalette()
    if mode == "dark":
        palette.setColor(QPalette.ColorRole.Window, QColor(34, 39, 46))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(205, 217, 229))
        palette.setColor(QPalette.ColorRole.Base, QColor(45, 51, 59))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(34, 39, 46))
        palette.setColor(QPalette.ColorRole.Text, QColor(205, 217, 229))
        palette.setColor(QPalette.ColorRole.Button, QColor(45, 51, 59))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(205, 217, 229))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(56, 139, 253))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    else:
        palette = app.style().standardPalette()
    app.setPalette(palette)


_LIGHT_GLOBAL_STYLE = """
QMainWindow, QDialog {
    background-color: #f5f7fa;
}
QWidget {
    color: #24292e;
}
QTableWidget {
    background-color: white;
    alternate-background-color: #f8f9fc;
    gridline-color: #e1e4e8;
    selection-background-color: #cfe2ff;
    color: #24292e;
}
QTableWidget::item {
    padding: 4px;
}
QHeaderView::section {
    background-color: #3b5998;
    color: white;
    padding: 6px;
    border: 1px solid #2d4373;
    font-weight: bold;
    font-size: 11px;
}
QPushButton {
    background-color: #4a6fa5;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #3d5f8a;
}
QPushButton:pressed {
    background-color: #2e4a6b;
}
QPushButton:disabled {
    background-color: #b8c4d0;
    color: #7a8a9a;
}
QPushButton#btn_send_broker {
    background-color: #2e7d32;
}
QPushButton#btn_send_broker:hover {
    background-color: #1b5e20;
}
QToolButton {
    background-color: #4a6fa5;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
}
QToolButton:hover {
    background-color: #3d5f8a;
}
QToolButton:pressed {
    background-color: #2e4a6b;
}
QToolButton::menu-indicator {
    subcontrol-origin: padding;
    subcontrol-position: left center;
    left: 6px;
}
QToolButton#menu_broker {
    background-color: #5d4037;
}
QToolButton#menu_broker:hover {
    background-color: #4e342e;
}
QToolButton#menu_share {
    background-color: #7b2d8b;
}
QToolButton#menu_share:hover {
    background-color: #5e2070;
}
QMenu {
    background-color: white;
    color: #24292e;
    border: 1px solid #d0d7de;
    border-radius: 4px;
    padding: 4px 0;
}
QMenu::item {
    padding: 8px 28px 8px 16px;
}
QMenu::item:selected {
    background-color: #cfe2ff;
}
QMenu::item:disabled {
    color: #7a8a9a;
}
QCheckBox {
    font-weight: bold;
}
QSpinBox, QLineEdit, QComboBox, QTextEdit {
    padding: 4px;
    border: 1px solid #d0d7de;
    border-radius: 4px;
    min-height: 22px;
    background-color: white;
    color: #24292e;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width: 16px;
}
QGroupBox {
    font-weight: bold;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    right: 10px;
    padding: 0 6px;
}
QLabel {
    color: #24292e;
}
QProgressBar {
    border: 1px solid #d0d7de;
    border-radius: 4px;
    text-align: center;
    color: #24292e;
}
QProgressBar::chunk {
    background-color: #4a6fa5;
    border-radius: 4px;
}
QStatusBar {
    background-color: #eef1f5;
    color: #24292e;
}
QListWidget {
    background-color: white;
    alternate-background-color: #f8f9fc;
    border: 1px solid #d0d7de;
    border-radius: 4px;
}
"""

_DARK_GLOBAL_STYLE = """
QMainWindow, QDialog {
    background-color: #22272e;
}
QWidget {
    color: #cdd9e5;
}
QTableWidget {
    background-color: #2d333b;
    alternate-background-color: #22272e;
    gridline-color: #444c56;
    selection-background-color: #264f78;
    color: #cdd9e5;
}
QTableWidget::item {
    padding: 4px;
}
QHeaderView::section {
    background-color: #1f4788;
    color: #e6edf3;
    padding: 6px;
    border: 1px solid #388bfd;
    font-weight: bold;
    font-size: 11px;
}
QPushButton {
    background-color: #388bfd;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #1f6feb;
}
QPushButton:pressed {
    background-color: #1158c7;
}
QPushButton:disabled {
    background-color: #484f58;
    color: #768390;
}
QPushButton#btn_send_broker {
    background-color: #238636;
}
QPushButton#btn_send_broker:hover {
    background-color: #2ea043;
}
QToolButton {
    background-color: #388bfd;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 4px;
    font-weight: bold;
}
QToolButton:hover {
    background-color: #1f6feb;
}
QToolButton:pressed {
    background-color: #1158c7;
}
QToolButton::menu-indicator {
    subcontrol-origin: padding;
    subcontrol-position: left center;
    left: 6px;
}
QToolButton#menu_broker {
    background-color: #6d4c41;
}
QToolButton#menu_broker:hover {
    background-color: #5d4037;
}
QToolButton#menu_share {
    background-color: #9b59b6;
}
QToolButton#menu_share:hover {
    background-color: #7d3c98;
}
QMenu {
    background-color: #2d333b;
    color: #cdd9e5;
    border: 1px solid #444c56;
    border-radius: 4px;
    padding: 4px 0;
}
QMenu::item {
    padding: 8px 28px 8px 16px;
}
QMenu::item:selected {
    background-color: #264f78;
}
QMenu::item:disabled {
    color: #768390;
}
QCheckBox {
    font-weight: bold;
    color: #cdd9e5;
}
QSpinBox, QLineEdit, QComboBox, QTextEdit, QDoubleSpinBox {
    padding: 4px;
    border: 1px solid #444c56;
    border-radius: 4px;
    min-height: 22px;
    background-color: #2d333b;
    color: #cdd9e5;
}
QComboBox QAbstractItemView {
    background-color: #2d333b;
    color: #cdd9e5;
    selection-background-color: #264f78;
}
QGroupBox {
    font-weight: bold;
    border: 1px solid #444c56;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 10px;
    color: #cdd9e5;
}
QGroupBox::title {
    subcontrol-origin: margin;
    right: 10px;
    padding: 0 6px;
}
QLabel {
    color: #cdd9e5;
}
QProgressBar {
    border: 1px solid #444c56;
    border-radius: 4px;
    text-align: center;
    color: #cdd9e5;
    background-color: #2d333b;
}
QProgressBar::chunk {
    background-color: #388bfd;
    border-radius: 4px;
}
QStatusBar {
    background-color: #1c2128;
    color: #adbac7;
}
QListWidget {
    background-color: #2d333b;
    alternate-background-color: #22272e;
    border: 1px solid #444c56;
    border-radius: 4px;
    color: #cdd9e5;
}
QTabWidget::pane {
    border: 1px solid #444c56;
    background: #22272e;
}
QDialogButtonBox QPushButton {
    min-width: 90px;
}
"""
