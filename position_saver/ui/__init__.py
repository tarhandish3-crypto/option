# position_saver/ui/__init__.py
# -*- coding: utf-8 -*-

"""
ماژول UI پکیج Position Saver.

شامل:
    - PositionSaverWidget: ویجت اصلی
    - دیالوگ‌ها: ویرایش، تسویه، آفست، تاریخچه
    - دیالوگ‌های تخصصی: پر کردن نماد، تحلیل نماد، تعریف استراتژی
    - چک استراتژی جدید
    - گزارش‌گیری
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
    # توابع کمکی
    find_conflicts,
    build_conflict_message,
    # ثابت‌ها
    BROKER_NAMES,
    DEFAULT_BROKER,
    AUTO_SWITCH_KEYBOARD,
)


# ═══════════════════════════════════════════════════
# ۲. دیالوگ Split (با محافظت)
# ═══════════════════════════════════════════════════

try:
    from position_saver.ui.split_position_dialog import (
        SplitPositionDialog,
        SPLIT_REASONS,
    )
    _SPLIT_DIALOG_AVAILABLE = True
except ImportError:
    SplitPositionDialog = None
    SPLIT_REASONS = []
    _SPLIT_DIALOG_AVAILABLE = False


# ═══════════════════════════════════════════════════
# ۳. دیالوگ‌های تخصصی
# ═══════════════════════════════════════════════════

try:
    from position_saver.ui.symbol_fill_dialog import SymbolFillDialog
    _SYMBOL_FILL_AVAILABLE = True
except ImportError:
    SymbolFillDialog = None
    _SYMBOL_FILL_AVAILABLE = False

try:
    from position_saver.ui.net_position_dialog import NetPositionDialog
    _NET_POSITION_AVAILABLE = True
except ImportError:
    NetPositionDialog = None
    _NET_POSITION_AVAILABLE = False

try:
    from position_saver.ui.strategy_dialog import (
        StrategyDialog,
        STANDARD_STRATEGIES,
    )
    _STRATEGY_DIALOG_AVAILABLE = True
except ImportError:
    StrategyDialog = None
    STANDARD_STRATEGIES = []
    _STRATEGY_DIALOG_AVAILABLE = False


# ═══════════════════════════════════════════════════
# ۴. چک استراتژی جدید
# ═══════════════════════════════════════════════════

try:
    from position_saver.ui.strategy_check_dialog import (
        StrategyCheckDialog,
    )
    _STRATEGY_CHECK_AVAILABLE = True
except ImportError:
    StrategyCheckDialog = None
    _STRATEGY_CHECK_AVAILABLE = False


# ═══════════════════════════════════════════════════
# ۵. گزارش‌گیری
# ═══════════════════════════════════════════════════

try:
    from position_saver.ui.report_dialog import (
        ReportDialog,
        ReportFilter,
        ReportRow,
        ReportResult,
        BaseReportExporter,
        ExcelReportExporter,
    )
    _REPORT_AVAILABLE = True
except ImportError:
    ReportDialog = None
    ReportFilter = None
    ReportRow = None
    ReportResult = None
    BaseReportExporter = None
    ExcelReportExporter = None
    _REPORT_AVAILABLE = False


# ═══════════════════════════════════════════════════
# ۶. Wizard ایمپورت
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
# ۷. ویجت اصلی (آخر — برای جلوگیری از circular)
# ═══════════════════════════════════════════════════

from position_saver.ui.main_widget import PositionSaverWidget


# ═══════════════════════════════════════════════════
# ۸. صادرکننده‌ها
# ═══════════════════════════════════════════════════

__all__ = [
    # ─── Widgets ───
    "PositionSaverWidget",

    # ─── دیالوگ‌های پایه ───
    "PositionEditDialog",
    "CashSettlementDialog",
    "OffsetDialog",
    "ImportHistoryDialog",

    # ─── توابع کمکی ───
    "find_conflicts",
    "build_conflict_message",

    # ─── دیالوگ‌های تخصصی ───
    "SymbolFillDialog",
    "NetPositionDialog",
    "StrategyDialog",
    "SplitPositionDialog",
    "SPLIT_REASONS",

    # ─── چک استراتژی ───
    "StrategyCheckDialog",

    # ─── گزارش‌گیری ───
    "ReportDialog",
    "ReportFilter",
    "ReportRow",
    "ReportResult",
    "BaseReportExporter",
    "ExcelReportExporter",

    # ─── Wizard ───
    "ImportWizardDialog",

    # ─── ثابت‌ها ───
    "STANDARD_STRATEGIES",
    "BROKER_NAMES",
    "DEFAULT_BROKER",
    "AUTO_SWITCH_KEYBOARD",

    # ─── پرچم‌ها ───
    "_IMPORT_WIZARD_AVAILABLE",
    "_STRATEGY_CHECK_AVAILABLE",
    "_REPORT_AVAILABLE",
    "_SPLIT_DIALOG_AVAILABLE",
    "_SYMBOL_FILL_AVAILABLE",
    "_NET_POSITION_AVAILABLE",
    "_STRATEGY_DIALOG_AVAILABLE",
]