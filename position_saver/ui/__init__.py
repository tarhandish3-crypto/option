# position_saver/ui/__init__.py
# -*- coding: utf-8 -*-

"""
ماژول UI پکیج Position Saver.

شامل:
    - PositionSaverWidget: ویجت اصلی مدیریت موقعیت‌ها
    - دیالوگ‌های کاربردی: ویرایش، تسویه، آفست، تاریخچه‌ی ایمپورت
    - Wizard ایمپورت اکسل
    - ثابت‌ها: نام کارگزاری‌ها، تنظیمات کیبورد
"""

# ═══════════════════════════════════════════════════
# ۱. دیالوگ‌ها (اول، چون ویجت اصلی به آن‌ها وابسته است)
# ═══════════════════════════════════════════════════

from position_saver.ui.dialogs import (
    PositionEditDialog,
    CashSettlementDialog,
    OffsetDialog,
    ImportHistoryDialog,
    # ثابت‌ها
    BROKER_NAMES,
    DEFAULT_BROKER,
    AUTO_SWITCH_KEYBOARD,
)


# ═══════════════════════════════════════════════════
# ۲. ویجت اصلی
# ═══════════════════════════════════════════════════

from position_saver.ui.main_widget import PositionSaverWidget


# ═══════════════════════════════════════════════════
# ۳. Wizard ایمپورت
# ═══════════════════════════════════════════════════

try:
    from position_saver.ui.import_wizard_dialog import (
        ImportWizardDialog,
    )
    _IMPORT_WIZARD_AVAILABLE = True
except ImportError:
    ImportWizardDialog = None
    _IMPORT_WIZARD_AVAILABLE = False


# ═══════════════════════════════════════════════════
# ۴. صادرکننده‌ها
# ═══════════════════════════════════════════════════

__all__ = [
    # ─── ویجت اصلی ───
    "PositionSaverWidget",

    # ─── دیالوگ‌ها ───
    "PositionEditDialog",
    "CashSettlementDialog",
    "OffsetDialog",
    "ImportHistoryDialog",

    # ─── Wizard ───
    "ImportWizardDialog",

    # ─── ثابت‌های UI ───
    "BROKER_NAMES",
    "DEFAULT_BROKER",
    "AUTO_SWITCH_KEYBOARD",

    # ─── پرچم‌ها ───
    "_IMPORT_WIZARD_AVAILABLE",
]