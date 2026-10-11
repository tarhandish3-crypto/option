# position_saver/theme.py
# -*- coding: utf-8 -*-

"""
تم مرکزی برنامه: پالت رنگ، QSS سراسری و توابع قالب‌بندی.

فقط به PySide6 وابسته است. هیچ وابستگی به سایر ماژول‌های برنامه ندارد.

استفاده:
    # در main.py
    from position_saver.theme import apply_theme
    apply_theme(app)

    # در سایر ماژول‌ها
    from position_saver.theme import (
        Theme, CURRENCY,
        fmt_money, fmt_pct, fmt_pnl, fmt_int, fmt_date,
        pnl_tone, set_kind, set_tone, set_invalid,
    )
"""

from PySide6.QtGui import QFont


# =====================================================
# پالت رنگ
# =====================================================

class Theme:
    """پالت رنگ مرکزی برنامه"""

    # ─── رنگ‌های اصلی ───
    PRIMARY = "#1E6FD9"
    PRIMARY_DARK = "#1859B0"
    PRIMARY_LIGHT = "#DCEBFF"

    # ─── رنگ‌های معنایی ───
    PROFIT = "#1B8A5A"      # سبز — سود
    LOSS = "#D64545"        # قرمز — زیان
    WARN = "#C77700"        # نارنجی — هشدار
    INFO = "#2196F3"        # آبی — اطلاع

    # ─── پس‌زمینه ───
    BG = "#F5F7FA"          # پس‌زمینه کلی
    CARD = "#FFFFFF"        # پس‌زمینه کارت‌ها
    BORDER = "#E3E8EF"      # مرزها
    ZEBRA = "#F8FAFC"       # خطوط یک‌درمیان جدول
    HEADER = "#EEF2F7"      # هدر جدول

    # ─── تعامل ───
    HOVER = "#EEF3FB"       # هاور
    SELECT = "#DCEBFF"      # انتخاب
    DISABLED_BG = "#EEF1F5"  # غیرفعال

    # ─── متن ───
    TEXT = "#1F2937"        # متن اصلی
    MUTED = "#6B7280"       # متن خاکستری
    TEXT_LIGHT = "#9AA3AF"  # متن غیرفعال


# واحد نمایش مبالغ — در صورت نیاز فقط این‌جا عوض شود
CURRENCY = "تومان"

# علامت LRM برای جلوگیری از جابجایی علامت منفی در متن راست‌به‌چپ
_LRM = "\u200e"


# =====================================================
# توابع قالب‌بندی
# =====================================================

def fmt_money(value, signed: bool = False) -> str:
    """
    عدد صحیح با جداکننده هزارگان.

    Args:
        value: مقدار عددی
        signed: اگر True، علامت + برای مثبت‌ها می‌گذارد

    Returns:
        مثال: '1,234,567' یا '+1,234,567'
    """
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        return "—"
    text = f"{v:+,}" if signed else f"{v:,}"
    return _LRM + text


def fmt_pct(value, digits: int = 1, signed: bool = True) -> str:
    """
    فرمت‌دهی درصد.

    Args:
        value: مقدار درصد (مثلاً 5.5)
        digits: تعداد رقم اعشار
        signed: اگر True، علامت + برای مثبت‌ها

    Returns:
        مثال: '+5.5%' یا '5.5%'
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    text = f"{v:+.{digits}f}%" if signed else f"{v:.{digits}f}%"
    return _LRM + text


def fmt_pnl(pnl: float, roi: float) -> str:
    """
    ترکیب سود/زیان و درصد بازدهی.

    Returns:
        مثال: '1,200,000 (+3.2%)'
    """
    return f"{fmt_money(pnl)} ({fmt_pct(roi)})"


def fmt_int(value) -> str:
    """
    عدد صحیح با جداکننده هزارگان (بدون واحد).

    Returns:
        مثال: '1,234,567'
    """
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        return "—"
    return _LRM + f"{v:,}"


def fmt_date(date_str) -> str:
    """
    فرمت‌دهی تاریخ (شمسي از jdatetime یا رشته).

    Args:
        date_str: jdatetime.date یا رشته '1403/01/15'

    Returns:
        '1403/01/15' یا '—'
    """
    if not date_str:
        return "—"
    return str(date_str).strip()


def fmt_datetime(dt) -> str:
    """
    فرمت‌دهی تاریخ و زمان.

    Returns:
        '1403/01/15 10:30:45' یا '—'
    """
    if dt is None:
        return "—"
    try:
        return dt.strftime("%Y/%m/%d %H:%M:%S")
    except AttributeError:
        return str(dt).strip()


# =====================================================
# توابع معنایی (tone)
# =====================================================

def pnl_tone(value: float) -> str:
    """
    تشخیص tone بر اساس علامت مقدار.

    Returns:
        'profit' | 'loss' | 'neutral'
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "neutral"
    if v > 0:
        return "profit"
    if v < 0:
        return "loss"
    return "neutral"


def days_tone(days: int) -> str:
    """
    تشخیص tone بر اساس تعداد روزهای باقی‌مانده.

    Returns:
        'loss' (زیر ۳ روز) | 'warn' (زیر ۷ روز) | 'muted'
    """
    if days is None:
        return "muted"
    if days <= 3:
        return "loss"
    if days <= 7:
        return "warn"
    return "muted"


def tone_color(tone: str) -> str:
    """تبدیل tone به رنگ hex"""
    return {
        "profit": Theme.PROFIT,
        "loss": Theme.LOSS,
        "warn": Theme.WARN,
        "primary": Theme.PRIMARY,
        "info": Theme.INFO,
        "muted": Theme.MUTED,
        "neutral": Theme.TEXT,
    }.get(tone, Theme.TEXT)


# =====================================================
# کمکی‌های استایل (repolish)
# =====================================================

def _repolish(widget) -> None:
    """
    بازخوانی استایل QSS بعد از تغییر property.

    در Qt، وقتی property یک ویجت تغییر می‌کند،
    QSS به‌صورت خودکار اعمال نمی‌شود. این تابع آن را اعمال می‌کند.
    """
    try:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()
    except Exception:
        pass


def set_kind(button, kind: str = "") -> None:
    """
    تنظیم نوع دکمه برای اعمال QSS.

    Args:
        button: QPushButton یا QToolButton
        kind: 'primary' | 'danger' | '' (خنثی)
    """
    button.setProperty("kind", kind)
    _repolish(button)


def set_tone(widget, tone: str = "", big: bool = False) -> None:
    """
    تنظیم رنگ معنایی یک لیبل.

    Args:
        widget: QLabel
        tone: 'profit' | 'loss' | 'warn' | 'primary' | 'muted' | 'neutral'
        big: اگر True، فونت بزرگ‌تر
    """
    widget.setProperty("tone", tone)
    widget.setProperty("big", big)
    _repolish(widget)


def set_invalid(widget, invalid: bool) -> None:
    """
    علامت‌گذاری فیلد نامعتبر (حاشیه قرمز).

    Args:
        widget: QLineEdit
        invalid: True = نامعتبر
    """
    widget.setProperty("invalid", bool(invalid))
    _repolish(widget)


# =====================================================
# QSS (استایل سراسری)
# =====================================================

QSS = f"""
/* ============================================ */
/* پس‌زمینه کلی                                  */
/* ============================================ */
QDialog, QMainWindow, QWidget#PositionSaver {{
    background: {Theme.BG};
}}

QToolTip {{
    background: {Theme.CARD};
    color: {Theme.TEXT};
    border: 1px solid {Theme.BORDER};
    border-radius: 4px;
    padding: 4px 6px;
}}

/* ============================================ */
/* دکمه‌ها                                       */
/* ============================================ */
QPushButton, QToolButton {{
    background: {Theme.CARD};
    color: {Theme.TEXT};
    border: 1px solid {Theme.BORDER};
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 20px;
}}

QPushButton:hover, QToolButton:hover {{
    background: {Theme.HOVER};
    border-color: #C9D2DE;
}}

QPushButton:pressed, QToolButton:pressed {{
    background: {Theme.SELECT};
}}

QPushButton:disabled, QToolButton:disabled {{
    color: {Theme.MUTED};
    background: {Theme.DISABLED_BG};
    border-color: {Theme.BORDER};
}}

/* دکمه primary (آبی) */
QPushButton[kind="primary"] {{
    background: {Theme.PRIMARY};
    color: white;
    border: 1px solid {Theme.PRIMARY};
    font-weight: bold;
}}

QPushButton[kind="primary"]:hover {{
    background: {Theme.PRIMARY_DARK};
    border-color: {Theme.PRIMARY_DARK};
}}

QPushButton[kind="primary"]:pressed {{
    background: #144A8E;
}}

QPushButton[kind="primary"]:disabled {{
    background: #A0BEE6;
    border-color: #A0BEE6;
    color: #E8EFFB;
}}

/* دکمه danger (قرمز) */
QPushButton[kind="danger"] {{
    background: {Theme.LOSS};
    color: white;
    border: 1px solid {Theme.LOSS};
    font-weight: bold;
}}

QPushButton[kind="danger"]:hover {{
    background: #B93A3A;
    border-color: #B93A3A;
}}

QPushButton[kind="danger"]:pressed {{
    background: #9C3030;
}}

/* ============================================ */
/* ورودی‌ها                                      */
/* ============================================ */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: white;
    color: {Theme.TEXT};
    border: 1px solid {Theme.BORDER};
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 20px;
    selection-background-color: {Theme.PRIMARY};
    selection-color: white;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus {{
    border: 1px solid {Theme.PRIMARY};
}}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QComboBox:disabled {{
    background: {Theme.DISABLED_BG};
    color: {Theme.TEXT_LIGHT};
}}

QLineEdit[invalid="true"] {{
    border: 1px solid {Theme.LOSS};
    background: #FFF5F5;
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox QAbstractItemView {{
    background: {Theme.CARD};
    border: 1px solid {Theme.BORDER};
    selection-background-color: {Theme.PRIMARY};
    selection-color: white;
    outline: none;
}}

/* ============================================ */
/* گروه‌ها (QGroupBox)                          */
/* ============================================ */
QGroupBox {{
    background: {Theme.CARD};
    border: 1px solid {Theme.BORDER};
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 10px;
    font-weight: bold;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top right;
    padding: 0 8px;
    color: {Theme.MUTED};
    background: {Theme.CARD};
}}

/* ============================================ */
/* تب‌ها                                         */
/* ============================================ */
QTabWidget::pane {{
    border: 1px solid {Theme.BORDER};
    background: {Theme.CARD};
    border-radius: 4px;
    top: -1px;
}}

QTabBar::tab {{
    background: {Theme.HEADER};
    color: {Theme.MUTED};
    padding: 8px 18px;
    border: 1px solid {Theme.BORDER};
    border-bottom: none;
    margin-left: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    min-width: 100px;
}}

QTabBar::tab:selected {{
    background: {Theme.CARD};
    color: {Theme.TEXT};
    font-weight: bold;
    border-bottom: 2px solid {Theme.PRIMARY};
}}

QTabBar::tab:hover:!selected {{
    background: #DDE5EF;
}}

/* ============================================ */
/* جدول                                         */
/* ============================================ */
QTableWidget {{
    background: {Theme.CARD};
    alternate-background-color: {Theme.ZEBRA};
    border: 1px solid {Theme.BORDER};
    border-radius: 4px;
    gridline-color: transparent;
    selection-background-color: {Theme.SELECT};
    selection-color: {Theme.TEXT};
    outline: none;
}}

QTableWidget::item {{
    padding: 4px;
}}

QTableWidget::item:selected {{
    background: {Theme.SELECT};
    color: {Theme.TEXT};
}}

QHeaderView::section {{
    background: {Theme.HEADER};
    color: {Theme.TEXT};
    border: none;
    border-bottom: 1px solid {Theme.BORDER};
    border-right: 1px solid {Theme.BORDER};
    padding: 7px 4px;
    font-weight: bold;
}}

QHeaderView::section:last {{
    border-right: none;
}}

QTableCornerButton::section {{
    background: {Theme.HEADER};
    border: none;
}}

/* ============================================ */
/* منو                                          */
/* ============================================ */
QMenu {{
    background: {Theme.CARD};
    border: 1px solid {Theme.BORDER};
    border-radius: 4px;
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 26px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background: {Theme.SELECT};
    color: {Theme.TEXT};
}}

QMenu::separator {{
    height: 1px;
    background: {Theme.BORDER};
    margin: 4px 8px;
}}

/* ============================================ */
/* کارت‌های خلاصه                                */
/* ============================================ */
QFrame#card {{
    background: {Theme.CARD};
    border: 1px solid {Theme.BORDER};
    border-radius: 8px;
}}

QLabel#cardTitle {{
    color: {Theme.MUTED};
    font-size: 11px;
}}

QLabel#cardValue {{
    font-size: 19px;
    font-weight: bold;
}}

/* ============================================ */
/* نوار وضعیت                                    */
/* ============================================ */
QStatusBar {{
    background: {Theme.CARD};
    border-top: 1px solid {Theme.BORDER};
    color: {Theme.MUTED};
}}

QStatusBar::item {{
    border: none;
}}

/* ============================================ */
/* رنگ‌های معنایی برچسب (tone)                   */
/* ============================================ */
QLabel[tone="profit"] {{
    color: {Theme.PROFIT};
    font-weight: bold;
}}

QLabel[tone="loss"] {{
    color: {Theme.LOSS};
    font-weight: bold;
}}

QLabel[tone="warn"] {{
    color: {Theme.WARN};
    font-weight: bold;
}}

QLabel[tone="info"] {{
    color: {Theme.INFO};
    font-weight: bold;
}}

QLabel[tone="primary"] {{
    color: {Theme.PRIMARY};
    font-weight: bold;
}}

QLabel[tone="neutral"] {{
    color: {Theme.TEXT};
    font-weight: bold;
}}

QLabel[tone="muted"] {{
    color: {Theme.MUTED};
}}

QLabel[big="true"] {{
    font-size: 15px;
}}

/* ============================================ */
/* چک‌باکس و رادیو                              */
/* ============================================ */
QCheckBox, QRadioButton {{
    spacing: 6px;
}}

/* ============================================ */
/* اسکرول‌بار                                    */
/* ============================================ */
QScrollBar:vertical {{
    background: {Theme.BG};
    width: 12px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: #C9D2DE;
    border-radius: 6px;
    min-height: 30px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background: #A6B2C0;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {Theme.BG};
    height: 12px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: #C9D2DE;
    border-radius: 6px;
    min-width: 30px;
    margin: 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background: #A6B2C0;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ============================================ */
/* لیست (Autocomplete)                          */
/* ============================================ */
QListWidget {{
    background: {Theme.CARD};
    border: 1px solid {Theme.BORDER};
    border-radius: 4px;
    outline: none;
}}

QListWidget::item {{
    padding: 4px 8px;
}}

QListWidget::item:selected {{
    background: {Theme.PRIMARY};
    color: white;
}}

QListWidget::item:hover {{
    background: #E3F2FD;
}}

/* ============================================ */
/* فریم‌های خط‌دار                                */
/* ============================================ */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    background: {Theme.CARD};
    border: 1px solid {Theme.BORDER};
    border-radius: 6px;
}}

/* ============================================ */
/* QMessageBox                                   */
/* ============================================ */
QMessageBox {{
    background: {Theme.BG};
}}

QMessageBox QLabel {{
    color: {Theme.TEXT};
}}
"""


# =====================================================
# اعمال تم روی QApplication
# =====================================================

def apply_theme(app) -> None:
    """
    اعمال سبک Fusion، فونت و QSS سراسری روی QApplication.

    Args:
        app: QApplication instance
    """
    try:
        # سبک Fusion
        app.setStyle("Fusion")

        # فونت سیستمی
        app.setFont(QFont("Tahoma", 9))

        # QSS سراسری
        app.setStyleSheet(QSS)
    except Exception as e:
        print(f"[Theme] Failed to apply theme: {e}")
