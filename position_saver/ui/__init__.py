# position_saver/ui/__init__.py
# -*- coding: utf-8 -*-

"""
ماژول UI پکیج Position Saver.

شامل:
    - PositionSaverWidget: ویجت اصلی
    - دیالوگ‌ها: ویرایش، تسویه، آفست، تاریخچه، نوع اعمال
    - دیالوگ‌های تخصصی: پر کردن نماد، تحلیل نماد، تعریف استراتژی
    - Wizard ایمپورت اکسل
    - ثابت‌ها: کارگزاری‌ها، استراتژی‌های استاندارد
"""

# ═══════════════════════════════════════════════════
# ۱. دیالوگ‌های پایه
# ═══════════════════════════════════════════════════

from position_saver.ui.dialogs import (
    PositionEditDialog,
    CashSettlementDialog,
    OffsetDialog,
    ImportHistoryDialog,
    ExerciseTypeDialog,
    # ثابت‌ها
    BROKER_NAMES,
    DEFAULT_BROKER,
    AUTO_SWITCH_KEYBOARD,
)

from position_saver.ui.split_position_dialog import (
    SplitPositionDialog,
    SPLIT_REASONS,
)


# ═══════════════════════════════════════════════════
# ۲. دیالوگ‌های تخصصی
# ═══════════════════════════════════════════════════

from position_saver.ui.symbol_fill_dialog import SymbolFillDialog

from position_saver.ui.net_position_dialog import NetPositionDialog

from position_saver.ui.strategy_dialog import (
    StrategyDialog,
    STANDARD_STRATEGIES,
)


# ═══════════════════════════════════════════════════
# ۳. ویجت اصلی
# ═══════════════════════════════════════════════════

from position_saver.ui.main_widget import PositionSaverWidget


# ═══════════════════════════════════════════════════
# ۴. Wizard ایمپورت (با محافظت)
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
# ۵. صادرکننده‌ها
# ═══════════════════════════════════════════════════

__all__ = [
    # ─── Widgets ───
    "PositionSaverWidget",

    # ─── دیالوگ‌های پایه ───
    "PositionEditDialog",
    "CashSettlementDialog",
    "OffsetDialog",
    "ImportHistoryDialog",
    "ExerciseTypeDialog",

    # ─── دیالوگ‌های تخصصی ───
    "SymbolFillDialog",
    "NetPositionDialog",
    "StrategyDialog",
    "SplitPositionDialog",
    "SPLIT_REASONS",

    # ─── Wizard ───
    "ImportWizardDialog",

    # ─── ثابت‌ها ───
    "STANDARD_STRATEGIES",
    "BROKER_NAMES",
    "DEFAULT_BROKER",
    "AUTO_SWITCH_KEYBOARD",

    # ─── پرچم‌ها ───
    "_IMPORT_WIZARD_AVAILABLE",
]