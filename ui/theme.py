# ui/theme.py
# -*- coding: utf-8 -*-

"""
مدیریت پوسته (روشن/تاریک/سیستم)، استایل‌های پیشرفته UI، کارت‌های KPI و فرمت‌بندی بومی بازار سرمایه.
"""

from __future__ import annotations

import datetime
import logging
from typing import Literal, Union, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPalette, QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

import jdatetime

logger = logging.getLogger("OptionScanner.UI.Theme")

ThemeMode = Literal["light", "dark"]

THEME_LIGHT = "روشن (Light)"
THEME_DARK = "تاریک (Dark)"
THEME_SYSTEM = "سیستم (System)"

LAYOUT_RTL = "rtl"
LAYOUT_LTR = "ltr"

# ثابت‌های رنگی تریدینگ
COLOR_PROFIT_DARK = "#3fb950"
COLOR_PROFIT_LIGHT = "#2e7d32"
COLOR_LOSS_DARK = "#f85149"
COLOR_LOSS_LIGHT = "#c62828"
COLOR_WARNING = "#d29922"
COLOR_INFO = "#388bfd"
COLOR_NEUTRAL = "#8c9bae"
COLOR_ACCENT = "#8a2be2"


# =========================================================================
# ۱. مدیریت تم و جهت چیدمان (Theme & Layout Management)
# =========================================================================

def resolve_theme(theme_setting: str) -> ThemeMode:
    if theme_setting == THEME_DARK:
        return "dark"
    if theme_setting == THEME_SYSTEM:
        return "dark" if _detect_system_dark() else "light"
    return "light"


def is_dark(theme_setting: str) -> bool:
    return resolve_theme(theme_setting) == "dark"


def apply_layout_direction(app: QApplication, layout_dir: str = LAYOUT_RTL) -> None:
    """تنظیم جهت چیدمان کل برنامه (راست‌به‌چپ یا چپ‌به‌راست)"""
    if layout_dir == LAYOUT_LTR:
        app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    else:
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)


def apply_app_layout(app: QApplication) -> None:
    """اعمال RTL سراسری برای کل برنامه (رفع خطای AttributeError)"""
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)


def setup_persian_font(app: QApplication, preferred_font: str = "Vazirmatn", base_size: int = 10) -> None:
    font_candidates = [preferred_font, "Vazirmatn",
                       "Shabnam", "Sahel", "Segoe UI", "Tahoma"]
    installed_fonts = QFontDatabase.families()

    chosen_family = "Segoe UI"
    for candidate in font_candidates:
        if candidate in installed_fonts:
            chosen_family = candidate
            break

    app_font = QFont(chosen_family, base_size)
    app_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(app_font)
    logger.info(f"UI Font configured: {chosen_family} (Size: {base_size})")


def apply_app_theme(app: QApplication, theme_setting: str) -> ThemeMode:
    mode = resolve_theme(theme_setting)
    app.setProperty("theme_mode", mode)
    setup_persian_font(app)
    app.setStyleSheet(get_global_stylesheet(mode))
    _apply_palette(app, mode)
    logger.info(f"Theme applied: {theme_setting} -> {mode}")
    return mode


def current_mode(app: QApplication | None = None) -> ThemeMode:
    target = app or QApplication.instance()
    if target is None:
        return "light"
    mode = target.property("theme_mode")
    return mode if mode in ("light", "dark") else "light"


def get_global_stylesheet(mode: ThemeMode) -> str:
    if mode == "dark":
        return _DARK_GLOBAL_STYLE
    return _LIGHT_GLOBAL_STYLE


# =========================================================================
# ۲. توابع فرمت‌بندی بومی بازار ایران (Rial, DTE, Percent, Greeks)
# =========================================================================

def format_rial(value: Union[int, float, None], unit: str = "", show_sign: bool = False) -> str:
    if value is None:
        return "-"
    try:
        val_int = int(round(value))
        formatted = f"{val_int:,}"
        if show_sign and val_int > 0:
            formatted = f"+{formatted}"
        if unit:
            formatted = f"{formatted} {unit}"
        return formatted
    except (ValueError, TypeError):
        return str(value)


def format_percent(value: Union[int, float, None], decimals: int = 1, show_sign: bool = True) -> str:
    if value is None:
        return "-"
    try:
        sign = "+" if (show_sign and value > 0) else ""
        return f"{sign}{value:.{decimals}f}%"
    except (ValueError, TypeError):
        return str(value)


def format_greek(value: Union[int, float, None], decimals: int = 3) -> str:
    if value is None:
        return "-"
    try:
        return f"{value:.{decimals}f}"
    except (ValueError, TypeError):
        return str(value)


def format_jalali_date(
    date_val: Union[datetime.date, datetime.datetime, str, None],
    include_dte: bool = True
) -> str:
    if not date_val:
        return "-"

    if isinstance(date_val, str):
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
            try:
                date_val = datetime.datetime.strptime(
                    date_val.split()[0], fmt).date()
                break
            except ValueError:
                pass

    if not isinstance(date_val, (datetime.date, datetime.datetime)):
        return str(date_val)

    target_date = date_val.date() if isinstance(
        date_val, datetime.datetime) else date_val
    today = datetime.date.today()
    dte = (target_date - today).days

    j_date = jdatetime.date.fromgregorian(date=target_date)
    j_str = j_date.strftime("%Y/%m/%d")

    if include_dte:
        if dte > 0:
            return f"{j_str} ({dte} روز)"
        elif dte == 0:
            return f"{j_str} (امروز)"
        else:
            return f"{j_str} (منقضی)"

    return j_str


# =========================================================================
# ۳. توابع رنگی سود/زیان و پویانمایی
# =========================================================================

def get_pnl_colors(mode: ThemeMode) -> tuple[QColor, QColor]:
    if mode == "dark":
        return QColor(COLOR_PROFIT_DARK), QColor(COLOR_LOSS_DARK)
    return QColor(COLOR_PROFIT_LIGHT), QColor(COLOR_LOSS_LIGHT)


def get_pnl_qcolor(value: Union[int, float, None], mode: ThemeMode = "dark", alpha: int = 255) -> QColor:
    if value is None or value == 0:
        c = QColor(COLOR_NEUTRAL)
    elif value > 0:
        c = QColor(COLOR_PROFIT_DARK if mode == "dark" else COLOR_PROFIT_LIGHT)
    else:
        c = QColor(COLOR_LOSS_DARK if mode == "dark" else COLOR_LOSS_LIGHT)
    c.setAlpha(alpha)
    return c


def get_flash_qcolor(direction: str, alpha: int = 180) -> QColor:
    if direction.upper() in ("UP", "BUY", "PROFIT"):
        return QColor(46, 133, 64, alpha)
    elif direction.upper() in ("DOWN", "SELL", "LOSS"):
        return QColor(197, 48, 48, alpha)
    return QColor(43, 108, 176, alpha)


def get_empty_state_color(mode: ThemeMode) -> QColor:
    return QColor(138, 146, 156) if mode == "dark" else QColor(150, 150, 150)


# =========================================================================
# ۴. استایل‌های المان‌های پیشرفته و کارت‌های KPI و فیلترها
# =========================================================================

def get_kpi_card_style(mode: ThemeMode, accent_color: str = "#388bfd") -> str:
    bg = "#161b22" if mode == "dark" else "#ffffff"
    border = "#30363d" if mode == "dark" else "#e1e4e8"
    return f"""
        QFrame {{
            background-color: {bg};
            border: 1px solid {border};
            border-top: 3px solid {accent_color};
            border-radius: 8px;
            padding: 8px 10px;
        }}
    """


def get_filter_chip_style(active: bool, mode: str) -> str:
    """استایل یکپارچه چیپ‌های فیلتر سریع"""
    is_dark = (mode == "dark")
    if active:
        bg = "#1f6feb" if is_dark else "#0969da"
        color = "#ffffff"
        border = "1px solid #388bfd" if is_dark else "1px solid #0969da"
    else:
        bg = "#21262d" if is_dark else "#f6f8fa"
        color = "#cdd9e5" if is_dark else "#57606a"
        border = "1px solid #30363d" if is_dark else "1px solid #d0d7de"

    return f"""
        QPushButton {{
            background-color: {bg};
            color: {color};
            border: {border};
            border-radius: 14px;
            padding: 4px 12px;
            font-size: 11px;
        }}
        QPushButton:hover {{
            border-color: {"#58a6ff" if is_dark else "#0969da"};
        }}
    """


def get_toolbar_frame_style(mode: ThemeMode) -> str:
    bg = "#161b22" if mode == "dark" else "#ffffff"
    border = "#30363d" if mode == "dark" else "#e1e4e8"
    return f"""
        QFrame {{
            background-color: {bg};
            border: 1px solid {border};
            border-radius: 8px;
            padding: 6px 10px;
        }}
    """


def get_separator_style(mode: ThemeMode) -> str:
    color = "#30363d" if mode == "dark" else "#d0d7de"
    return f"background-color: {color};"


def get_interval_label_style(mode: ThemeMode) -> str:
    color = "#8b949e" if mode == "dark" else "#666"
    return f"color: {color}; font-size: 11px;"


def get_inspector_frame_style(mode: ThemeMode) -> str:
    bg = "#0d1117" if mode == "dark" else "#ffffff"
    border = "#30363d" if mode == "dark" else "#e2e8f0"
    return f"background-color: {bg}; border: 1px solid {border}; border-radius: 8px;"


def get_symbol_filter_info_style(mode: ThemeMode) -> str:
    color = "#8b949e" if mode == "dark" else "#2c3e50"
    return f"font-weight: bold; color: {color};"


def get_info_banner_style(mode: ThemeMode) -> str:
    bg = "#161b22" if mode == "dark" else "#f0f2f5"
    border = "#30363d" if mode == "dark" else "#d0d7de"
    color = "#8b949e" if mode == "dark" else "#2c3e50"
    return f"background-color: {bg}; border: 1px solid {border}; border-radius: 4px; padding: 8px; color: {color};"


def get_sub_panel_style(mode: ThemeMode) -> str:
    bg = "#161b22" if mode == "dark" else "#f0f2f5"
    border = "#30363d" if mode == "dark" else "#d0d7de"
    return f"background-color: {bg}; border: 1px dashed {border}; border-radius: 4px; padding: 2px;"


def get_disabled_table_style(mode: ThemeMode) -> str:
    bg = "#2b2b2b" if mode == "dark" else "#f0f2f5"
    fg = "#777" if mode == "dark" else "#666"
    return f"QTableWidget {{ background-color: {bg}; color: {fg}; }}"


def get_greek_label_style(mode: ThemeMode) -> str:
    bg = "rgba(255,255,255,0.04)" if mode == "dark" else "rgba(0,0,0,0.04)"
    return f"font-weight: bold; background-color: {bg}; border-radius: 4px; padding: 4px;"


def get_preset_button_style(mode: ThemeMode) -> str:
    bg = "#21262d" if mode == "dark" else "#f0f2f5"
    fg = "#8b949e" if mode == "dark" else "#57606a"
    border = "#30363d" if mode == "dark" else "#d0d7de"
    hover_bg = "#30363d" if mode == "dark" else "#e1e4e8"
    hover_fg = "#58a6ff"
    hover_border = "#58a6ff"
    return f"""
        QPushButton {{
            background-color: {bg};
            color: {fg};
            border: 1px solid {border};
            border-radius: 4px;
            padding: 2px 7px;
            font-size: 11px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {hover_bg};
            color: {hover_fg};
            border-color: {hover_border};
        }}
    """


def get_symbol_filter_stats_style(mode: ThemeMode) -> str:
    if mode == "dark":
        return (
            "color: #8b949e; font-size: 9pt; padding: 6px; "
            "background-color: #161b22; border-radius: 4px;"
        )
    return (
        "color: #34495e; font-size: 9pt; padding: 6px; "
        "background-color: #ecf0f1; border-radius: 4px;"
    )


def get_dialog_profile_frame_style(mode: ThemeMode) -> str:
    if mode == "dark":
        return "QFrame { background:#21262d; border-radius:8px; padding:6px; }"
    return "QFrame { background:#f0f2f5; border-radius:8px; padding:6px; }"


def get_button_style(mode: str, role: str = "primary") -> str:
    """تولید استایل یکپارچه برای تمام دکمه‌های برنامه"""
    is_dark = (mode == "dark")

    styles = {
        "primary": {
            "bg": "#1f6feb" if is_dark else "#0969da",
            "hover": "#388bfd" if is_dark else "#1f883d",
            "text": "#ffffff",
            "border": "none"
        },
        "secondary": {
            "bg": "#21262d" if is_dark else "#f6f8fa",
            "hover": "#30363d" if is_dark else "#eef1f5",
            "text": "#cdd9e5" if is_dark else "#24292f",
            "border": "1px solid #30363d" if is_dark else "1px solid #d0d7de"
        },
        "success": {
            "bg": "#238636" if is_dark else "#1f883d",
            "hover": "#2ea043" if is_dark else "#1a7f37",
            "text": "#ffffff",
            "border": "none"
        },
        "danger": {
            "bg": "#da3633" if is_dark else "#cf222e",
            "hover": "#f85149" if is_dark else "#a40e26",
            "text": "#ffffff",
            "border": "none"
        },
        "warning": {
            "bg": "#9e6a03" if is_dark else "#d97706",
            "hover": "#b07804" if is_dark else "#b45309",
            "text": "#ffffff",
            "border": "none"
        }
    }

    style = styles.get(role, styles["primary"])

    return f"""
        QPushButton {{
            background-color: {style['bg']};
            color: {style['text']};
            border: {style['border']};
            border-radius: 6px;
            padding: 6px 12px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {style['hover']};
        }}
        QPushButton:disabled {{
            background-color: {"#161b22" if is_dark else "#eef1f5"};
            color: {"#484f58" if is_dark else "#8c959f"};
            border: {"1px solid #30363d" if is_dark else "1px solid #d0d7de"};
        }}
    """


def get_accent_button_style(mode: ThemeMode, accent: str = "#8a2be2", hover: str = "#a855f7") -> str:
    if mode == "light":
        bg = "#7b1fa2"
        hover_bg = "#9c27b0"
    else:
        bg = accent
        hover_bg = hover
    return f"""
        QPushButton {{
            background-color: {bg};
            color: white;
            border: none;
            border-radius: 5px;
            padding: 8px 15px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {hover_bg}; }}
    """


def get_dialog_tab_style(mode: ThemeMode) -> str:
    if mode == "dark":
        return """
            QTabWidget::pane { border:1px solid #30363d; border-radius:6px; padding:10px; background:#161b22; }
            QTabBar::tab { padding:8px 16px; margin-right:4px; border-radius:4px; color:#8b949e; }
            QTabBar::tab:selected { background:#1f6feb; color:white; }
        """
    return """
        QTabWidget::pane { border:1px solid #d0d7de; border-radius:6px; padding:10px; }
        QTabBar::tab { padding:8px 16px; margin-right:4px; border-radius:4px; }
        QTabBar::tab:selected { background:#4a6fa5; color:white; }
    """


def get_dialog_warning_banner_style(mode: ThemeMode) -> str:
    if mode == "dark":
        return "background:#3d2e00; border:1px solid #d29922; border-radius:6px; padding:10px; color:#e3b341;"
    return "background:#fff3cd; border:1px solid #ffc107; border-radius:6px; padding:10px; color:#856404;"


def _detect_system_dark() -> bool:
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        return scheme == Qt.ColorScheme.Dark
    except Exception:
        pass
    return False


def _apply_palette(app: QApplication, mode: ThemeMode) -> None:
    palette = QPalette()
    if mode == "dark":
        palette.setColor(QPalette.ColorRole.Window, QColor(13, 17, 23))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(205, 217, 229))
        palette.setColor(QPalette.ColorRole.Base, QColor(22, 27, 34))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(13, 17, 23))
        palette.setColor(QPalette.ColorRole.Text, QColor(205, 217, 229))
        palette.setColor(QPalette.ColorRole.Button, QColor(33, 38, 45))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(205, 217, 229))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(56, 139, 253))
        palette.setColor(QPalette.ColorRole.HighlightedText,
                         QColor(255, 255, 255))
    else:
        palette = app.style().standardPalette()
    app.setPalette(palette)


_LIGHT_GLOBAL_STYLE = """
QMainWindow, QDialog { background-color: #f6f8fa; }
QWidget { color: #24292e; font-family: 'Vazirmatn', 'Shabnam', 'Segoe UI', Tahoma, sans-serif; }
QTableView, QTableWidget {
    background-color: white;
    alternate-background-color: #f6f8fa;
    gridline-color: #e1e4e8;
    selection-background-color: #cfe2ff;
    selection-color: #000000;
    color: #24292e;
    border: 1px solid #d0d7de;
    border-radius: 6px;
}
QHeaderView::section {
    background-color: #f6f8fa;
    color: #24292e;
    padding: 6px;
    border: 1px solid #d0d7de;
    font-weight: bold;
    font-size: 11px;
}
QPushButton {
    background-color: #f6f8fa;
    color: #24292f;
    border: 1px solid #d0d7de;
    padding: 6px 14px;
    border-radius: 6px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #f3f4f6;
    border-color: #0969da;
    color: #0969da;
}
QMenu { background-color: white; color: #24292e; border: 1px solid #d0d7de; border-radius: 6px; padding: 4px 0; }
QMenu::item { padding: 8px 24px 8px 16px; }
QMenu::item:selected { background-color: #e8f0fe; color: #1a73e8; }
QGroupBox { font-weight: bold; border: 1px solid #d0d7de; border-radius: 6px; margin-top: 10px; padding: 10px; background-color: #ffffff; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top right; padding: 0 6px; color: #1f6feb; }
QProgressBar { border: 1px solid #d0d7de; border-radius: 4px; text-align: center; color: #24292e; }
QProgressBar::chunk { background-color: #2ea043; border-radius: 4px; }
QStatusBar { background-color: #ffffff; border-top: 1px solid #d0d7de; color: #57606a; }
"""

_DARK_GLOBAL_STYLE = """
QMainWindow, QDialog { background-color: #0d1117; }
QWidget { color: #cdd9e5; font-family: 'Vazirmatn', 'Shabnam', 'Segoe UI', Tahoma, sans-serif; }
QTableView, QTableWidget {
    background-color: #161b22;
    alternate-background-color: #0d1117;
    gridline-color: #30363d;
    selection-background-color: #1f3a5f;
    selection-color: #ffffff;
    color: #cdd9e5;
    border: 1px solid #30363d;
    border-radius: 6px;
}
QHeaderView::section {
    background-color: #161b22;
    color: #8b949e;
    padding: 6px;
    border: 1px solid #30363d;
    font-weight: bold;
    font-size: 11px;
}
QPushButton {
    background-color: #21262d;
    color: #cdd9e5;
    border: 1px solid #30363d;
    padding: 6px 14px;
    border-radius: 6px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #30363d;
    border-color: #58a6ff;
    color: #58a6ff;
}
QMenu { background-color: #161b22; color: #cdd9e5; border: 1px solid #30363d; border-radius: 6px; padding: 4px 0; }
QMenu::item { padding: 8px 24px 8px 16px; }
QMenu::item:selected { background-color: #1f3a5f; color: #58a6ff; }
QGroupBox { font-weight: bold; border: 1px solid #30363d; border-radius: 6px; margin-top: 10px; padding: 10px; background-color: #161b22; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top right; padding: 0 6px; color: #58a6ff; }
QProgressBar { border: 1px solid #30363d; border-radius: 4px; text-align: center; color: #cdd9e5; background-color: #161b22; }
QProgressBar::chunk { background-color: #238636; border-radius: 4px; }
QStatusBar { background-color: #161b22; border-top: 1px solid #30363d; color: #8b949e; }
"""
