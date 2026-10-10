# ui/theme.py
# -*- coding: utf-8 -*-

"""
مدیریت پوسته (روشن/تاریک/سیستم) — نسخه‌ی بازطراحی‌شده.

ایده‌ی اصلی:
  ۱. همه‌ی رنگ‌ها فقط یک‌جا تعریف می‌شوند: tokens(mode)
  ۲. یک QSS سراسری از روی همین توکن‌ها ساخته می‌شود (get_global_stylesheet)
     و ویجت‌ها با objectName / property انتخاب می‌شوند، نه با setStyleSheet پراکنده:
        QFrame#card            کارت‌های نوار ابزار و پنل‌ها
        QPushButton[role=...]  primary | success | danger | warning
        QPushButton[chip=true] چیپ‌های فیلتر (+ [active=true])
        QLabel[pill=...]       ok | err | warn | idle  (نشانگرهای نوار وضعیت)
  ۳. تمام توابع قدیمی (get_button_style و ...) باقی مانده‌اند و حالا رنگ‌های
     جدید را برمی‌گردانند؛ پس دیالوگ‌های قدیمی بدون تغییر هم هم‌رنگ می‌شوند.
"""

from __future__ import annotations

import logging
from pathlib import Path
from string import Template
from typing import Dict, Literal, Union

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QPalette, QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QWidget

logger = logging.getLogger("OptionScanner.UI.Theme")

ThemeMode = Literal["light", "dark"]

THEME_LIGHT = "روشن (Light)"
THEME_DARK = "تاریک (Dark)"
THEME_SYSTEM = "سیستم (System)"

LAYOUT_RTL = "rtl"
LAYOUT_LTR = "ltr"


# =========================================================================
# ۰. توکن‌های رنگی — تنها منبع حقیقت برای همه‌ی رنگ‌ها
# =========================================================================

_BASE_TOKENS: Dict[str, Dict[str, str]] = {
    "dark": {
        "bg": "#0A0F1E",
        "sf": "#111833",
        "sf2": "#172042",
        "bd": "#252F55",
        "bd2": "#3A4670",
        "tx": "#E8ECF8",
        "mu": "#93A0C4",
        "mu_dis": "#5E6A91",
        "pr": "#3865EC",
        "pr_h": "#4D77F5",
        "prt": "#8FB0FF",
        "ok": "#3DDC97",
        "er": "#FF7A8A",
        "wn": "#FFC857",
        "ok_btn": "#0B8A5C", "ok_btn_h": "#0FA06B",
        "er_btn": "#D12F46", "er_btn_h": "#E5435A",
        "wn_btn": "#B7791F", "wn_btn_h": "#CC8A2B",
        "hover": "#1D2756",
        "sel": "#1B2650",
        "input_bg": "#0A0F1E",
        "scroll": "#2E3A63", "scroll_h": "#46568C",
        "shadow": "#000000",
    },
    "light": {
        "bg": "#EEF1F8",
        "sf": "#FFFFFF",
        "sf2": "#F4F6FC",
        "bd": "#DCE2F0",
        "bd2": "#B7C0D9",
        "tx": "#12182B",
        "mu": "#566280",
        "mu_dis": "#9AA5C0",
        "pr": "#2F5BE0",
        "pr_h": "#4A72EE",
        "prt": "#2F5BE0",
        "ok": "#0B8A5C",
        "er": "#CF3149",
        "wn": "#A86A0C",
        "ok_btn": "#0B8A5C", "ok_btn_h": "#0E9D69",
        "er_btn": "#D12F46", "er_btn_h": "#E04258",
        "wn_btn": "#C07A13", "wn_btn_h": "#D58A1F",
        "hover": "#EBEFFA",
        "sel": "#E7EDFD",
        "input_bg": "#FFFFFF",
        "scroll": "#C9D1E6", "scroll_h": "#A9B4D2",
        "shadow": "#1E2A5A",
    },
}


def _rgba(hex_color: str, alpha: int) -> str:
    """رنگ hex → رشته‌ی rgba(r,g,b,a) سازگار با QSS (alpha بین ۰ تا ۲۵۵)."""
    c = QColor(hex_color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


def _norm_mode(mode: str | None) -> ThemeMode:
    return "dark" if mode == "dark" else "light"


def tokens(mode: str | None = None) -> Dict[str, str]:
    """
    دیکشنری رنگ‌های پوسته (همراه با نسخه‌های نیمه‌شفاف *_soft و *_line).
    اگر mode داده نشود، پوسته‌ی فعلی برنامه استفاده می‌شود.
    """
    m = _norm_mode(mode if mode is not None else current_mode())
    t = dict(_BASE_TOKENS[m])
    t["pr_soft"] = _rgba(t["pr"], 46)
    t["ok_soft"] = _rgba(t["ok"], 38)
    t["er_soft"] = _rgba(t["er"], 38)
    t["wn_soft"] = _rgba(t["wn"], 38)
    t["ok_line"] = _rgba(t["ok"], 90)
    t["er_line"] = _rgba(t["er"], 90)
    t["wn_line"] = _rgba(t["wn"], 90)
    t["hover_row"] = _rgba(t["pr"], 18)
    return t


def repolish(widget: QWidget) -> None:
    """بعد از تغییر setProperty(...) باید صدا زده شود تا QSS دوباره اعمال شود."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def mpl_colors(mode: str | None = None) -> Dict[str, str]:
    """رنگ‌های هماهنگ برای نمودارهای matplotlib (Payoff و ماتریس ریسک-بازده)."""
    t = tokens(mode)
    return {
        "bg": t["sf"], "fg": t["tx"], "muted": t["mu"], "grid": t["bd"],
        "line": t["prt"], "profit": t["ok"], "loss": t["er"],
        "spot": t["wn"], "strike": "#8B7BFF", "zero": t["mu"],
    }


# ثابت‌های قدیمی (برای سازگاری با کدهای موجود)
COLOR_PROFIT_DARK = _BASE_TOKENS["dark"]["ok"]
COLOR_PROFIT_LIGHT = _BASE_TOKENS["light"]["ok"]
COLOR_LOSS_DARK = _BASE_TOKENS["dark"]["er"]
COLOR_LOSS_LIGHT = _BASE_TOKENS["light"]["er"]
COLOR_WARNING = _BASE_TOKENS["dark"]["wn"]
COLOR_INFO = _BASE_TOKENS["dark"]["prt"]
COLOR_NEUTRAL = _BASE_TOKENS["dark"]["mu"]
COLOR_ACCENT = "#8B7BFF"


# =========================================================================
# ۱. مدیریت تم و جهت چیدمان
# =========================================================================

def resolve_theme(theme_setting: str) -> ThemeMode:
    # علاوه بر برچسب‌های فارسی، مقادیر "dark"/"light" هم پذیرفته می‌شوند
    # (DEFAULT_SETTINGS["theme"] ممکن است برابر "dark" باشد).
    if theme_setting in (THEME_DARK, "dark"):
        return "dark"
    if theme_setting in (THEME_LIGHT, "light"):
        return "light"
    if theme_setting == THEME_SYSTEM:
        return "dark" if _detect_system_dark() else "light"
    return "light"


def is_dark(theme_setting: str) -> bool:
    return resolve_theme(theme_setting) == "dark"


def apply_layout_direction(app: QApplication, layout_dir: str = LAYOUT_RTL) -> None:
    if layout_dir == LAYOUT_LTR:
        app.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    else:
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)


def apply_app_layout(app: QApplication) -> None:
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)


def load_bundled_fonts() -> int:
    """
    اگر فایل‌های فونت در ui/assets/fonts/*.ttf|otf باشند بارگذاری می‌شوند
    (پیشنهاد: Vazirmatn-Regular / Medium / SemiBold / Bold).
    """
    fonts_dir = Path(__file__).resolve().parent / "assets" / "fonts"
    loaded = 0
    if fonts_dir.is_dir():
        for p in sorted(fonts_dir.iterdir()):
            if p.suffix.lower() in (".ttf", ".otf"):
                if QFontDatabase.addApplicationFont(str(p)) >= 0:
                    loaded += 1
    return loaded


def setup_persian_font(app: QApplication, preferred_font: str = "Vazirmatn", base_size: int = 10) -> None:
    load_bundled_fonts()
    font_candidates = [preferred_font, "Vazirmatn", "Shabnam", "Sahel", "Segoe UI", "Tahoma"]
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


# =========================================================================
# ۲. فرمت‌بندی بومی بازار ایران (بدون تغییر)
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


# =========================================================================
# ۳. رنگ‌های سود/زیان
# =========================================================================

def get_pnl_colors(mode: ThemeMode) -> tuple[QColor, QColor]:
    t = tokens(mode)
    return QColor(t["ok"]), QColor(t["er"])


def get_pnl_qcolor(value: Union[int, float, None], mode: ThemeMode = "dark", alpha: int = 255) -> QColor:
    t = tokens(mode)
    if value is None or value == 0:
        c = QColor(t["mu"])
    elif value > 0:
        c = QColor(t["ok"])
    else:
        c = QColor(t["er"])
    c.setAlpha(alpha)
    return c


def get_flash_qcolor(direction: str, alpha: int = 180) -> QColor:
    if direction.upper() in ("UP", "BUY", "PROFIT"):
        return QColor(46, 133, 64, alpha)
    elif direction.upper() in ("DOWN", "SELL", "LOSS"):
        return QColor(197, 48, 48, alpha)
    return QColor(43, 108, 176, alpha)


def get_empty_state_color(mode: ThemeMode) -> QColor:
    return QColor(tokens(mode)["mu"])


# =========================================================================
# ۴. استایل‌های inline قدیمی (سازگار با کدهای موجود، با رنگ‌های جدید)
#    ⚠️ در فاز بعد به‌جای این‌ها از objectName/property استفاده می‌شود.
# =========================================================================

def get_kpi_card_style(mode: ThemeMode, accent_color: str = "") -> str:
    t = tokens(mode)
    accent = accent_color or t["pr"]
    return f"""
        .QFrame {{
            background-color: {t['sf']};
            border: 1px solid {t['bd']};
            border-top: 3px solid {accent};
            border-radius: 12px;
            padding: 8px 10px;
        }}
    """


def get_filter_chip_style(active: bool, mode: str) -> str:
    t = tokens(mode)
    if active:
        bg, color, border = t["pr_soft"], t["prt"], f"1px solid {t['pr']}"
    else:
        bg, color, border = t["sf2"], t["tx"], f"1px solid {t['bd']}"
    return f"""
        QPushButton {{
            background-color: {bg}; color: {color}; border: {border};
            border-radius: 18px; padding: 4px 14px; font-size: 12px; font-weight: 500;
        }}
        QPushButton:hover {{ border-color: {t['prt']}; }}
    """


def get_toolbar_frame_style(mode: ThemeMode) -> str:
    # ".QFrame" فقط خودِ QFrame را هدف می‌گیرد، نه زیرکلاس‌هایی مثل QSplitter
    t = tokens(mode)
    return f"""
        .QFrame {{
            background-color: {t['sf']};
            border: 1px solid {t['bd']};
            border-radius: 14px;
        }}
    """


def get_separator_style(mode: ThemeMode) -> str:
    return f"background-color: {tokens(mode)['bd']}; border: none;"


def get_interval_label_style(mode: ThemeMode) -> str:
    return f"color: {tokens(mode)['mu']}; font-size: 12px;"


def get_inspector_frame_style(mode: ThemeMode) -> str:
    t = tokens(mode)
    return f"background-color: {t['sf']}; border: 1px solid {t['bd']}; border-radius: 16px;"


def get_symbol_filter_info_style(mode: ThemeMode) -> str:
    return f"font-weight: bold; color: {tokens(mode)['mu']};"


def get_info_banner_style(mode: ThemeMode) -> str:
    t = tokens(mode)
    return (f"background-color: {t['sf2']}; border: 1px solid {t['bd']}; "
            f"border-radius: 10px; padding: 10px; color: {t['mu']};")


def get_sub_panel_style(mode: ThemeMode) -> str:
    t = tokens(mode)
    return f"background-color: {t['sf2']}; border: 1px dashed {t['bd2']}; border-radius: 10px; padding: 2px;"


def get_disabled_table_style(mode: ThemeMode) -> str:
    t = tokens(mode)
    return f"QTableWidget {{ background-color: {t['sf2']}; color: {t['mu_dis']}; }}"


def get_greek_label_style(mode: ThemeMode) -> str:
    t = tokens(mode)
    return (f"font-weight: bold; background-color: {t['sf2']}; border: 1px solid {t['bd']}; "
            f"border-radius: 10px; padding: 6px;")


def get_preset_button_style(mode: ThemeMode) -> str:
    t = tokens(mode)
    return f"""
        QPushButton {{
            background-color: {t['sf2']}; color: {t['mu']}; border: 1px solid {t['bd']};
            border-radius: 8px; padding: 3px 9px; font-size: 11px; font-weight: bold; min-height: 20px;
        }}
        QPushButton:hover {{ background-color: {t['hover']}; color: {t['prt']}; border-color: {t['prt']}; }}
    """


def get_symbol_filter_stats_style(mode: ThemeMode) -> str:
    t = tokens(mode)
    return f"color: {t['mu']}; font-size: 9pt; padding: 8px; background-color: {t['sf2']}; border-radius: 8px;"


def get_dialog_profile_frame_style(mode: ThemeMode) -> str:
    t = tokens(mode)
    return f".QFrame {{ background: {t['sf2']}; border: 1px solid {t['bd']}; border-radius: 12px; padding: 6px; }}"


def _role_colors(t: Dict[str, str], role: str) -> Dict[str, str]:
    if role == "primary":
        return dict(bg=t["pr"], hover=t["pr_h"], text="#FFFFFF", border="none")
    if role == "success":
        return dict(bg=t["ok_btn"], hover=t["ok_btn_h"], text="#FFFFFF", border="none")
    if role == "danger":
        return dict(bg=t["er_btn"], hover=t["er_btn_h"], text="#FFFFFF", border="none")
    if role == "warning":
        return dict(bg=t["wn_btn"], hover=t["wn_btn_h"], text="#FFFFFF", border="none")
    return dict(bg=t["sf2"], hover=t["hover"], text=t["tx"], border=f"1px solid {t['bd']}")


def get_button_style(mode: str, role: str = "primary") -> str:
    """استایل inline یکپارچه (نسخه‌ی قدیمی API). در فاز بعد: btn.setProperty('role', role)."""
    t = tokens(mode)
    c = _role_colors(t, role)
    return f"""
        QPushButton {{
            background-color: {c['bg']}; color: {c['text']}; border: {c['border']};
            border-radius: 10px; padding: 7px 14px; font-weight: 600; min-height: 22px;
        }}
        QPushButton:hover {{ background-color: {c['hover']}; }}
        QPushButton:disabled {{
            background-color: {t['sf']}; color: {t['mu_dis']}; border: 1px solid {t['bd']};
        }}
    """


def get_accent_button_style(mode: ThemeMode, accent: str = "#8B7BFF", hover: str = "#A294FF") -> str:
    return f"""
        QPushButton {{
            background-color: {accent}; color: white; border: none;
            border-radius: 10px; padding: 8px 15px; font-weight: bold;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
    """


def get_dialog_tab_style(mode: ThemeMode) -> str:
    """استایل تب دیالوگ‌ها؛ با توکن‌ها تا با QSS سراسری هم‌رنگ بماند."""
    t = tokens(mode)
    return f"""
        QTabWidget::pane {{
            border: 1px solid {t['bd']}; border-radius: 12px;
            background-color: {t['sf']}; top: -1px; padding: 8px;
        }}
        QTabBar::tab {{
            background: transparent; color: {t['mu']};
            padding: 8px 16px; margin: 0 2px; border-radius: 8px; font-weight: 600;
        }}
        QTabBar::tab:hover {{ color: {t['tx']}; background-color: {t['sf2']}; }}
        QTabBar::tab:selected {{ background-color: {t['pr_soft']}; color: {t['prt']}; }}
    """


def get_dialog_warning_banner_style(mode: ThemeMode) -> str:
    t = tokens(mode)
    return (f"background: {t['wn_soft']}; border: 1px solid {t['wn_line']}; "
            f"border-radius: 10px; padding: 10px; color: {t['wn']};")


# =========================================================================
# ۵. QSS سراسری
# =========================================================================

_QSS = Template(r"""
QToolTip { color:$tx; background-color:$sf2; border:1px solid $bd; padding:5px 9px; border-radius:8px; font-size:11px; }
QMainWindow, QDialog { background-color:$bg; }
QWidget { color:$tx; font-family:'Vazirmatn','Shabnam','Segoe UI',Tahoma,sans-serif; }
QMessageBox { background-color:$sf; }
QLabel { background:transparent; }

/* ───────── کارت‌ها و اجزای ساختاری ───────── */
QFrame#card { background-color:$sf; border:1px solid $bd; border-radius:16px; }
QFrame#chipGroup { background-color:$sf2; border:1px solid $bd; border-radius:12px; }
QFrame#brandMark { background-color:$pr; border:none; border-radius:12px; }
QFrame#statTile { background-color:$sf2; border:1px solid $bd; border-radius:12px; }
QFrame#vsep { background-color:$bd; border:none; min-width:1px; max-width:1px; }
QFrame#hsep { background-color:$bd; border:none; min-height:1px; max-height:1px; }

QLabel#brandTitle { font-size:16px; font-weight:700; }
QLabel#brandSub { font-size:12px; color:$mu; }
QLabel#cardTitle { font-size:14px; font-weight:700; }
QLabel#cardCaption { font-size:12px; font-weight:600; color:$mu; }
QLabel#tileCaption { font-size:12px; color:$mu; }
QLabel#tileValue { font-size:15px; font-weight:700; }
QLabel#tileValue[tone="ok"] { color:$ok; }
QLabel#tileValue[tone="er"] { color:$er; }
QLabel#tileValue[tone="wn"] { color:$wn; }
QLabel#tileValue[tone="pr"] { color:$prt; }
QLabel[role="muted"] { color:$mu; font-size:12px; }
QLabel[role="selectedChip"] { padding:3px 10px; border-radius:11px; background-color:$pr_soft; color:$prt; font-weight:600; font-size:12px; }

QLabel[pill="idle"], QLabel[pill="ok"], QLabel[pill="err"], QLabel[pill="warn"] {
    padding:3px 10px; border-radius:11px; font-size:11px; font-weight:600;
    background-color:$sf2; border:1px solid $bd; color:$mu;
}
QLabel[pill="ok"]   { color:$ok; background-color:$ok_soft; border-color:$ok_line; }
QLabel[pill="err"]  { color:$er; background-color:$er_soft; border-color:$er_line; }
QLabel[pill="warn"] { color:$wn; background-color:$wn_soft; border-color:$wn_line; }

/* ───────── دکمه‌ها ───────── */
QPushButton { background-color:$sf2; color:$tx; border:1px solid $bd; border-radius:10px; padding:6px 14px; font-weight:600; min-height:24px; }
QPushButton:hover { background-color:$hover; border-color:$prt; }
QPushButton:pressed { background-color:$bd; }
QPushButton:checked { background-color:$pr_soft; border-color:$pr; color:$prt; }
QPushButton:disabled { color:$mu_dis; background-color:$sf; border-color:$bd; }

QPushButton[role="primary"] { background-color:$pr; color:#FFFFFF; border:1px solid $pr; }
QPushButton[role="primary"]:hover { background-color:$pr_h; border-color:$pr_h; }
QPushButton[role="primary"]:disabled { background-color:$pr_soft; color:$mu_dis; border-color:$pr_soft; }
QPushButton[role="success"] { background-color:$ok_btn; color:#FFFFFF; border:1px solid $ok_btn; }
QPushButton[role="success"]:hover { background-color:$ok_btn_h; border-color:$ok_btn_h; }
QPushButton[role="danger"] { background-color:$er_btn; color:#FFFFFF; border:1px solid $er_btn; }
QPushButton[role="danger"]:hover { background-color:$er_btn_h; border-color:$er_btn_h; }
QPushButton[role="warning"] { background-color:$wn_btn; color:#FFFFFF; border:1px solid $wn_btn; }
QPushButton[role="warning"]:hover { background-color:$wn_btn_h; border-color:$wn_btn_h; }
QPushButton[role="success"]:disabled, QPushButton[role="danger"]:disabled, QPushButton[role="warning"]:disabled {
    background-color:$sf; color:$mu_dis; border-color:$bd;
}

QPushButton[chip="true"] { border-radius:20px; padding:4px 14px; font-weight:500; min-height:30px; }
QPushButton[chip="true"][active="true"] { background-color:$pr_soft; border:1px solid $pr; color:$prt; }
QPushButton#iconButton { padding:0; min-width:44px; max-width:44px; min-height:44px; max-height:44px; border-radius:12px; }

/* ───────── ورودی‌ها ───────── */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background-color:$input_bg; color:$tx; border:1px solid $bd; border-radius:10px;
    padding:6px 10px; selection-background-color:$pr; selection-color:#FFFFFF;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus { border-color:$pr; }
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled { color:$mu_dis; background-color:$sf; }
QComboBox::drop-down { border:none; width:24px; }
QComboBox QAbstractItemView { background-color:$sf; color:$tx; border:1px solid $bd; border-radius:8px; selection-background-color:$pr_soft; selection-color:$tx; outline:0; }

QCheckBox, QRadioButton { spacing:8px; background:transparent; }
QCheckBox::indicator { width:18px; height:18px; border-radius:5px; border:1.5px solid $bd2; background-color:$input_bg; }
QCheckBox::indicator:hover { border-color:$pr; }
QCheckBox::indicator:checked { background-color:$pr; border-color:$pr; image:url('$check'); }
QRadioButton::indicator { width:16px; height:16px; border-radius:9px; border:1.5px solid $bd2; background-color:$input_bg; }
QRadioButton::indicator:checked { background-color:$pr; border-color:$pr; }

QSlider::groove:horizontal { height:5px; background:$bd; border-radius:2px; }
QSlider::sub-page:horizontal { background:$pr; border-radius:2px; }
QSlider::handle:horizontal { background:#FFFFFF; border:2px solid $pr; width:14px; margin:-6px 0; border-radius:8px; }

/* ───────── جدول‌ها ───────── */
QTableView, QTableWidget { background-color:$sf; alternate-background-color:$sf; gridline-color:transparent; border:none; outline:0; selection-background-color:$sel; selection-color:$tx; }
QTableView::item { padding:0 8px; border:none; border-bottom:1px solid $bd; }
QTableView::item:hover { background-color:$hover_row; }
QTableView::item:selected { background-color:$sel; color:$tx; }
QTableView::indicator { width:16px; height:16px; border-radius:4px; border:1.5px solid $bd2; background-color:$input_bg; }
QTableView::indicator:checked { background-color:$pr; border-color:$pr; image:url('$check'); }
QHeaderView { background-color:$sf2; border:none; }
QHeaderView::section { background-color:$sf2; color:$mu; padding:10px 8px; border:none; border-bottom:1px solid $bd; font-weight:600; font-size:12px; }
QHeaderView::section:hover { color:$tx; }
QTableCornerButton::section { background-color:$sf2; border:none; }

QListView, QListWidget { background-color:$sf; alternate-background-color:$sf2; border:1px solid $bd; border-radius:10px; outline:0; }
QListView::item { padding:6px 8px; border-radius:6px; }
QListView::item:hover { background-color:$hover; }
QListView::item:selected { background-color:$pr_soft; color:$tx; }

/* ───────── کانتینرها ───────── */
QGroupBox { font-weight:700; border:1px solid $bd; border-radius:12px; margin-top:14px; padding:14px 12px 10px 12px; background-color:$sf; }
QGroupBox::title { subcontrol-origin:margin; subcontrol-position:top right; padding:0 8px; color:$prt; }
QTabWidget::pane { border:1px solid $bd; border-radius:12px; background-color:$sf; top:-1px; }
QTabBar::tab { background:transparent; color:$mu; padding:8px 16px; margin:0 2px; border-radius:8px; font-weight:600; }
QTabBar::tab:hover { color:$tx; background-color:$sf2; }
QTabBar::tab:selected { background-color:$pr_soft; color:$prt; }
QSplitter::handle { background:transparent; }
QSplitter::handle:hover { background-color:$bd; }

QMenu { background-color:$sf; color:$tx; border:1px solid $bd; border-radius:10px; padding:6px; }
QMenu::item { padding:8px 22px 8px 16px; border-radius:6px; }
QMenu::item:selected { background-color:$pr_soft; color:$prt; }
QMenu::separator { height:1px; background:$bd; margin:4px 8px; }

QProgressBar { background-color:$sf2; border:1px solid $bd; border-radius:7px; text-align:center; color:$tx; font-size:11px; min-height:14px; }
QProgressBar::chunk { background-color:$pr; border-radius:6px; }
QStatusBar { background-color:$sf; border-top:1px solid $bd; color:$mu; }
QStatusBar::item { border:none; }

/* ───────── اسکرول‌بار ───────── */
QAbstractScrollArea::corner { background:transparent; }
QScrollBar:vertical { background:transparent; width:12px; margin:2px; }
QScrollBar::handle:vertical { background:$scroll; min-height:32px; border-radius:4px; margin:0 2px; }
QScrollBar::handle:vertical:hover { background:$scroll_h; }
QScrollBar::handle:vertical:pressed { background:$prt; }
QScrollBar:horizontal { background:transparent; height:12px; margin:2px; }
QScrollBar::handle:horizontal { background:$scroll; min-width:32px; border-radius:4px; margin:2px 0; }
QScrollBar::handle:horizontal:hover { background:$scroll_h; }
QScrollBar::handle:horizontal:pressed { background:$prt; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; height:0; background:none; border:none; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical, QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background:transparent; }
""")


def _check_icon_path() -> str:
    """آیکون تیکِ سفید برای چک‌باکس‌ها (فایل PNG موقت؛ QSS فقط با فایل می‌تواند image بگیرد)."""
    try:
        from ui import icons
        return icons.write_png("check", "#FFFFFF", 14, "check_white.png")
    except Exception as e:  # pragma: no cover
        logger.warning(f"check icon not generated: {e}")
        return ""


def get_global_stylesheet(mode: ThemeMode) -> str:
    t = tokens(mode)
    t["check"] = _check_icon_path()
    return _QSS.safe_substitute(t)


# =========================================================================
# ۶. Palette و تشخیص تم سیستم
# =========================================================================

def _detect_system_dark() -> bool:
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        return scheme == Qt.ColorScheme.Dark
    except Exception:
        pass
    return False


def _apply_palette(app: QApplication, mode: ThemeMode) -> None:
    t = tokens(mode)
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(t["bg"]))
    p.setColor(QPalette.ColorRole.WindowText, QColor(t["tx"]))
    p.setColor(QPalette.ColorRole.Base, QColor(t["sf"]))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(t["sf2"]))
    p.setColor(QPalette.ColorRole.Text, QColor(t["tx"]))
    p.setColor(QPalette.ColorRole.Button, QColor(t["sf2"]))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(t["tx"]))
    p.setColor(QPalette.ColorRole.Highlight, QColor(t["pr"]))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(t["mu"]))
    p.setColor(QPalette.ColorRole.Link, QColor(t["prt"]))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(t["sf2"]))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(t["tx"]))
    app.setPalette(p)
